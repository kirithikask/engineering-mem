"""
Multimodal knowledge chunking.

The original plain-text chunker (``text_chunker.py``) is untouched: it is still
used for the text-only paths. This module handles the richer media the ingestion
pipeline can now produce, and it keeps structure instead of flattening it:

* PDF page  -> section -> paragraph -> chunk
* table     -> headers preserved, one row per line, table kept as its own chunk
* diagram / inspection photograph -> a chunk that carries the page, the
  component, the surrounding text as caption and the extraction provenance,
  so it stays retrievable and traceable back to the drawing it came from.

Every chunk returned here is shaped for ``document_chunks`` (the relational
columns) plus a metadata block that the indexing layer writes to
``embedding_records`` so retrieval can filter on component, subsystem, revision
and document status.
"""

import re
import uuid
from typing import Any, Dict, List, Optional

# Engineering component vocabulary used for metadata tagging. Terms are matched
# against section headings, table titles and surrounding page text.
COMPONENT_KEYWORDS = {
    "hydraulic pump": ("pump", "pumps"),
    "main control valve": ("control valve", "main valve", "spool"),
    "hydraulic filter": ("filter", "filtration", "strainer"),
    "oil cooler": ("cooler", "oil cooler", "radiator", "heat exchanger"),
    "accumulator": ("accumulator", "gas charge", "precharge"),
    "boom cylinder": ("boom cylinder", "boom ram"),
    "arm cylinder": ("arm cylinder", "arm ram"),
    "bucket cylinder": ("bucket cylinder", "bucket ram"),
    "pilot system": ("pilot", "pilot pressure", "pilot valve", "joystick"),
    "swing motor": ("swing motor", "swing", "slew"),
    "travel motor": ("travel motor", "travel", "track motor"),
    "hydraulic line": ("hose", "line", "pipe", "tube", "fitting"),
    "hydraulic oil": ("hydraulic oil", "reservoir", "tank", "fluid"),
    "relief valve": ("relief valve", "main relief", "pressure relief"),
}

SUBSYSTEM_KEYWORDS = {
    "Hydraulic System": ("hydraulic", "oil", "pump", "valve", "cylinder", "pressure"),
    "Cooling System": ("cooling", "cooler", "temperature", "thermostat", "fan"),
    "Electrical System": ("electrical", "wiring", "sensor", "solenoid", "battery"),
    "Engine": ("engine", "diesel", "injector", "turbo"),
    "Undercarriage": ("track", "undercarriage", "roller", "sprocket", "idler"),
}

# Headings that introduce a safety-relevant passage. Used to tag chunks so the
# UI can raise safety information before a physical inspection.
SAFETY_HEADING_TERMS = (
    "safety", "warning", "caution", "danger", "lockout", "tagout",
    "personal protective", "ppe", "before servicing", "relieve pressure",
)


def detect_component(*texts: Optional[str]) -> str:
    """Best-effort component tag from heading/body text, or a neutral default."""
    blob = " ".join((t or "").lower() for t in texts)
    for canonical, terms in COMPONENT_KEYWORDS.items():
        if any(term in blob for term in terms):
            return canonical
    return "Hydraulic System"


def detect_subsystem(*texts: Optional[str]) -> str:
    blob = " ".join((t or "").lower() for t in texts)
    for canonical, terms in SUBSYSTEM_KEYWORDS.items():
        if any(term in blob for term in terms):
            return canonical
    return "Hydraulic System"


def is_heading(line: str) -> bool:
    """Section heading test: short, non-sentence, and title/upper case or numbered."""
    stripped = line.strip()
    if not stripped or len(stripped) > 70:
        return False
    if stripped.endswith((".", ":", ";")) and not re.match(r"^\d+(\.\d+)*\s", stripped):
        return False
    words = stripped.split()
    if len(words) > 9:
        return False
    letters = [c for c in stripped if c.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    return upper_ratio >= 0.7 or bool(re.match(r"^\d+(\.\d+)*(\s|\.)", stripped))


def _chunk_id() -> str:
    return f"CHK-{uuid.uuid4().hex[:8].upper()}"


def _split_paragraphs(text: str) -> List[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) <= 1:
        paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    return paragraphs


def _window(words: List[str], size: int, overlap: int) -> List[List[str]]:
    if not words:
        return []
    if len(words) <= size:
        return [words]
    out, start = [], 0
    while start < len(words):
        out.append(words[start:start + size])
        if start + size >= len(words):
            break
        start += size - overlap
    return out


def chunk_page_text(
    *,
    document_id: str,
    document_name: str,
    document_type: str,
    page_number: int,
    text: str,
    metadata: Dict[str, Any],
    chunk_size_words: int = 220,
    overlap_words: int = 40,
) -> List[Dict[str, Any]]:
    """Page -> section -> paragraph -> chunk, with section metadata preserved."""
    chunks: List[Dict[str, Any]] = []
    section = "General"
    buffer: List[str] = []

    def flush() -> None:
        nonlocal buffer
        if not buffer:
            return
        for window in _window(buffer, chunk_size_words, overlap_words):
            body = " ".join(window).strip()
            if not body:
                continue
            chunks.append(
                {
                    "chunk_id": _chunk_id(),
                    "document_id": document_id,
                    "document_name": document_name,
                    "document_type": document_type,
                    "page_number": page_number,
                    "section_heading": section[:250],
                    "component": detect_component(section, body),
                    "machine_model": metadata.get("machine_model", "All Models / Hydraulic Excavator"),
                    "chunk_kind": "text",
                    "chunk_text": body,
                    "metadata": {
                        **metadata,
                        "page_number": page_number,
                        "section_heading": section[:250],
                        "subsystem": detect_subsystem(section, body),
                        "safety_related": any(t in section.lower() for t in SAFETY_HEADING_TERMS),
                    },
                }
            )
        buffer = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if is_heading(line):
            flush()
            section = line
            continue
        buffer.append(line)

    flush()
    return chunks


def chunk_table(
    *,
    document_id: str,
    document_name: str,
    document_type: str,
    page_number: int,
    table_index: int,
    rows: List[List[Any]],
    caption: str,
    metadata: Dict[str, Any],
    max_rows_per_chunk: int = 24,
    repeat_header: bool = True,
) -> List[Dict[str, Any]]:
    """Table -> kept as a table: header row preserved on every chunk.""" 
    if not rows:
        return []

    header = [str(c or "").strip() for c in rows[0]]
    body_rows = rows[1:] if len(rows) > 1 else rows
    chunks: List[Dict[str, Any]] = []

    for start in range(0, len(body_rows), max_rows_per_chunk):
        window = body_rows[start:start + max_rows_per_chunk]
        lines = []
        if repeat_header and header and header != [""]:
            lines.append(" | ".join(header))
            lines.append("-" * min(60, len(lines[0])))
        for row in window:
            lines.append(" | ".join(str(c if c is not None else "").strip() for c in row))
        body = "\n".join(lines)
        if not body.strip():
            continue
        section = caption or f"Table {table_index + 1}"
        chunks.append(
            {
                "chunk_id": _chunk_id(),
                "document_id": document_id,
                "document_name": document_name,
                "document_type": document_type,
                "page_number": page_number,
                "section_heading": section[:250],
                "component": detect_component(section, " ".join(header)),
                "machine_model": metadata.get("machine_model", "All Models / Hydraulic Excavator"),
                "chunk_kind": "table",
                "chunk_text": f"[TABLE page {page_number} · {section}]\n{body}",
                "metadata": {
                    **metadata,
                    "page_number": page_number,
                    "section_heading": section[:250],
                    "table_index": table_index,
                    "table_headers": header,
                    "row_count": len(window),
                    "row_offset": start,
                    "subsystem": detect_subsystem(section, " ".join(header)),
                },
            }
        )
    return chunks


def chunk_visual(
    *,
    document_id: str,
    document_name: str,
    document_type: str,
    page_number: int,
    image_index: int,
    caption: str,
    bbox: Optional[List[float]],
    metadata: Dict[str, Any],
    visual_description: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Diagram / photograph -> retrievable chunk linked to page, component and caption.

    ``visual_description`` is only populated when a description source actually
    exists (an OCR'd figure caption, the text surrounding the figure, or a
    technician-supplied caption). No vision model is assumed, so the reader can
    always see where the caption came from.
    """
    section = metadata.get("section_heading") or "Figure"
    caption_text = (caption or "").strip()
    header = f"[DIAGRAM page {page_number} · {section}]"
    body_lines = [header]
    if visual_description:
        body_lines.append(f"Description: {visual_description}")
    if caption_text:
        body_lines.append(f"Caption / surrounding text: {caption_text}")
    if bbox:
        body_lines.append("Region: " + ", ".join(f"{v:.1f}" for v in bbox))
    if not visual_description and not caption_text:
        body_lines.append(
            "Description: not available — no local vision model is configured, "
            "and this figure has no extractable caption text."
        )

    return [
        {
            "chunk_id": _chunk_id(),
            "document_id": document_id,
            "document_name": document_name,
            "document_type": document_type,
            "page_number": page_number,
            "section_heading": section[:250],
            "component": detect_component(section, caption_text),
            "machine_model": metadata.get("machine_model", "All Models / Hydraulic Excavator"),
            "chunk_kind": "figure",
            "chunk_text": "\n".join(body_lines),
            "metadata": {
                **metadata,
                "page_number": page_number,
                "section_heading": section[:250],
                "image_index": image_index,
                "visual_description_source": "caption_text" if caption_text else "none",
                "subsystem": detect_subsystem(section, caption_text),
            },
        }
    ]


def structure_to_chunks(
    *,
    document_id: str,
    document_name: str,
    document_type: str,
    structured_pages: List[Dict[str, Any]],
    metadata: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Walk the structured extraction output of any document kind into chunks."""
    chunks: List[Dict[str, Any]] = []
    for page in structured_pages:
        page_number = int(page.get("page_number", 1))
        page_meta = {**metadata, "section_heading": "General"}

        if page.get("text"):
            chunks.extend(
                chunk_page_text(
                    document_id=document_id,
                    document_name=document_name,
                    document_type=document_type,
                    page_number=page_number,
                    text=page["text"],
                    metadata=page_meta,
                )
            )

        for t_idx, table in enumerate(page.get("tables", []) or []):
            chunks.extend(
                chunk_table(
                    document_id=document_id,
                    document_name=document_name,
                    document_type=document_type,
                    page_number=page_number,
                    table_index=t_idx,
                    rows=table.get("rows", []),
                    caption=table.get("caption", ""),
                    metadata=page_meta,
                )
            )

        for i_idx, image in enumerate(page.get("images", []) or []):
            chunks.extend(
                chunk_visual(
                    document_id=document_id,
                    document_name=document_name,
                    document_type=document_type,
                    page_number=page_number,
                    image_index=i_idx,
                    caption=image.get("caption", ""),
                    bbox=image.get("bbox"),
                    metadata=page_meta,
                    visual_description=image.get("visual_description"),
                )
            )
    return chunks
