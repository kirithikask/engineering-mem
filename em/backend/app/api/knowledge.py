"""
Knowledge Center and review queue API (brief §4, §6, §14, §16, §25).

Review actions are role-gated: only ENGINEER and ADMIN can turn a technician-submitted
draft into approved engineering knowledge, and only through ``POST /api/knowledge/{id}/review``.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from backend.app.api.auth import get_current_user, require_role
from backend.app.db.mysql_client import db
from backend.app.services.audit_service import audit_service
from backend.app.services.index_service import index_service
from backend.app.services.knowledge_service import QUALITY_LEVELS, knowledge_service
from backend.app.services.retrieval_service import (
    DOC_STATUS_PRIORITY,
    QUALITY_WEIGHTS,
    retrieval_service,
)

router = APIRouter(prefix="/api/knowledge", tags=["Engineering Knowledge"])


@router.get("/overview")
def overview():
    data = knowledge_service.overview()
    data["vector_index"] = {
        "vectors": int(index_service.stats()["vectors"]),
        "dimension": int(index_service.stats()["dimension"]),
        "model": index_service.stats()["embedding_model"],
    }
    data["retrieval_latency"] = retrieval_service.latency_summary()
    data["quality_levels"] = QUALITY_LEVELS
    return data


@router.get("/quality-levels")
def quality_levels():
    return {
        "levels": QUALITY_LEVELS,
        "meaning": {
            "UNVERIFIED": "Captured but not yet checked by anyone: raw extraction or unconfirmed entry.",
            "TECHNICIAN_SUBMITTED": "Recorded by a field technician; not yet reviewed by an engineer.",
            "ENGINEER_REVIEWED": "Checked and annotated by an engineer; usable evidence, not manufacturer-approved.",
            "VERIFIED": "Approved engineering knowledge, retrievable as authoritative evidence.",
        },
        "retrieval_weights": {
            "quality": QUALITY_WEIGHTS,
            "document_status": DOC_STATUS_PRIORITY,
            "score": "effective_score = cosine_similarity x quality_weight x version_priority",
        },
    }


@router.get("")
def list_items(
    status: Optional[str] = None,
    quality_level: Optional[str] = None,
    knowledge_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return knowledge_service.list_items(
        status=status,
        quality_level=quality_level,
        knowledge_type=knowledge_type,
        limit=limit,
        offset=offset,
    )


@router.get("/review-queue")
def review_queue(limit: int = Query(50, ge=1, le=200), user: dict = Depends(require_role("ENGINEER", "ADMIN"))):
    pending = knowledge_service.list_items(status="PENDING_REVIEW", limit=limit)
    drafts = knowledge_service.list_items(status="DRAFT", limit=limit)
    reviews = db.execute_query(
        "SELECT knowledge_id, reviewer_name, reviewer_role, action, prior_status, new_status, comment, created_at "
        f"FROM knowledge_reviews ORDER BY created_at DESC LIMIT {int(limit)}"
    )
    return {
        "pending_review": pending["items"],
        "drafts": drafts["items"],
        "recent_reviews": reviews,
        "counts": {"pending": pending["total"], "drafts": drafts["total"]},
        "note": (
            "Approving a case here is what promotes field experience into the Engineering Memory: the item is "
            "embedded with BGE and added to the FAISS index immediately."
        ),
    }


@router.get("/conflicts")
def conflicts(limit: int = Query(50, ge=1, le=200)):
    return {
        "conflicts": knowledge_service.open_conflicts(limit=limit),
        "note": "Conflicting engineering information is never auto-resolved; both sources are retained and shown.",
    }


@router.post("/conflicts/{conflict_id}/resolve")
def resolve_conflict(conflict_id: str, payload: Dict[str, Any] = Body(...), user: dict = Depends(require_role("ENGINEER", "ADMIN"))):
    resolution = (payload.get("resolution") or "").strip()
    if not resolution:
        raise HTTPException(status_code=400, detail="resolution is required.")
    result = knowledge_service.resolve_conflict(conflict_id, resolution, user)
    audit_service.record(
        user=user,
        action="CONFLICT_RESOLVED",
        entity_type="evidence_conflict",
        entity_id=conflict_id,
        detail={"resolution": resolution},
    )
    return result


@router.post("/reindex")
def reindex(payload: Optional[Dict[str, Any]] = Body(None), user: dict = Depends(require_role("ADMIN"))):
    """Rebuild the whole vector index in the background (admin only)."""
    payload = payload or {}
    job = index_service.rebuild_start(user=user, note=payload.get("note") or "admin reindex")
    audit_service.record(
        user=user,
        action="VECTOR_INDEX_REBUILD_STARTED",
        entity_type="vector_index",
        entity_id=job.get("job_id"),
        detail=payload,
    )
    return job


@router.get("/reindex/{job_id}")
def reindex_status(job_id: str, user: dict = Depends(require_role("ADMIN"))):
    job = index_service.rebuild_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown or expired reindex job.")
    return job


@router.get("/{knowledge_id}")
def get_item(knowledge_id: str):
    result = knowledge_service.get_item(knowledge_id)
    if not result.get("item"):
        raise HTTPException(status_code=404, detail="Knowledge item not found.")
    return result


@router.post("/{knowledge_id}/submit")
def submit(knowledge_id: str, user: dict = Depends(get_current_user)):
    result = knowledge_service.submit_for_review(knowledge_id, user)
    if not result.get("item"):
        raise HTTPException(status_code=404, detail="Knowledge item not found.")
    audit_service.record(
        user=user,
        action="KNOWLEDGE_SUBMITTED_FOR_REVIEW",
        entity_type="knowledge_item",
        entity_id=knowledge_id,
        detail={"investigation_id": result["item"].get("investigation_id")},
    )
    return {"status": "ok", "item": result["item"], "message": "Submitted for expert review."}


@router.post("/{knowledge_id}/review")
def review(knowledge_id: str, payload: Dict[str, Any] = Body(...), user: dict = Depends(require_role("ENGINEER", "ADMIN"))):
    action = (payload.get("action") or "").upper()
    if action not in ("APPROVE", "REJECT"):
        raise HTTPException(status_code=400, detail="action must be APPROVE or REJECT.")
    quality = payload.get("quality_level")
    if quality and quality not in QUALITY_LEVELS:
        raise HTTPException(status_code=400, detail=f"Unknown quality level '{quality}'.")
    if action == "APPROVE" and quality and QUALITY_LEVELS.index(quality) < QUALITY_LEVELS.index("ENGINEER_REVIEWED"):
        raise HTTPException(
            status_code=400,
            detail="Approved knowledge must be ENGINEER_REVIEWED or VERIFIED.",
        )

    result = knowledge_service.review(
        knowledge_id=knowledge_id,
        action=action,
        user=user,
        comment=payload.get("comment"),
        edits=payload.get("edits"),
        quality_level=quality,
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("detail"))
    audit_service.record(
        user=user,
        action="KNOWLEDGE_APPROVED" if action == "APPROVE" else "KNOWLEDGE_REJECTED",
        entity_type="knowledge_item",
        entity_id=knowledge_id,
        detail={
            "quality_level": result.get("quality_level"),
            "edits": list((payload.get("edits") or {}).keys()),
            "indexed": (result.get("index") or {}).get("added"),
            "comment": payload.get("comment"),
        },
    )
    return result
