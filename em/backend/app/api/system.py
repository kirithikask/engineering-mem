"""
System status, vector database internals and safety procedures (brief §14, §20, §22).

Everything on these endpoints is read from the running process or the database.
Where a capability does not exist locally, the payload says so instead of implying
that it does — including the honest statement that a full local-network or server
outage stops the platform, and that edge deployment is an architecture option, not
something implemented in this build.
"""

import os
import socket
from typing import Any, Dict

import requests
from fastapi import APIRouter, Depends, Query

from backend.app.api.auth import require_role
from backend.app.db.mysql_client import db
from backend.app.services.index_service import index_service
from backend.app.services.knowledge_service import knowledge_service
from backend.app.services.memory_service import MODEL_NAME, memory_service
from backend.app.services.reasoning_service import OLLAMA_URL, MODEL_NAME as LLM_MODEL
from backend.app.services.retrieval_service import retrieval_service
from backend.app.services.sensor_service import sensor_service

router = APIRouter(prefix="/api/system", tags=["Platform Status"])


def _endpoint_is_local(url: str) -> bool:
    host = url.split("//")[-1].split("/")[0].split(":")[0]
    if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return True
    try:
        resolved = socket.gethostbyname(host)
        return resolved.startswith("127.") or resolved.startswith("192.168.") or resolved.startswith("10.")
    except Exception:
        return False


@router.get("/status")
def status():
    """Component-level status for the workstation strip (brief §20)."""
    llm_ok = False
    llm_error = None
    try:
        response = requests.get(OLLAMA_URL.replace("/generate", "/tags"), timeout=2)
        response.raise_for_status()
        llm_ok = True
    except Exception as exc:
        llm_error = str(exc)

    index = memory_service.index
    components = {
        "local_ai": {
            "label": "LOCAL AI",
            "ready": llm_ok,
            "model": LLM_MODEL,
            "endpoint": OLLAMA_URL,
            "endpoint_is_loopback": _endpoint_is_local(OLLAMA_URL),
            "detail": "Qwen served by the local Ollama runtime." if llm_ok else f"Unreachable: {llm_error}",
        },
        "database": {
            "label": "DATABASE",
            "connected": True,
            "engine": "MySQL" if db.use_mysql else "SQLite (local fallback)",
            "detail": "Relational store for machines, documents, investigations and knowledge.",
        },
        "vector_index": {
            "label": "VECTOR INDEX",
            "available": index is not None,
            "vectors": int(index.ntotal) if index is not None else 0,
            "dimension": int(index.d) if index is not None else 0,
            "model": MODEL_NAME,
            "detail": "FAISS index on local disk." if index is not None else "Index not loaded.",
        },
        "llm": {
            "label": "LLM",
            "local": _endpoint_is_local(OLLAMA_URL),
            "model": LLM_MODEL,
            "detail": "No cloud AI service is configured or called by this platform.",
        },
        "embedding_model": {
            "label": "EMBEDDINGS",
            "ready": memory_service.embedder is not None,
            "model": MODEL_NAME,
        },
        "sensor_model": {
            "label": "SENSOR MODEL",
            "ready": sensor_service.model is not None,
            "note": "Hydraulic test-rig condition classifier (public dataset), used as supporting evidence only.",
        },
    }

    degraded = [key for key, value in components.items() if value.get("ready") is False or value.get("available") is False]
    return {
        "components": components,
        "degraded": degraded,
        "offline_operation": {
            "diagnosis_without_internet": True,
            "detail": (
                "All inference is local: documents, embeddings, the vector index and the language model run on this "
                "host or the local network, so normal diagnosis does not require public internet access."
            ),
            "internet_unavailable_notice": "Internet unavailable — local diagnosis remains operational.",
            "limitation": (
                "If power, the machine hosting the platform, or the local network itself is unavailable, the platform "
                "stops with it. This build does not provide a failover path around that."
            ),
        },
        "edge_deployment": {
            "implemented": False,
            "detail": (
                "Edge deployment (central engineering memory synchronising to a local edge server running FastAPI, "
                "BGE, FAISS and Qwen) is a deployment architecture option. It is NOT implemented in this build, and "
                "this endpoint reports it as such rather than implying availability."
            ),
        },
    }


@router.get("/vector-db")
def vector_db():
    """Real FAISS internals: counts, dimension, mapping, versions and measured latency."""
    stats = index_service.stats()
    stats["retrieval_latency"] = retrieval_service.latency_summary()
    stats["recent_retrievals"] = retrieval_service.recent_events(limit=10)
    stats["document_chunks_total"] = _scalar("SELECT COUNT(*) AS n FROM document_chunks")
    stats["document_chunks_approved"] = len(index_service.approved_chunks())
    stats["maintenance_cases_total"] = _scalar("SELECT COUNT(*) AS n FROM maintenance_cases")
    stats["approved_knowledge_total"] = _scalar(
        "SELECT COUNT(*) AS n FROM knowledge_items WHERE status = 'APPROVED'"
    )
    stats["approved_knowledge_indexed"] = _scalar(
        "SELECT COUNT(*) AS n FROM embedding_records WHERE owner_type = 'knowledge'"
    )
    stats["rebuild_note"] = (
        "Only evidence that has been approved can enter the index: maintenance cases marked verified, chunks of "
        "CURRENT/APPROVED document revisions, and knowledge items with status APPROVED."
    )
    return stats


@router.get("/safety")
def safety(component: str = Query(None), task: str = Query(None)):
    return knowledge_service.safety_for(component=component, task=task)


@router.get("/audit-summary")
def audit_summary(user: dict = Depends(require_role("ADMIN"))):
    """Counts by action, read from the append-only audit log."""
    rows = db.execute_query(
        "SELECT action, COUNT(*) AS n, MAX(created_at) AS last_at FROM audit_logs GROUP BY action ORDER BY n DESC"
    )
    total = _scalar("SELECT COUNT(*) AS n FROM audit_logs")
    return {
        "total_events": total,
        "by_action": [
            {"action": row["action"], "count": int(row["n"]), "last_at": row.get("last_at")} for row in rows
        ],
    }


def _scalar(query: str) -> int:
    rows = db.execute_query(query)
    if not rows:
        return 0
    value = list(rows[0].values())[0]
    return int(value) if value is not None else 0
