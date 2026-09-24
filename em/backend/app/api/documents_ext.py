"""
Document versioning, approval and review endpoints (brief §6, §16, §25).

Registered under the same ``/api/documents`` prefix as the original document
router. No existing path is redefined: only new sub-paths are added, so the
original ``GET /api/documents``, ``GET /api/documents/{id}`` and
``POST /api/documents/upload`` keep their exact behaviour.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.auth import get_current_user, require_role
from backend.app.db.mysql_client import db
from backend.app.services.audit_service import audit_service
from backend.app.services.knowledge_service import DOCUMENT_STATUSES, knowledge_service

router = APIRouter(prefix="/api/documents", tags=["Engineering Documents"])


@router.get("/{document_id}/versions")
def get_versions(document_id: str):
    result = knowledge_service.list_versions(document_id)
    if not result.get("document"):
        raise HTTPException(status_code=404, detail="Document not found")
    result["statuses"] = DOCUMENT_STATUSES
    return result


@router.post("/{document_id}/approve")
def approve_document(
    document_id: str,
    payload: Optional[Dict[str, Any]] = None,
    user: dict = Depends(require_role("ENGINEER", "ADMIN")),
):
    """Approve a revision, supersede older revisions and embed its chunks into FAISS."""
    payload = payload or {}
    result = knowledge_service.approve_document(
        document_id=document_id,
        version_id=payload.get("version_id"),
        user=user,
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("detail"))
    audit_service.record(
        user=user,
        action="DOCUMENT_APPROVED",
        entity_type="document",
        entity_id=document_id,
        detail={
            "revision": result.get("revision"),
            "superseded": result.get("superseded"),
            "indexed": (result.get("index") or {}).get("added"),
        },
    )
    result["message"] = (
        "Revision approved as CURRENT. "
        + (
            f"Embedded {result['index'].get('added')} passage(s) into the vector index. "
            if (result.get("index") or {}).get("added")
            else "Passages were already present in the vector index. "
        )
        + (
            f"{len(result.get('superseded') or [])} older revision(s) marked SUPERSEDED."
            if result.get("superseded")
            else "No older revision required superseding."
        )
    )
    return result


@router.post("/{document_id}/reject")
def reject_document(
    document_id: str,
    payload: Optional[Dict[str, Any]] = None,
    user: dict = Depends(require_role("ENGINEER", "ADMIN")),
):
    payload = payload or {}
    result = knowledge_service.reject_document(
        document_id=document_id, user=user, comment=payload.get("comment")
    )
    audit_service.record(
        user=user,
        action="DOCUMENT_REJECTED",
        entity_type="document",
        entity_id=document_id,
        detail={"comment": payload.get("comment")},
    )
    result["message"] = "Extraction rejected. The original file and extraction records are retained for audit."
    return result


@router.get("/{document_id}/review-status")
def review_status(document_id: str):
    placeholder = "%s" if db.use_mysql else "?"
    docs = db.execute_query(f"SELECT * FROM documents WHERE document_id = {placeholder}", (document_id,))
    if not docs:
        raise HTTPException(status_code=404, detail="Document not found")
    document = docs[0]
    versions = db.execute_query(
        "SELECT version_id, revision, status, extraction_confidence, approved_by, approved_at, superseded_date "
        f"FROM document_versions WHERE document_id = {placeholder} ORDER BY created_at DESC",
        (document_id,),
    )
    extraction_rows = db.execute_query(
        "SELECT review_status, COUNT(*) AS n FROM document_extractions "
        f"WHERE document_id = {placeholder} GROUP BY review_status",
        (document_id,),
    )
    indexed = db.execute_query(
        "SELECT COUNT(*) AS n FROM embedding_records WHERE owner_type = 'chunk' AND owner_id IN "
        f"(SELECT chunk_id FROM document_chunks WHERE document_id = {placeholder})",
        (document_id,),
    )
    return {
        "document": document,
        "versions": versions,
        "extraction_review": [
            {"review_status": row["review_status"], "count": int(row["n"])} for row in extraction_rows
        ],
        "indexed_vectors": int(indexed[0]["n"]) if indexed else 0,
        "stage": (
            "INDEXED"
            if (indexed and int(indexed[0]["n"]) > 0)
            else "APPROVED" if document.get("status") == "APPROVED"
            else "REVIEW_REQUIRED"
        ),
    }
