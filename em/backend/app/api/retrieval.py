"""
Retrieval API (brief §9, §25).

``POST /api/retrieval/search`` exposes the hybrid retrieval surface: semantic
similarity combined with metadata filtering, source-quality weighting and document
version priority. Everything reported — latency, vector count, dimension, scores
— is measured on the call or read from the live index.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Query

from backend.app.api.auth import get_current_user
from backend.app.services.retrieval_service import retrieval_service

router = APIRouter(prefix="/api/retrieval", tags=["Evidence Retrieval"])


@router.post("/search")
def search(payload: Dict[str, Any] = Body(...), user: dict = Depends(get_current_user)):
    query = (payload.get("query") or "").strip()
    if not query:
        # An empty query is allowed only when symptoms are supplied instead.
        symptoms = payload.get("symptoms") or []
        if not symptoms:
            return {
                "query": "",
                "evidence": [],
                "counts": {"candidates": 0, "returned": 0},
                "detail": "Provide a query or a symptom list.",
            }
        return retrieval_service.search_text(
            symptoms,
            filters=payload.get("filters"),
            top_k=int(payload.get("top_k") or 8),
            user=user,
            machine_id=payload.get("machine_id"),
            investigation_id=payload.get("investigation_id"),
        )
    return retrieval_service.search(
        query,
        filters=payload.get("filters"),
        top_k=int(payload.get("top_k") or 8),
        user=user,
        machine_id=payload.get("machine_id"),
        investigation_id=payload.get("investigation_id"),
    )


@router.post("/search-by-symptoms")
def search_by_symptoms(payload: Dict[str, Any] = Body(...), user: dict = Depends(get_current_user)):
    """Search using the canonical symptom representation the diagnosis path uses."""
    return retrieval_service.search_text(
        payload.get("symptoms") or [],
        filters=payload.get("filters"),
        top_k=int(payload.get("top_k") or 8),
        user=user,
        machine_id=payload.get("machine_id"),
        investigation_id=payload.get("investigation_id"),
    )


@router.get("/filters")
def filter_options():
    return retrieval_service.filter_options()


@router.get("/events")
def events(limit: int = Query(25, ge=1, le=200)):
    return {
        "events": retrieval_service.recent_events(limit=limit),
        "note": "Every row is a real retrieval that ran on this server, with its measured latency.",
    }


@router.get("/latency")
def latency():
    return {
        "summary": retrieval_service.latency_summary(),
        "measurement_source": "retrieval_events table (per-call measurements written at retrieval time)",
    }
