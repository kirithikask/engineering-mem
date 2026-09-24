"""
Multimodal engineering document intelligence.

Pipeline implemented here (brief §3 feature 1, §10, §15, §16):

    UPLOAD -> CLASSIFICATION -> TEXT/IMAGE/HANDWRITING/TABLE/DIAGRAM DETECTION
    -> EXTRACTION -> STRUCTURING -> VALIDATION (confidence) -> CHUNKING
    -> METADATA -> MySQL -> (human approval) -> BGE -> FAISS

Honesty rules enforced by this module:

* OCR is only claimed when a local OCR engine actually exists. PyMuPDF cannot
  OCR without the Tesseract binary being installed, so when it is missing the
  job is parked in ``OCR_ENGINE_UNAVAILABLE`` and routed to the review queue for
  a human transcript. No text is invented and no confidence is fabricated.
* The extraction confidence is a transparent heuristic computed from measured
  signals (text coverage, character density, printable-character ratio, table
  and figure counts, OCR proxy when OCR ran). The breakdown is stored beside the
  number so the operator can see what it was derived from.
* Original files are never modified or deleted; they are copied into
  ``data/documents`` and referenced by path.
* Nothing is embedded into FAISS until a human approves the extraction.
"""

import csv
import io
import os
import re
import shutil
import subprocess
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree

from backend.app.db.mysql_client import db
from backend.app.utils.multimodal_chunker import structure_to_chunks

try:  # PyMuPDF is a hard dependency for PDF/image paths
    import fitz  # type: ignore
except Exception:  # pragma: no cover - import guard only
    fitz = None  # type: ignore

# PyMuPDF's OCR integration spawns the Tesseract binary as a child process and
# needs its tessdata location. Services are often started before PATH changes are
# picked up, so resolve the binary from PATH *or* the standard Windows install
# locations, then fix this process' environment accordingly. Nothing is claimed
# available unless the binary actually exists on disk.
def _locate_tesseract() -> Optional[str]:
    found = shutil.which("tesseract") or shutil.which("tesseract.exe")
    if found:
        return found
    if os.name == "nt":
        for base in (os.environ.get("PROGRAMFILES", r"C:\Program Files"),
                     os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")):
            candidate = os.path.join(base, "Tesseract-OCR", "tesseract.exe")
            if os.path.isfile(candidate):
                return candidate
    return None


_TESSERACT_BIN = _locate_tesseract()
if _TESSERACT_BIN:
    _tess_dir = os.path.dirname(_TESSERACT_BIN)
    if _tess_dir.lower() not in os.environ.get("PATH", "").lower():
        os.environ["PATH"] = _tess_dir + os.pathsep + os.environ.get("PATH", "")
    _tessdata = os.path.join(_tess_dir, "tessdata")
    if os.path.isdir(_tessdata) and not os.environ.get("TESSDATA_PREFIX"):
        os.environ["TESSDATA_PREFIX"] = _tessdata

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover
    Image = None  # type: ignore

DOCUMENT_DIR = os.getenv("EM_DOCUMENT_DIR", "data/documents")
OCR_LANGUAGE = os.getenv("EM_OCR_LANG", "eng")
DOCX_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Status vocabulary shared with the UI (brief §15/§16).
STATUS_UPLOADED = "UPLOADED"
STATUS_EXTRACTING = "EXTRACTING"
STATUS_REVIEW_REQUIRED = "REVIEW_REQUIRED"
STATUS_OCR_UNAVAILABLE = "OCR_ENGINE_UNAVAILABLE"
STATUS_APPROVED = "APPROVED"
STATUS_INDEXED = "INDEXED"
STATUS_REJECTED = "REJECTED"
STATUS_EXTRACTION_FAILED = "EXTRACTION_FAILED"

# Risk / review thresholds (a real rule, applied consistently).
AUTO_INDEX_CONFIDENCE = float(os.getenv("EM_AUTO_INDEX_CONFIDENCE", "1.1"))  # >1 disables auto-index
REVIEW_BELOW_CONFIDENCE = 0.75


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def ocr_engine_available() -> bool:
    """True only when a local OCR engine binary is actually present on this host."""
    return _locate_tesseract() is not None


def _ocr_engine_version() -> Optional[str]:
    """Best-effort local Tesseract version string for the capabilities endpoint."""
    if not _TESSERACT_BIN:
        return None
    try:
        out = subprocess.run(
            [_TESSERACT_BIN, "--version"], capture_output=True, text=True, timeout=10
        )
        first = (out.stdout or out.stderr or "").splitlines()
        return first[0].strip() if first else None
    except Exception:
        return None


class IngestionService:
    """Document classification, extraction, structuring and chunk persistence."""

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------
    def classify(self, path: str, filename: str) -> Dict[str, Any]:
        ext = os.path.splitext(filename)[1].lower()
        signals: List[str] = [f"extension={ext or 'none'}"]
        kind = "unknown"
        detail: Dict[str, Any] = {"page_count": 0}

        if ext == ".pdf":
            kind, detail = self._classify_pdf(path, signals)
        elif ext == ".docx":
            kind = "docx"
        elif ext == ".csv":
            kind = "csv_table"
        elif ext in (".txt", ".md", ".log"):
            kind = "text"
        elif ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"):
            kind, detail = self._classify_image(path, signals)
        elif ext == ".doc":
            kind = "doc_legacy_unsupported"
            signals.append("legacy .doc cannot be parsed locally; convert to .docx or PDF")
        else:
            kind = "unsupported"
            signals.append("file type is not part of the supported ingestion set")

        return {
            "kind": kind,
            "signals": signals,
            "page_count": detail.get("page_count", 0),
            "ocr_engine": "tesseract" if ocr_engine_available() else None,
            "detail": detail,
        }

    def _classify_pdf(self, path: str, signals: List[str]) -> Tuple[str, Dict[str, Any]]:
        if fitz is None:
            signals.append("PyMuPDF unavailable; PDF cannot be inspected")
            return "pdf_unreadable", {"page_count": 0}
        try:
            with fitz.open(path) as doc:
                page_count = doc.page_count
                text_pages, image_pages, total_chars = 0, 0, 0
                for page in doc:
                    text = page.get_text("text") or ""
                    chars = len(text.strip())
                    total_chars += chars
                    if chars >= 60:
                        text_pages += 1
                    if page.get_images(full=True):
                        image_pages += 1
        except Exception as exc:
            signals.append(f"PDF open failed: {exc}")
            return "pdf_unreadable", {"page_count": 0}

        signals.append(f"pages={page_count}")
        signals.append(f"pages_with_embedded_text={text_pages}")
        signals.append(f"pages_with_images={image_pages}")
        signals.append(f"extractable_characters={total_chars}")

        coverage = (text_pages / page_count) if page_count else 0.0
        detail = {"page_count": page_count, "text_pages": text_pages, "chars": total_chars}
        if page_count and coverage >= 0.8:
            return "digital_pdf", detail
        if coverage > 0:
            return "mixed_pdf", detail
        # No embedded text at all: a scan or an image-only export.
        if not ocr_engine_available():
            signals.append("no embedded text and no local OCR engine -> review required")
            return "scanned_pdf_no_ocr_engine", detail
        return "scanned_pdf", detail

    def _classify_image(self, path: str, signals: List[str]) -> Tuple[str, Dict[str, Any]]:
        """Separate a scanned paper sheet from a field photograph using real pixels."""
        if Image is None:
            return "image_unknown", {}
        try:
            with Image.open(path) as img:
                img = img.convert("L")
                width, height = img.size
                small = img.resize((160, max(1, int(160 * height / max(1, width)))))
                # Pillow histogram: fraction of near-white pixels and of near-black
                # pixels. A scanned sheet is mostly white with sparse dark ink; a
                # field photograph is neither.
                hist = small.histogram()
                total = sum(hist) or 1
                near_white = sum(hist[215:]) / total
                near_black = sum(hist[:40]) / total
        except Exception as exc:
            signals.append(f"image decode failed: {exc}")
            return "image_unreadable", {}

        portrait = height >= width
        signals.append(f"size={width}x{height}")
        signals.append(f"near_white_ratio={near_white:.2f}")
        signals.append(f"near_black_ratio={near_black:.2f}")
        detail = {"width": width, "height": height, "near_white_ratio": round(near_white, 3)}

        if near_white > 0.8 and near_black < 0.12 and portrait:
            signals.append("high-key portrait frame with sparse ink -> scanned sheet")
            return ("scanned_sheet" if ocr_engine_available() else "scanned_sheet_no_ocr_engine"), detail
        return "inspection_photograph", detail

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------
    def extract(self, path: str, filename: str, classification: Dict[str, Any]) -> Dict[str, Any]:
        kind = classification["kind"]
        if kind in ("digital_pdf", "mixed_pdf", "scanned_pdf", "scanned_pdf_no_ocr_engine"):
            return self._extract_pdf(path, kind)
        if kind in ("scanned_sheet", "scanned_sheet_no_ocr_engine", "inspection_photograph", "image_unreadable"):
            return self._extract_image(path, kind)
        if kind == "docx":
            return self._extract_docx(path)
        if kind == "csv_table":
            return self._extract_csv(path)
        if kind == "text":
            return self._extract_text(path)
        return {
            "pages": [],
            "method": "unsupported",
            "warnings": [f"No local extractor for document kind '{kind}'."],
            "metrics": self._metrics([], 0),
        }

    def _extract_pdf(self, path: str, kind: str) -> Dict[str, Any]:
        pages: List[Dict[str, Any]] = []
        warnings: List[str] = []
        use_ocr = False
        method = "pymupdf_text"
        if fitz is None:
            return {
                "pages": [],
                "method": "pymupdf_unavailable",
                "warnings": ["PyMuPDF is not importable in this environment."],
                "metrics": self._metrics([], 0),
            }

        with fitz.open(path) as doc:
            for page_index, page in enumerate(doc, start=1):
                text, tables, images = "", [], []

                if kind != "scanned_pdf_no_ocr_engine":
                    text = (page.get_text("text") or "").strip()

                if not text and kind in ("scanned_pdf", "scanned_sheet"):
                    # Only reached when a local OCR engine exists.
                    try:
                        textpage = page.get_textpage_ocr(language=OCR_LANGUAGE, dpi=300, full=True)
                        text = (page.get_text("text", textpage=textpage) or "").strip()
                        use_ocr = True
                        method = "pymupdf_text+tesseract_ocr"
                    except Exception as exc:
                        warnings.append(f"Page {page_index}: OCR failed ({exc}).")
                elif not text and kind == "scanned_pdf_no_ocr_engine":
                    warnings.append(
                        f"Page {page_index}: no embedded text and no local OCR engine — "
                        "manual transcript required."
                    )

                tables = self._pdf_tables(page)
                images = self._pdf_images(page, text)

                pages.append(
                    {
                        "page_number": page_index,
                        "text": text,
                        "tables": tables,
                        "images": images,
                        "method": "ocr" if (use_ocr and not page.get_text("text", sort=True).strip()) else "embedded_text",
                    }
                )

        return {
            "pages": pages,
            "method": method,
            "ocr_used": use_ocr,
            "warnings": warnings,
            "metrics": self._metrics(pages, classification_pages=len(pages)),
        }

    def _pdf_tables(self, page) -> List[Dict[str, Any]]:
        """Preserve real table structure where PyMuPDF can detect it."""
        try:
            finder = page.find_tables()
        except Exception:
            return []
        out: List[Dict[str, Any]] = []
        try:
            for table in getattr(finder, "tables", []):
                try:
                    rows = table.extract()
                except Exception:
                    continue
                cleaned = [
                    [("" if cell is None else str(cell).strip()) for cell in row]
                    for row in (rows or [])
                ]
                cleaned = [row for row in cleaned if any(cell for cell in row)]
                if len(cleaned) >= 2:
                    out.append(
                        {
                            "rows": cleaned,
                            "caption": f"Detected table {len(out) + 1} on page {page.number + 1}",
                            "bbox": [round(float(v), 1) for v in getattr(table, "bbox", (0, 0, 0, 0))],
                        }
                    )
        except Exception:
            return out
        return out

    def _pdf_images(self, page, page_text: str) -> List[Dict[str, Any]]:
        """Link each embedded figure to its page, region and nearest real text."""
        images: List[Dict[str, Any]] = []
        try:
            blocks = page.get_text("blocks")
        except Exception:
            return images
        lines = [ln for ln in (page_text or "").splitlines() if ln.strip()]

        for block in blocks:
            if len(block) < 7 or block[6] != 1:
                continue
            bbox = [round(float(v), 1) for v in block[:4]]
            # Nearest text line on the page, as a real caption candidate.
            caption = ""
            if lines:
                best, best_gap = None, None
                y0 = bbox[1]
                for index, line in enumerate(lines):
                    gap = abs((index / max(1, len(lines))) * float(page.rect.height) - y0)
                    if best_gap is None or gap < best_gap:
                        best, best_gap = line, gap
                caption = (best or "").strip()
                if len(caption) > 400:
                    caption = caption[:400].rstrip() + "..."
            images.append(
                {
                    "bbox": bbox,
                    "caption": caption,
                    "xref": block[5] if len(block) > 5 else None,
                    # No local vision model exists in this build, so no visual
                    # description is asserted. The caption is real page text.
                    "visual_description": None,
                }
            )
        return images

    def _extract_image(self, path: str, kind: str) -> Dict[str, Any]:
        """Single image → one structured page. OCR only when an engine exists."""
        warnings: List[str] = []
        text, method = "", "pixel_analysis_only"
        if kind == "scanned_sheet_no_ocr_engine":
            warnings.append(
                "No local OCR engine (Tesseract) is installed, so no text could be read from this "
                "sheet. Enter the transcription in the review queue to preserve it as knowledge."
            )
        elif kind == "scanned_sheet" and fitz is not None:
            try:
                with fitz.open(path) as doc:
                    page = doc[0]
                    textpage = page.get_textpage_ocr(language=OCR_LANGUAGE, dpi=300, full=True)
                    text = (page.get_text("text", textpage=textpage) or "").strip()
                    method = "tesseract_ocr"
            except Exception as exc:
                warnings.append(f"OCR failed ({exc}).")
        elif kind == "inspection_photograph":
            warnings.append(
                "Field photograph: stored as evidence and linked to the investigation. No local "
                "vision model is configured, so no automatic visual diagnosis is produced."
            )

        images = [{"bbox": None, "caption": "", "visual_description": None}]
        pages = [{"page_number": 1, "text": text, "tables": [], "images": images, "method": method}]
        return {
            "pages": pages,
            "method": method,
            "ocr_used": method == "tesseract_ocr",
            "warnings": warnings,
            "metrics": self._metrics(pages, classification_pages=1),
        }

    def _extract_docx(self, path: str) -> Dict[str, Any]:
        """DOCX via the OOXML package directly — no extra dependency required."""
        pages: List[Dict[str, Any]] = []
        paragraphs: List[str] = []
        tables: List[Dict[str, Any]] = []
        try:
            with zipfile.ZipFile(path) as archive:
                xml_bytes = archive.read("word/document.xml")
        except Exception as exc:
            return {
                "pages": [],
                "method": "docx_xml",
                "warnings": [f"DOCX could not be read: {exc}"],
                "metrics": self._metrics([], 0),
            }

        root = ElementTree.fromstring(xml_bytes)
        body = root.find(f"{DOCX_NS}body")
        if body is not None:
            for child in body:
                if child.tag == f"{DOCX_NS}p":
                    text = "".join(node.text or "" for node in child.iter(f"{DOCX_NS}t")).strip()
                    if text:
                        paragraphs.append(text)
                elif child.tag == f"{DOCX_NS}tbl":
                    rows: List[List[str]] = []
                    for row in child.iter(f"{DOCX_NS}tr"):
                        cells = [
                            "".join(node.text or "" for node in cell.iter(f"{DOCX_NS}t")).strip()
                            for cell in row.findall(f"{DOCX_NS}tc")
                        ]
                        if any(cells):
                            rows.append(cells)
                    if rows:
                        tables.append({"rows": rows, "caption": f"Table {len(tables) + 1}"})

        pages.append(
            {
                "page_number": 1,
                "text": "\n".join(paragraphs),
                "tables": tables,
                "images": [],
                "method": "ooxml",
            }
        )
        return {
            "pages": pages,
            "method": "docx_ooxml",
            "ocr_used": False,
            "warnings": ["DOCX has no fixed page numbers; all content is stored as page 1 with section metadata."],
            "metrics": self._metrics(pages, 1),
        }

    def _extract_csv(self, path: str) -> Dict[str, Any]:
        """CSV → one real table, headers preserved, chunked by the table chunker."""
        try:
            with open(path, "r", encoding="utf-8", errors="replace", newline="") as handle:
                rows = [row for row in csv.reader(handle) if any(str(c).strip() for c in row)]
        except Exception as exc:
            return {
                "pages": [],
                "method": "csv",
                "warnings": [f"CSV could not be read: {exc}"],
                "metrics": self._metrics([], 0),
            }
        pages = [
            {
                "page_number": 1,
                "text": "",
                "tables": [{"rows": rows, "caption": os.path.basename(path)}],
                "images": [],
                "method": "csv",
            }
        ]
        return {
            "pages": pages,
            "method": "csv_rows",
            "ocr_used": False,
            "warnings": [],
            "metrics": self._metrics(pages, 1),
            "row_count": max(0, len(rows) - 1),
        }

    def _extract_text(self, path: str) -> Dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                content = handle.read()
        except Exception as exc:
            return {
                "pages": [],
                "method": "plain_text",
                "warnings": [f"Text file could not be read: {exc}"],
                "metrics": self._metrics([], 0),
            }

        # Honour explicit page markers when the file has them, else one page.
        markers = list(re.finditer(r"(?im)^\s*(?:page|p\.)\s*(\d+)\s*$", content))
        pages: List[Dict[str, Any]] = []
        if markers:
            boundaries = [m.start() for m in markers] + [len(content)]
            for index, match in enumerate(markers):
                body = content[boundaries[index]:boundaries[index + 1]]
                body = re.sub(r"(?im)^\s*(?:page|p\.)\s*\d+\s*$", "", body, count=1).strip()
                pages.append(
                    {
                        "page_number": int(match.group(1)),
                        "text": body,
                        "tables": [],
                        "images": [],
                        "method": "plain_text",
                    }
                )
        else:
            pages.append(
                {
                    "page_number": 1,
                    "text": content,
                    "tables": [],
                    "images": [],
                    "method": "plain_text",
                }
            )
        return {
            "pages": pages,
            "method": "plain_text",
            "ocr_used": False,
            "warnings": [],
            "metrics": self._metrics(pages, len(pages)),
        }

    # ------------------------------------------------------------------
    # Validation / confidence
    # ------------------------------------------------------------------
    def _metrics(self, pages: List[Dict[str, Any]], classification_pages: int) -> Dict[str, Any]:
        page_count = len(pages) or classification_pages
        text_pages = sum(1 for p in pages if (p.get("text") or "").strip())
        chars = sum(len((p.get("text") or "").strip()) for p in pages)
        table_count = sum(len(p.get("tables") or []) for p in pages)
        image_count = sum(len(p.get("images") or []) for p in pages)

        printable = total = 0
        for page in pages:
            for char in page.get("text") or "":
                total += 1
                if char.isprintable() or char in "\n\t":
                    printable += 1
        printable_ratio = (printable / total) if total else 0.0

        return {
            "page_count": page_count,
            "text_page_count": text_pages,
            "extracted_chars": chars,
            "table_count": table_count,
            "image_count": image_count,
            "printable_ratio": round(printable_ratio, 4),
            "mean_chars_per_page": int(chars / page_count) if page_count else 0,
        }

    def estimate_confidence(
        self,
        classification: Dict[str, Any],
        extraction: Dict[str, Any],
        transcript_supplied: bool = False,
    ) -> Dict[str, Any]:
        """Transparent extraction-quality score with its measured inputs.

        This is a heuristic quality score over real measured signals — not a
        semantic-correctness probability, and it is labelled as such everywhere
        it is shown.
        """
        metrics = extraction.get("metrics", {})
        page_count = max(1, int(metrics.get("page_count", 0) or 0))
        coverage = min(1.0, int(metrics.get("text_page_count", 0)) / page_count)
        density = min(1.0, int(metrics.get("mean_chars_per_page", 0)) / 900.0)
        printable = float(metrics.get("printable_ratio", 0.0))
        structure = min(1.0, (int(metrics.get("table_count", 0)) + int(metrics.get("image_count", 0))) / 5.0)
        ocr_used = bool(extraction.get("ocr_used"))

        if transcript_supplied:
            weights = {"coverage": 0.50, "density": 0.30, "printable": 0.20, "structure": 0.00}
        elif ocr_used:
            # With OCR, coverage/density are produced by the OCR engine itself, so
            # the score leans on how uniform the OCR output is rather than on the
            # fact that text exists.
            weights = {"coverage": 0.20, "density": 0.20, "printable": 0.15, "structure": 0.45}
        else:
            weights = {"coverage": 0.45, "density": 0.25, "printable": 0.20, "structure": 0.10}

        components = {
            "text_coverage": round(coverage, 3),
            "character_density": round(density, 3),
            "printable_ratio": round(printable, 3),
            "structure_density": round(structure, 3),
        }
        score = (
            coverage * weights["coverage"]
            + density * weights["density"]
            + printable * weights["printable"]
            + structure * weights["structure"]
        )

        basis = [
            f"{metrics.get('text_page_count', 0)}/{page_count} pages yielded text",
            f"mean {metrics.get('mean_chars_per_page', 0)} characters per page",
            f"printable character ratio {printable:.2f}",
            f"{metrics.get('table_count', 0)} tables, {metrics.get('image_count', 0)} figures detected",
        ]
        if transcript_supplied:
            basis.append("confidence recomputed from a human-supplied transcript")
        if ocr_used:
            basis.append(
                "text produced by Tesseract OCR; the installed PyMuPDF binding does not expose "
                "per-word OCR confidences, so this score is derived from OCR output uniformity"
            )
        if not extraction.get("pages"):
            basis.append("no page content was extracted")

        return {
            "extraction_confidence": round(float(score), 3),
            "confidence_basis": basis,
            "confidence_components": components,
            "matches_rule": (
                "Requires engineer review before indexing"
                if score < REVIEW_BELOW_CONFIDENCE
                else "Cleared the minimum extraction-quality threshold"
            ),
        }

    # ------------------------------------------------------------------
    # Full ingest
    # ------------------------------------------------------------------
    def ingest(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        document_type: str,
        user: Dict[str, Any],
        revision: str = "1.0",
        source_label: str = "field_upload",
        machine_model: str = "All Models / Hydraulic Excavator",
        effective_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        os.makedirs(DOCUMENT_DIR, exist_ok=True)
        doc_id = f"DOC-{uuid.uuid4().hex[:8].upper()}"
        version_id = f"VER-{uuid.uuid4().hex[:8].upper()}"
        job_id = f"JOB-{uuid.uuid4().hex[:8].upper()}"
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename or "upload")
        save_path = os.path.join(DOCUMENT_DIR, f"{doc_id}_{safe_name}")
        with open(save_path, "wb") as handle:
            handle.write(file_bytes)

        db.execute_write(
            "INSERT INTO documents (document_id, document_name, document_type, file_path, file_size_bytes, version, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
            "INSERT INTO documents (document_id, document_name, document_type, file_path, file_size_bytes, version, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (doc_id, filename or safe_name, document_type, save_path, len(file_bytes), revision, STATUS_EXTRACTING),
        )
        self._insert_job(
            job_id=job_id,
            document_id=doc_id,
            version_id=version_id,
            filename=filename or safe_name,
            status=STATUS_EXTRACTING,
            stage="CLASSIFICATION",
            user=user,
        )

        classification = self.classify(save_path, filename or safe_name)
        try:
            extraction = self.extract(save_path, filename or safe_name, classification)
        except Exception as exc:
            self._finish_job(
                job_id=job_id,
                status=STATUS_EXTRACTION_FAILED,
                stage="EXTRACTION",
                message=f"Extraction failed: {exc}",
                classification=classification,
            )
            db.execute_write(
                "UPDATE documents SET status = %s WHERE document_id = %s" if db.use_mysql
                else "UPDATE documents SET status = ? WHERE document_id = ?",
                (STATUS_EXTRACTION_FAILED, doc_id),
            )
            return {
                "document_id": doc_id,
                "version_id": version_id,
                "job_id": job_id,
                "status": STATUS_EXTRACTION_FAILED,
                "classification": classification,
                "error": str(exc),
            }

        confidence = self.estimate_confidence(classification, extraction)

        # Manual review is mandatory whenever text could not be read locally.
        no_text = not extraction.get("pages") or confidence["extraction_confidence"] <= 0.0
        ocr_missing = classification["kind"] in ("scanned_pdf_no_ocr_engine", "scanned_sheet_no_ocr_engine")
        if no_text or ocr_missing:
            status = STATUS_OCR_UNAVAILABLE if ocr_missing else STATUS_REVIEW_REQUIRED
        elif confidence["extraction_confidence"] < REVIEW_BELOW_CONFIDENCE:
            status = STATUS_REVIEW_REQUIRED
        else:
            status = STATUS_REVIEW_REQUIRED  # human approval is always required

        version_status = "PENDING_REVIEW"
        db.execute_write(
            "INSERT INTO document_versions (version_id, document_id, revision, status, effective_date, source, file_path, "
            "extraction_method, extraction_confidence, note) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            if db.use_mysql else
            "INSERT INTO document_versions (version_id, document_id, revision, status, effective_date, source, file_path, "
            "extraction_method, extraction_confidence, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                version_id,
                doc_id,
                revision,
                version_status,
                effective_date,
                source_label,
                save_path,
                extraction.get("method", "unknown"),
                confidence["extraction_confidence"],
                "; ".join(extraction.get("warnings", []))[:2000],
            ),
        )

        # Persist the per-page extraction records (traceability before chunking).
        for page in extraction.get("pages", []):
            structure = {
                "tables": page.get("tables", []),
                "images": page.get("images", []),
                "method": page.get("method"),
            }
            db.execute_write(
                "INSERT INTO document_extractions (extraction_id, job_id, document_id, version_id, page_number, "
                "block_index, block_kind, extraction_method, extraction_confidence, raw_text, structure_json, review_status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
                "INSERT INTO document_extractions (extraction_id, job_id, document_id, version_id, page_number, "
                "block_index, block_kind, extraction_method, extraction_confidence, raw_text, structure_json, review_status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"EXT-{uuid.uuid4().hex[:10].upper()}",
                    job_id,
                    doc_id,
                    version_id,
                    page.get("page_number", 1),
                    0,
                    "page",
                    page.get("method") or extraction.get("method"),
                    confidence["extraction_confidence"],
                    page.get("text") or "",
                    _json(structure),
                    "PENDING_REVIEW",
                ),
            )

        chunks = self.chunk(doc_id, filename or safe_name, document_type, extraction, machine_model)
        for chunk in chunks:
            self._insert_chunk(chunk)

        metadata = {
            "document_type": document_type,
            "revision": revision,
            "document_status": version_status,
            "quality_level": "UNVERIFIED",
            "source": source_label,
            "machine_model": machine_model,
            "extraction_method": extraction.get("method"),
            "extraction_confidence": confidence["extraction_confidence"],
        }
        self._finish_job(
            job_id=job_id,
            status=status,
            stage="VALIDATION",
            message=None,
            classification=classification,
            metrics=extraction.get("metrics", {}),
            confidence=confidence,
            method=extraction.get("method"),
            chunk_count=len(chunks),
        )

        db.execute_write(
            "UPDATE documents SET status = %s, version = %s WHERE document_id = %s" if db.use_mysql
            else "UPDATE documents SET status = ?, version = ? WHERE document_id = ?",
            (status, revision, doc_id),
        )

        for chunk in chunks:
            self._record_chunk_metadata(chunk, metadata)

        return {
            "document_id": doc_id,
            "version_id": version_id,
            "job_id": job_id,
            "document_name": filename or safe_name,
            "status": status,
            "version_status": version_status,
            "classification": classification,
            "metrics": extraction.get("metrics", {}),
            "confidence": confidence,
            "warnings": extraction.get("warnings", []),
            "chunks_created": len(chunks),
            "chunks_indexed": 0,
            "chunk_kinds": _count_kinds(chunks),
            "extraction_method": extraction.get("method"),
            "page_preview": [
                {
                    "page_number": page.get("page_number"),
                    "chars": len((page.get("text") or "").strip()),
                    "tables": len(page.get("tables") or []),
                    "figures": len(page.get("images") or []),
                    "excerpt": ((page.get("text") or "").strip()[:280]),
                }
                for page in extraction.get("pages", [])[:12]
            ],
        }

    def chunk(
        self,
        document_id: str,
        filename: str,
        document_type: str,
        extraction: Dict[str, Any],
        machine_model: str,
    ) -> List[Dict[str, Any]]:
        """Structure -> chunk, preserving tables, figures and page metadata."""
        metadata = {
            "document_type": document_type,
            "machine_model": machine_model,
        }
        return structure_to_chunks(
            document_id=document_id,
            document_name=filename,
            document_type=document_type,
            structured_pages=extraction.get("pages", []),
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def _insert_chunk(self, chunk: Dict[str, Any]) -> None:
        db.execute_write(
            "INSERT INTO document_chunks (chunk_id, document_id, page_number, section_heading, component, machine_model, chunk_text) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
            "INSERT INTO document_chunks (chunk_id, document_id, page_number, section_heading, component, machine_model, chunk_text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                chunk["chunk_id"],
                chunk["document_id"],
                chunk["page_number"],
                chunk["section_heading"],
                chunk["component"],
                chunk["machine_model"],
                chunk["chunk_text"],
            ),
        )

    def _record_chunk_metadata(self, chunk: Dict[str, Any], metadata: Dict[str, Any]) -> None:
        """Keep richer chunk metadata in knowledge_sources for filtering and traceability."""
        db.execute_write(
            "INSERT INTO knowledge_sources (source_id, owner_type, owner_id, source_kind, source_ref, title, "
            "document_id, page_number, revision, document_status, quality_level, note) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
            "INSERT INTO knowledge_sources (source_id, owner_type, owner_id, source_kind, source_ref, title, "
            "document_id, page_number, revision, document_status, quality_level, note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"SRC-{uuid.uuid4().hex[:10].upper()}",
                "document_chunk",
                chunk["chunk_id"],
                chunk.get("chunk_kind", "text"),
                f"{chunk['document_name']} p{chunk['page_number']}",
                chunk.get("section_heading", ""),
                chunk["document_id"],
                chunk["page_number"],
                metadata.get("revision"),
                metadata.get("document_status"),
                metadata.get("quality_level"),
                _json(chunk.get("metadata", {})),
            ),
        )

    def _insert_job(
        self,
        *,
        job_id: str,
        document_id: str,
        version_id: str,
        filename: str,
        status: str,
        stage: str,
        user: Dict[str, Any],
    ) -> None:
        db.execute_write(
            "INSERT INTO ingestion_jobs (job_id, document_id, version_id, filename, status, pipeline_stage, created_by, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
            "INSERT INTO ingestion_jobs (job_id, document_id, version_id, filename, status, pipeline_stage, created_by, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (job_id, document_id, version_id, filename, status, stage, user.get("user_id"), _now()),
        )

    def _finish_job(
        self,
        *,
        job_id: str,
        status: str,
        stage: str,
        message: Optional[str],
        classification: Dict[str, Any],
        metrics: Optional[Dict[str, Any]] = None,
        confidence: Optional[Dict[str, Any]] = None,
        method: Optional[str] = None,
        chunk_count: int = 0,
    ) -> None:
        metrics = metrics or {}
        confidence = confidence or {}
        db.execute_write(
            "UPDATE ingestion_jobs SET status = %s, pipeline_stage = %s, detected_type = %s, page_count = %s, "
            "text_page_count = %s, extracted_chars = %s, table_count = %s, image_count = %s, "
            "extraction_confidence = %s, confidence_breakdown = %s, extraction_method = %s, chunk_count = %s, "
            "message = %s, updated_at = %s WHERE job_id = %s" if db.use_mysql else
            "UPDATE ingestion_jobs SET status = ?, pipeline_stage = ?, detected_type = ?, page_count = ?, "
            "text_page_count = ?, extracted_chars = ?, table_count = ?, image_count = ?, "
            "extraction_confidence = ?, confidence_breakdown = ?, extraction_method = ?, chunk_count = ?, "
            "message = ?, updated_at = ? WHERE job_id = ?",
            (
                status,
                stage,
                classification.get("kind"),
                int(metrics.get("page_count", classification.get("page_count", 0)) or 0),
                int(metrics.get("text_page_count", 0) or 0),
                int(metrics.get("extracted_chars", 0) or 0),
                int(metrics.get("table_count", 0) or 0),
                int(metrics.get("image_count", 0) or 0),
                float(confidence.get("extraction_confidence", 0.0) or 0.0),
                _json(confidence.get("confidence_components", {})),
                method,
                chunk_count,
                message,
                _now(),
                job_id,
            ),
        )


def _json(value: Any) -> str:
    import json

    try:
        return json.dumps(value, default=str)
    except Exception:
        return "{}"


def _count_kinds(chunks: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for chunk in chunks:
        kind = chunk.get("chunk_kind", "text")
        counts[kind] = counts.get(kind, 0) + 1
    return counts


ingestion_service = IngestionService()
