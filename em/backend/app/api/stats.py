"""
Aggregate knowledge-base statistics.

The UI reads every headline figure from here instead of hardcoding counts, so the
dashboard can never drift from the database and index that actually exist.
"""

import os

from fastapi import APIRouter

from backend.app.db.mysql_client import db
from backend.app.services.memory_service import memory_service, MODEL_NAME

router = APIRouter(prefix="/api/stats", tags=["Knowledge Base Statistics"])

# Ordered palette from the industrial design language, applied cyclically to bars.
COMPONENT_PALETTE = ["#C9973E", "#8E6330", "#5D8068", "#A8B0B7", "#B85C55", "#4B5563"]


def _scalar(query: str, default: int = 0) -> int:
    rows = db.execute_query(query)
    if not rows:
        return default
    value = list(rows[0].values())[0]
    return int(value) if value is not None else default


@router.get("")
def knowledge_base_stats():
    machine_total = _scalar("SELECT COUNT(*) AS n FROM machines")
    case_total = _scalar("SELECT COUNT(*) AS n FROM maintenance_cases")

    index_vectors = int(memory_service.index.ntotal) if memory_service.index is not None else 0
    index_dimension = int(memory_service.index.d) if memory_service.index is not None else 0

    failure_distribution = [
        {
            "name": row["component"],
            "count": int(row["n"]),
            "color": COMPONENT_PALETTE[i % len(COMPONENT_PALETTE)],
        }
        for i, row in enumerate(
            db.execute_query(
                "SELECT component, COUNT(*) AS n FROM maintenance_cases "
                "GROUP BY component ORDER BY n DESC LIMIT 8"
            )
        )
    ]

    return {
        "machines": {
            "total": machine_total,
            "by_status": [
                {"status": row["status"], "count": int(row["n"])}
                for row in db.execute_query(
                    "SELECT status, COUNT(*) AS n FROM machines GROUP BY status ORDER BY n DESC"
                )
            ],
        },
        "cases": {
            "total": case_total,
            "by_source": [
                {"source_type": row["source_type"] or "historical", "count": int(row["n"])}
                for row in db.execute_query(
                    "SELECT source_type, COUNT(*) AS n FROM maintenance_cases "
                    "GROUP BY source_type ORDER BY n DESC"
                )
            ],
            "failure_distribution": failure_distribution,
        },
        "components": _scalar("SELECT COUNT(*) AS n FROM components"),
        "technicians": _scalar("SELECT COUNT(*) AS n FROM technicians"),
        "documents": _scalar("SELECT COUNT(*) AS n FROM documents"),
        "document_chunks": _scalar("SELECT COUNT(*) AS n FROM document_chunks"),
        "index": {
            "vectors": index_vectors,
            "dimension": index_dimension,
            "embedding_model": MODEL_NAME,
            "loaded": memory_service.index is not None,
        },
        "database": {
            "engine": "MySQL" if db.use_mysql else "SQLite (local fallback)",
            "connected": True,
        },
        "reasoning_model": os.getenv("OLLAMA_MODEL", "qwen3:4b"),
    }
