"""
Investigation API (brief §12, §17, §18, §25).

The workstation talks to these endpoints only. Every field returned comes from a
row written by a real action: findings, timeline events, retrieval snapshots and
repair attempts are all persisted, so reloading the page reconstructs the same
investigation.
"""

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile

from backend.app.api.auth import get_current_user
from backend.app.db.mysql_client import db
from backend.app.services.audit_service import audit_service
from backend.app.services.investigation_service import EVIDENCE_DIR, investigation_service
from backend.app.services.knowledge_service import knowledge_service

router = APIRouter(prefix="/api/investigations", tags=["Investigations"])

MAX_PHOTO_BYTES = int(os.getenv("EM_MAX_PHOTO_BYTES", str(16 * 1024 * 1024)))
ALLOWED_PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic"}


def _require(investigation_id: str) -> Dict[str, Any]:
    rows = db.execute_query(
        "SELECT * FROM investigations WHERE investigation_id = {} ".format("%s" if db.use_mysql else "?"),
        (investigation_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Investigation not found.")
    return rows[0]


@router.get("")
def list_investigations(
    machine_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
):
    return {"investigations": investigation_service.list(machine_id=machine_id, status=status, limit=limit)}


@router.post("")
def create_investigation(payload: Dict[str, Any] = Body(...), user: dict = Depends(get_current_user)):
    machine_id = (payload.get("machine_id") or "").strip()
    if not machine_id:
        raise HTTPException(status_code=400, detail="machine_id is required.")
    symptoms = payload.get("symptoms") or []
    if isinstance(symptoms, str):
        symptoms = [s.strip() for s in symptoms.split(",") if s.strip()]
    problem = payload.get("problem_statement") or payload.get("title") or "; ".join(symptoms)
    result = investigation_service.create(
        machine_id=machine_id,
        title=payload.get("title") or problem[:180] or "Unnamed investigation",
        problem_statement=problem,
        symptoms=list(symptoms),
        subsystem=payload.get("subsystem"),
        severity=(payload.get("severity") or "MEDIUM"),
        user=user,
    )
    if not result.get("investigation"):
        raise HTTPException(status_code=400, detail="Machine not found or investigation could not be created.")
    return result


@router.get("/attempts/similar")
def similar_attempts(
    component: Optional[str] = None,
    symptom: Optional[str] = None,
    limit: int = Query(6, ge=1, le=25),
):
    """Historical repair attempts for comparable symptoms, successes and failures."""
    return investigation_service.similar_attempts(component=component, symptom_text=symptom, limit=limit)


@router.get("/{investigation_id}")
def get_investigation(investigation_id: str):
    result = investigation_service.get(investigation_id)
    if not result.get("investigation"):
        raise HTTPException(status_code=404, detail="Investigation not found.")
    return result


@router.get("/{investigation_id}/timeline")
def timeline(investigation_id: str):
    _require(investigation_id)
    return {
        "investigation_id": investigation_id,
        "timeline": investigation_service.timeline(investigation_id),
        "source": "investigation_events table (persisted, not reconstructed on the client)",
    }


@router.post("/{investigation_id}/findings")
def add_finding(investigation_id: str, payload: Dict[str, Any] = Body(...), user: dict = Depends(get_current_user)):
    _require(investigation_id)
    return investigation_service.add_finding(investigation_id=investigation_id, payload=payload, user=user)


@router.post("/{investigation_id}/re-evaluate")
def re_evaluate(investigation_id: str, user: dict = Depends(get_current_user)):
    _require(investigation_id)
    return investigation_service.re_evaluate(investigation_id, user=user, trigger="manual")


@router.post("/{investigation_id}/diagnose")
def diagnose(investigation_id: str, payload: Optional[Dict[str, Any]] = Body(None), user: dict = Depends(get_current_user)):
    """Grounded reasoning over the accumulated evidence of this investigation."""
    _require(investigation_id)
    return investigation_service.diagnose(investigation_id=investigation_id, user=user, extra=payload or {})


@router.get("/{investigation_id}/next-inspection")
def next_inspection(investigation_id: str):
    _require(investigation_id)
    situation = investigation_service.situation(investigation_id)
    return {"investigation_id": investigation_id, "situation": situation}


@router.get("/{investigation_id}/safety")
def safety(investigation_id: str, component: Optional[str] = None, task: Optional[str] = None):
    _require(investigation_id)
    return knowledge_service.safety_for(component=component, task=task)


@router.post("/{investigation_id}/attempts")
def add_attempt(investigation_id: str, payload: Dict[str, Any] = Body(...), user: dict = Depends(get_current_user)):
    _require(investigation_id)
    return investigation_service.add_attempt(investigation_id=investigation_id, payload=payload, user=user)


@router.post("/{investigation_id}/repair")
def record_repair(investigation_id: str, payload: Dict[str, Any] = Body(...), user: dict = Depends(get_current_user)):
    """Record the repair that was carried out, with its outcome (brief §5)."""
    _require(investigation_id)
    return investigation_service.add_attempt(investigation_id=investigation_id, payload=payload, user=user)


@router.post("/{investigation_id}/verify")
def verify(investigation_id: str, payload: Dict[str, Any] = Body(...), user: dict = Depends(get_current_user)):
    _require(investigation_id)
    return investigation_service.verify(investigation_id=investigation_id, payload=payload, user=user)


@router.post("/{investigation_id}/close")
def close(investigation_id: str, payload: Dict[str, Any] = Body(...), user: dict = Depends(get_current_user)):
    _require(investigation_id)
    return investigation_service.close(investigation_id=investigation_id, payload=payload, user=user)


@router.post("/{investigation_id}/create-knowledge")
def create_knowledge(investigation_id: str, payload: Optional[Dict[str, Any]] = Body(None), user: dict = Depends(get_current_user)):
    """Generate the structured case draft for expert review (closed loop, step 1)."""
    _require(investigation_id)
    return investigation_service.create_knowledge(investigation_id=investigation_id, payload=payload or {}, user=user)


@router.get("/{investigation_id}/case-draft")
def case_draft(investigation_id: str):
    investigation = _require(investigation_id)
    investigation.setdefault("symptoms_json", investigation.get("symptoms_json"))
    return {
        "investigation_id": investigation_id,
        "draft": knowledge_service.create_case_draft(investigation=investigation, user={}),
    }


@router.get("/{investigation_id}/photos")
def list_photos(investigation_id: str):
    _require(investigation_id)
    return {"photos": investigation_service.photos(investigation_id)}


@router.post("/{investigation_id}/photos")
async def upload_photo(
    investigation_id: str,
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
    component: Optional[str] = Form(None),
    user: dict = Depends(get_current_user),
):
    """Store photo evidence, analyse it locally and offer it as investigation evidence."""
    _require(investigation_id)
    filename = file.filename or "photo.jpg"
    extension = os.path.splitext(filename)[1].lower()
    if extension and extension not in ALLOWED_PHOTO_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported image type '{extension}'.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded photo is empty.")
    if len(content) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail=f"Photo exceeds the {MAX_PHOTO_BYTES} byte limit.")

    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    import uuid as _uuid

    temp_path = os.path.join(EVIDENCE_DIR, f"PHO-{_uuid.uuid4().hex[:8].upper()}_{filename}")
    with open(temp_path, "wb") as handle:
        handle.write(content)

    result = investigation_service.add_photo(
        investigation_id=investigation_id,
        payload={
            "filename": filename,
            "caption": caption,
            "component": component,
            "bytes": len(content),
            "path": temp_path,
        },
        user=user,
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("detail"))
    return result


@router.post("/{investigation_id}/photos/{photo_id}/correct")
def correct_photo(investigation_id: str, photo_id: str, payload: Dict[str, Any] = Body(...), user: dict = Depends(get_current_user)):
    _require(investigation_id)
    component = (payload.get("component") or "").strip()
    if not component:
        raise HTTPException(status_code=400, detail="component is required.")
    return investigation_service.correct_photo(photo_id=photo_id, component=component, user=user)


@router.post("/{investigation_id}/observations")
def add_observation(investigation_id: str, payload: Dict[str, Any] = Body(...), user: dict = Depends(get_current_user)):
    """Free-text technician observation, kept as its own evidence record."""
    investigation = _require(investigation_id)
    text = (payload.get("observation_text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="observation_text is required.")
    import uuid as _uuid

    observation_id = f"OBS-{_uuid.uuid4().hex[:8].upper()}"
    db.execute_write(
        "INSERT INTO technician_observations (observation_id, machine_id, investigation_id, component, "
        "observation_text, context_json, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
        "INSERT INTO technician_observations (observation_id, machine_id, investigation_id, component, "
        "observation_text, context_json, created_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            observation_id,
            investigation["machine_id"],
            investigation_id,
            payload.get("component"),
            text,
            None,
            user.get("user_id"),
        ),
    )
    investigation_service.add_event(
        investigation_id=investigation_id,
        event_type="OBSERVATION",
        summary=text[:300],
        user=user,
        payload={"observation_id": observation_id, "component": payload.get("component")},
    )
    audit_service.record(
        user=user,
        action="OBSERVATION_RECORDED",
        entity_type="observation",
        entity_id=observation_id,
        machine_id=investigation["machine_id"],
        investigation_id=investigation_id,
        detail={"component": payload.get("component")},
    )
    return {"status": "ok", "observation_id": observation_id, "situation": investigation_service.situation(investigation_id)}
