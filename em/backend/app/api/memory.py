from fastapi import APIRouter, Query
from typing import Dict, Any, List
from backend.app.services.memory_service import memory_service

router = APIRouter(prefix="/api/memory", tags=["Engineering Memory Search"])

@router.get("/search")
def search_memory(query: str = Query(..., min_length=2), top_k: int = 10):
    results = memory_service.search(query, top_k_cases=top_k, top_k_chunks=top_k)
    return {
        "query": query,
        "cases": results["cases"],
        "chunks": results["chunks"],
        "total_results": len(results["cases"]) + len(results["chunks"])
    }
