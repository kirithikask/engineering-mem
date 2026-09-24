"""
Ingestion API (brief §15, §16, §25).

Every response is built from what the ingestion pipeline actually measured: page
counts, table and figure counts, chunk kinds, the confidence score and its
breakdown, and the review decision. Nothing here estimates or rounds up.
"""

import json
import os
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from backend.app.api.auth import get_current_user, require_role
from backend.app.db.mysql_client import db
from backend.app.services.audit_service import audit_service
from backend.app.services.ingestion_service import (
    _ocr_engine_version,
    REVIEW_BELOW_CONFIDENCE,
    ingestion_service,
    ocr_engine_available,
)
from backend.app.services.retrieval_service import retrieval_service

router = APIRouter(prefix="/api/ingestion", tags=["Document Ingestion"])

MAX_UPLOAD_BYTES = int(os.getenv("EM_MAX_UPLOAD_BYTES", str(64 * 1024 * 1024)))


def _job(row: Dict[str, Any]) -> Dict[str, Any]:
    breakdown = row.get("confidence_breakdown")
    if breakdown:
        try:
            row["confidence_breakdown"] = json.loads(breakdown)
        except Exception:
            pass
    return row


@router.get("/capabilities")
def capabilities():
    """What this host can actually do — the UI must not promise more."""
    return {
        "ocr_engine": "tesseract" if ocr_engine_available() else None,
        "ocr_available": ocr_engine_available(),
        "ocr_engine_version": _ocr_engine_version(),
        "ocr_note": (
            "Local OCR is available."
            if ocr_engine_available()
            else "No local OCR engine (Tesseract) is installed on this host: scanned and handwritten material is "
                 "accepted and stored, then routed to the review queue for a human transcript. No text is guessed."
        ),
        "supported_types": ["pdf", "docx", "txt", "md", "log", "csv", "png", "jpg", "jpeg", "tif", "tiff", "bmp"],
        "vision_model": None,
        "vision_note": "No local vision model is configured; document figures are linked to page text and metadata, "
                       "never described by a model.",
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "review_threshold": REVIEW_BELOW_CONFIDENCE,
        "confidence_kind": "heuristic extraction-quality score over measured signals (not a semantic accuracy claim)",
    }


@router.post("/upload")
async def upload_intelligent(
    file: UploadFile = File(...),
    document_type: str = Form("service_manual"),
    revision: str = Form("1.0"),
    source: str = Form("field_upload"),
    machine_model: str = Form("All Models / Hydraulic Excavator"),
    user: dict = Depends(get_current_user),
):
    """Full multimodal pipeline: classify → extract → structure → validate → chunk → persist."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds the {MAX_UPLOAD_BYTES} byte limit.")

    result = ingestion_service.ingest(
        file_bytes=content,
        filename=file.filename or "uploaded_document",
        document_type=document_type,
        user=user,
        revision=revision,
        source_label=source,
        machine_model=machine_model,
    )
    audit_service.record(
        user=user,
        action="DOCUMENT_INGESTED",
        entity_type="document",
        entity_id=result.get("document_id"),
        detail={
            "filename": file.filename,
            "kind": (result.get("classification") or {}).get("kind"),
            "status": result.get("status"),
            "confidence": (result.get("confidence") or {}).get("extraction_confidence"),
            "chunks": result.get("chunks_created"),
            "bytes": len(content),
        },
    )
    return result


@router.get("/jobs")
def list_jobs(limit: int = 50):
    rows = db.execute_query(
        "SELECT job_id, document_id, version_id, filename, status, detected_type, pipeline_stage, page_count, "
        "text_page_count, extracted_chars, table_count, image_count, extraction_confidence, confidence_breakdown, "
        "extraction_method, chunk_count, vector_count, message, created_by, created_at, updated_at "
        f"FROM ingestion_jobs ORDER BY created_at DESC LIMIT {int(limit)}"
    )
    return {
        "jobs": [_job(row) for row in rows],
        "pipeline": [
            "UPLOAD",
            "CLASSIFICATION",
            "EXTRACTION",
            "STRUCTURING",
            "VALIDATION",
            "CHUNKING",
            "METADATA",
            "MYSQL",
            "APPROVAL",
            "BGE",
            "FAISS",
        ],
    }


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    placeholder = "%s" if db.use_mysql else "?"
    rows = db.execute_query(f"SELECT * FROM ingestion_jobs WHERE job_id = {placeholder}", (job_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Ingestion job not found.")
    extractions = db.execute_query(
        "SELECT extraction_id, page_number, block_kind, extraction_method, extraction_confidence, review_status, "
        f"LENGTH(raw_text) AS chars FROM document_extractions WHERE job_id = {placeholder} ORDER BY page_number ASC",
        (job_id,),
    )
    return {"job": _job(rows[0]), "pages": extractions}


@router.get("/queue")
def review_queue(limit: int = 50, user: dict = Depends(require_role("ENGINEER", "ADMIN"))):
    """Extractions that need a human decision before they can be indexed."""
    rows = db.execute_query(
        "SELECT d.document_id, d.document_name, d.document_type, d.status, d.file_size_bytes, d.created_at, "
        "v.version_id, v.revision, v.status AS version_status, v.extraction_method, v.extraction_confidence, v.note, "
        "(SELECT COUNT(*) FROM document_chunks c WHERE c.document_id = d.document_id) AS chunk_count, "
        "(SELECT COUNT(*) FROM document_extractions e WHERE e.document_id = d.document_id) AS page_count "
        "FROM documents d LEFT JOIN document_versions v ON v.document_id = d.document_id "
        "WHERE d.status IN ('REVIEW_REQUIRED', 'OCR_ENGINE_UNAVAILABLE', 'EXTRACTING', 'UPLOADED', 'EXTRACTION_FAILED') "
        f"ORDER BY d.created_at DESC LIMIT {int(limit)}"
    )
    return {
        "queue": rows,
        "count": len(rows),
        "ocr_available": ocr_engine_available(),
        "note": (
            "Items appear here when extraction quality is below the review threshold, when the document could not be "
            "read locally, or until an engineer approves it. Nothing is embedded into the vector index before approval."
        ),
        "refresh_with": "GET /api/retrieval/search once an item is approved",
    }


@router.get("/documents/{document_id}/extractions")
def document_extractions(document_id: str):
    placeholder = "%s" if db.use_mysql else "?"
    rows = db.execute_query(
        "SELECT extraction_id, page_number, block_index, block_kind, extraction_method, extraction_confidence, "
        "raw_text, structure_json, review_status, reviewer_id, reviewed_at FROM document_extractions "
        f"WHERE document_id = {placeholder} ORDER BY page_number ASC, block_index ASC",
        (document_id,),
    )
    for row in rows:
        try:
            row["structure"] = json.loads(row.pop("structure_json") or "{}")
        except Exception:
            row["structure"] = {}
    return {"document_id": document_id, "extractions": rows}


@router.put("/extractions/{extraction_id}")
def update_extraction(extraction_id: str, payload: Dict[str, Any], user: dict = Depends(require_role("ENGINEER", "ADMIN"))):
    """Human transcript / correction of an extraction (the review-queue Edit action)."""
    placeholder = "%s" if db.use_mysql else "?"
    rows = db.execute_query(
        f"SELECT extraction_id, document_id, version_id, page_number FROM document_extractions WHERE extraction_id = {placeholder}",
        (extraction_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Extraction record not found.")
    row = rows[0]
    text = payload.get("raw_text")
    if not isinstance(text, str):
        raise HTTPException(status_code=400, detail="raw_text must be a string.")

    db.execute_write(
        f"UPDATE document_extractions SET raw_text = {placeholder}, extraction_method = {placeholder}, "
        f"extraction_confidence = {placeholder}, review_status = 'EDITED', reviewer_id = {placeholder} "
        f"WHERE extraction_id = {placeholder}",
        (
            text,
            "manual_transcript",
            float(payload.get("extraction_confidence") or 0.0),
            user.get("user_id"),
            extraction_id,
        ),
    )
    audit_service.record(
        user=user,
        action="EXTRACTION_EDITED",
        entity_type="document_extraction",
        entity_id=extraction_id,
        detail={"document_id": row["document_id"], "page": row["page_number"], "chars": len(text)},
    )
    return {
        "status": "ok",
        "extraction_id": extraction_id,
        "review_status": "EDITED",
        "message": "Transcript stored. Approve the document to rebuild its chunks with the corrected text.",
    }


@router.post("/documents/{document_id}/rebuild-chunks")
def rebuild_chunks(document_id: str, user: dict = Depends(require_role("ENGINEER", "ADMIN"))):
    """Re-chunk a document from its (possibly human-corrected) extraction records."""
    placeholder = "%s" if db.use_mysql else "?"
    docs = db.execute_query(f"SELECT * FROM documents WHERE document_id = {placeholder}", (document_id,))
    if not docs:
        raise HTTPException(status_code=404, detail="Document not found.")
    document = docs[0]
    pages = db.execute_query(
        f"SELECT page_number, raw_text, structure_json FROM document_extractions WHERE document_id = {placeholder} "
        "ORDER BY page_number ASC",
        (document_id,),
    )
    if not pages:
        raise HTTPException(status_code=400, detail="No extraction records exist for this document.")

    structured = []
    for page in pages:
        try:
            structure = json.loads(page.get("structure_json") or "{}")
        except Exception:
            structure = {}
        structured.append(
            {
                "page_number": page["page_number"],
                "text": page.get("raw_text") or "",
                "tables": structure.get("tables", []),
                "images": structure.get("images", []),
            }
        )

    chunks = ingestion_service.chunk(
        document_id,
        document["document_name"],
        document["document_type"],
        {"pages": structured},
        "All Models / Hydraulic Excavator",
    )
    db.execute_write(
        f"DELETE FROM document_chunks WHERE document_id = {placeholder}", (document_id,)
    )
    for chunk in chunks:
        ingestion_service._insert_chunk(chunk)
        ingestion_service._record_chunk_metadata(
            chunk,
            {
                "revision": document.get("version"),
                "document_status": "PENDING_REVIEW",
                "quality_level": "UNVERIFIED",
            },
        )
    audit_service.record(
        user=user,
        action="DOCUMENT_REBUILT_CHUNKS",
        entity_type="document",
        entity_id=document_id,
        detail={"chunks": len(chunks)},
    )
    return {"status": "ok", "document_id": document_id, "chunks_created": len(chunks)}


@router.get("/search-test")
def ingestion_search_test(query: str, user: dict = Depends(require_role("ENGINEER", "ADMIN"))):
    """Confirm that a newly approved document is retrievable (acceptance test 1/10)."""
    return retrieval_service.search(query, top_k=5, user=user)
