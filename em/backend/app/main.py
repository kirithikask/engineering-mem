import os
import sys
import time

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("backend"))

from backend.app.api.auth import router as auth_router
from backend.app.api.machines import router as machines_router
from backend.app.api.diagnose import router as diagnose_router
from backend.app.api.cases import router as cases_router
from backend.app.api.documents import router as documents_router
from backend.app.api.sensors import router as sensors_router
from backend.app.api.benchmark import router as benchmark_router
from backend.app.api.memory import router as memory_router
from backend.app.api.stats import router as stats_router

# Extension routers (ADDITIVE). Each one serves only new paths; no existing
# route, response shape or behaviour is redefined.
from backend.app.api.audit import router as audit_router
from backend.app.api.documents_ext import router as documents_ext_router
from backend.app.api.ingestion import router as ingestion_router
from backend.app.api.investigations import router as investigations_router
from backend.app.api.knowledge import router as knowledge_router
from backend.app.api.passport import router as passport_router
from backend.app.api.retrieval import router as retrieval_router
from backend.app.api.system import router as system_router
from backend.app.db.extensions import ensure_extension_schema
from backend.app.db.mysql_client import db
from backend.app.services.memory_service import memory_service
from backend.app.services.sensor_service import sensor_service

OLLAMA_TAGS_URL = os.getenv("OLLAMA_TAGS_URL", "http://localhost:11434/api/tags")
_ollama_cache = {"checked_at": 0.0, "available": False}


def _ollama_available(ttl_seconds: float = 15.0) -> bool:
    """Probe the local Ollama runtime, cached briefly so health checks stay cheap."""
    now = time.time()
    if now - _ollama_cache["checked_at"] < ttl_seconds:
        return _ollama_cache["available"]
    try:
        response = requests.get(OLLAMA_TAGS_URL, timeout=2)
        response.raise_for_status()
        available = True
    except Exception:
        available = False
    _ollama_cache.update(checked_at=now, available=available)
    return available

app = FastAPI(
    title="Engineering Memory API",
    description="Offline Industrial Heavy Equipment Diagnostic Platform",
    version="1.0.0"
)

# Enable CORS for local React development and LAN deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router)
app.include_router(machines_router)
app.include_router(diagnose_router)
app.include_router(cases_router)
app.include_router(documents_router)
app.include_router(sensors_router)
app.include_router(benchmark_router)
app.include_router(memory_router)
app.include_router(stats_router)

# --- Extension modules: investigations, ingestion, knowledge, retrieval, audit --
app.include_router(investigations_router)
app.include_router(ingestion_router)
app.include_router(documents_ext_router)
app.include_router(knowledge_router)
app.include_router(retrieval_router)
app.include_router(passport_router)
app.include_router(audit_router)
app.include_router(system_router)

# Create the additive extension tables (idempotent). A failure here must never
# stop the original platform from starting, so it is reported and not raised.
try:
    EXTENSION_SCHEMA = ensure_extension_schema()
except Exception as _schema_error:  # pragma: no cover - defensive
    EXTENSION_SCHEMA = {"error": str(_schema_error)}
    print(f"[Schema] Extension schema could not be verified: {_schema_error}")

@app.get("/api/health")
def health_check():
    """Report only what is actually loaded and reachable, with an operator-facing message."""
    ollama_ok = _ollama_available()
    faiss_ok = memory_service.index is not None
    sensor_ok = sensor_service.model is not None

    degraded = []
    if not ollama_ok:
        degraded.append("Local AI engine unavailable.")
    if not faiss_ok:
        degraded.append("Engineering memory retrieval unavailable.")

    return {
        "status": "degraded" if degraded else "online",
        "service": "Engineering Memory Industrial Backend",
        "offline_mode": True,
        "database": "MySQL (Connected)" if db.use_mysql else "SQLite Local Fallback (Active)",
        "faiss_vectors": int(memory_service.index.ntotal) if faiss_ok else 0,
        "warnings": degraded,
        "models_loaded": {
            "bge_embeddings": memory_service.embedder is not None,
            "faiss_index": faiss_ok,
            "qwen_ollama": ollama_ok,
            "sensor_rf_classifier": sensor_ok
        },
        # Additive: reports how the extension schema loaded. Existing keys above
        # are unchanged for existing clients.
        "extension_schema": EXTENSION_SCHEMA,
    }

@app.get("/")
def root():
    """Serve the built React app so the whole product runs as ONE process on ONE port.

    Deployment model: build the frontend once (`npm run build` in frontend/), then a
    single uvicorn process on port 8000 serves both the UI and the API at
    http://<server-ip>:8000 for every technician on the LAN. When dist/ is absent
    (API-only development) fall back to the JSON status message.
    """
    if os.path.exists(_index_html):
        return FileResponse(_index_html)
    return {"message": "Engineering Memory API is operational.", "hint": "Frontend not built - run `npm run build` in frontend/"}


# --- Single-process frontend serving -----------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FRONTEND_DIST = os.getenv("FRONTEND_DIST", os.path.join(_PROJECT_ROOT, "frontend", "dist"))
_index_html = os.path.join(FRONTEND_DIST, "index.html")

if os.path.isdir(os.path.join(FRONTEND_DIST, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    """Client-side routing support: static files when they exist, index.html otherwise.

    Unknown /api/* paths stay JSON 404s instead of returning the SPA shell.
    """
    if full_path == "api" or full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    candidate = os.path.normpath(os.path.join(FRONTEND_DIST, full_path))
    if candidate.startswith(os.path.normpath(FRONTEND_DIST)) and os.path.isfile(candidate):
        return FileResponse(candidate)
    if os.path.exists(_index_html):
        return FileResponse(_index_html)
    raise HTTPException(status_code=404, detail="Not found")

if __name__ == "__main__":
    import uvicorn
    # 0.0.0.0 so technician devices on the LAN can reach http://<server-ip>:8000
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=False)
