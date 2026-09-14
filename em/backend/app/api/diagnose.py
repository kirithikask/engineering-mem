import uuid
import json
import time
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends, Body

from backend.app.schemas.schemas import DiagnoseRequest, DiagnoseResponse, ConfirmDiagnosisRequest
from backend.app.services.memory_service import memory_service
from backend.app.services.reasoning_service import reasoning_engine, parse_symptoms
from backend.app.services.representation import query_text
from backend.app.services.sensor_service import sensor_service
from backend.app.api.auth import get_current_user
from backend.app.db.mysql_client import db

router = APIRouter(prefix="/api/diagnose", tags=["Diagnosis Engine"])

# Evidence bundles are cached between the retrieval and reasoning phases so the
# technician sees retrieved evidence immediately and the LLM step never re-runs
# retrieval. Bounded so a long session cannot grow without limit.
RETRIEVAL_CACHE_MAX = 64
_retrieval_cache: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()

# ---------------------------------------------------------------------------
# Background reasoning jobs.
#
# Measured on this host: Qwen 3:4B generates at ~2 tokens/s on CPU, so a full
# reasoning pass takes 100-150 s. Any long-lived HTTP request through the
# Cloudflare tunnel is killed by the proxy at ~100 s (error 524) — the root
# cause of "model not returning an answer" via the public link. The fix is
# structural: /reason/start launches reasoning in a worker thread and returns
# a job id immediately; /reason/status polls are short, so no request ever
# carries a generation in flight across the proxy.
# ---------------------------------------------------------------------------
REASON_JOBS_MAX = 32
_reason_jobs: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_reason_jobs_lock = threading.Lock()


def _run_reason_job(job_id: str, bundle: Dict[str, Any]) -> None:
    """Worker: run the full reasoning pass, store the result for polling."""
    try:
        diagnosis = reasoning_engine.diagnose(
            machine_id=bundle["machine_id"],
            symptoms=bundle["symptoms"],
            observations=bundle["observations"],
            retrieved_cases=bundle["cases"],
            retrieved_chunks=bundle["chunks"],
            sensor_findings=bundle["sensor"],
        )
        diagnosis["machine"] = bundle["machine"]
        diagnosis["sensor_evidence"] = bundle["sensor"]
        with _reason_jobs_lock:
            _reason_jobs[job_id] = {"status": "done", "diagnosis": diagnosis, "finished_at": time.time()}
    except Exception as e:  # pragma: no cover - defensive
        print(f"[ReasonJob {job_id}] failed: {e}")
        with _reason_jobs_lock:
            _reason_jobs[job_id] = {"status": "failed", "error": str(e), "finished_at": time.time()}


def _gc_reason_jobs() -> None:
    """Keep the job table bounded (completed jobs older than 15 min are dropped)."""
    with _reason_jobs_lock:
        now = time.time()
        for jid in [j for j, v in _reason_jobs.items()
                    if v.get("finished_at") and now - v["finished_at"] > 900]:
            _reason_jobs.pop(jid, None)
        while len(_reason_jobs) > REASON_JOBS_MAX:
            _reason_jobs.popitem(last=False)


@router.post("/reason/start")
def start_reasoning(payload: Dict[str, Any] = Body(...), user: dict = Depends(get_current_user)):
    """Stage 2 entry: validate the bundle, spawn reasoning, return a job id at once."""
    retrieval_id = payload.get("retrieval_id")
    bundle = _retrieval_cache.get(retrieval_id) if retrieval_id else None
    if bundle is None:
        raise HTTPException(
            status_code=404,
            detail="Retrieval session expired or not found. Re-run the retrieval step.",
        )

    _gc_reason_jobs()
    job_id = f"JOB-{uuid.uuid4().hex[:10].upper()}"
    with _reason_jobs_lock:
        _reason_jobs[job_id] = {
            "status": "running",
            "started_at": time.time(),
            "retrieval_id": retrieval_id,
        }
    threading.Thread(target=_run_reason_job, args=(job_id, bundle), daemon=True).start()
    return {"job_id": job_id, "status": "running"}


@router.get("/reason/status/{job_id}")
def reason_status(job_id: str, user: dict = Depends(get_current_user)):
    """Short poll: job state. A finished job returns the full diagnosis exactly once,
    then flips to 'consumed' so the audit write does not repeat on every poll."""
    with _reason_jobs_lock:
        job = _reason_jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown or expired reasoning job.")
        status = job["status"]
        # 'done' and 'consumed' both carry the diagnosis: the first delivery
        # audits once, later polls re-serve the stored result. Re-polling a
        # finished job used to crash with a NameError (second poll observed as
        # a 500 through the tunnel, leaving the UI waiting forever).
        diagnosis = job.get("diagnosis")
        if status == "done":
            job["status"] = "consumed"

    if status == "running":
        return {"job_id": job_id, "status": "running", "elapsed_s": round(time.time() - job["started_at"], 1)}
    if status == "failed":
        return {"job_id": job_id, "status": "failed", "detail": job.get("error", "reasoning failed")}
    if diagnosis is None:
        raise HTTPException(status_code=500, detail="Reasoning job finished without a result.")

    # Assemble the final payload (audit + timings), same shape as the
    # synchronous /reason endpoint so the frontend treats them identically.
    already_audited = status == "consumed"
    bundle = _retrieval_cache.get(job.get("retrieval_id"), {})
    diagnosis["retrieval_id"] = job.get("retrieval_id")
    mysql_ms = 0.0 if already_audited else _audit(bundle, diagnosis, user)
    timings = dict(bundle.get("timings", {}))
    timings.update(diagnosis.get("timings", {}))
    timings["mysql_ms"] = round(timings.get("mysql_ms", 0.0) + mysql_ms, 2)
    timings["total_ms"] = round(timings.get("retrieval_total_ms", 0.0) + timings.get("reasoning_total_ms", 0.0) + mysql_ms, 2)
    diagnosis["timings"] = timings
    return diagnosis



def _machine_context(machine_id: str) -> Dict[str, Any]:
    rows = db.execute_query(
        "SELECT machine_model, machine_type, manufacturer, operating_hours, status, last_maintenance "
        "FROM machines WHERE machine_id = " + ("%s" if db.use_mysql else "?"),
        (machine_id,),
    )
    return rows[0] if rows else {}


def _build_query(symptoms: List[str]) -> str:
    """
    Search text for a symptom report, built by the canonical representation
    module so the diagnosis path and the benchmark path ask the same question.
    """
    return query_text(symptoms)


def _retrieve(req: DiagnoseRequest) -> Dict[str, Any]:
    """
    Stage 1: parse symptoms, retrieve engineering memory, assess sensor condition.

    Sensor inference and memory retrieval are independent, so they run
    concurrently. Returns the full evidence bundle plus measured stage timings.
    """
    stage_start = time.time()

    t0 = time.time()
    symptom_struct = parse_symptoms(req.symptoms)
    symptom_ms = (time.time() - t0) * 1000

    t0 = time.time()
    machine = _machine_context(req.machine_id)
    mysql_ms = (time.time() - t0) * 1000

    search_query = _build_query(req.symptoms)
    sensor_inputs = req.sensor_telemetry or req.observations

    with ThreadPoolExecutor(max_workers=2) as pool:
        memory_future = pool.submit(memory_service.search, search_query, 6, 3)
        sensor_future = pool.submit(
            sensor_service.analyze_sensor_data, req.machine_id, sensor_inputs
        )
        memory_results = memory_future.result()
        sensor_findings = sensor_future.result()

    mem_timings = memory_results.get("timings", {})
    retrieved_cases = memory_results.get("cases", [])
    retrieved_chunks = memory_results.get("chunks", [])

    sufficiency = reasoning_engine.evaluate_evidence_sufficiency(retrieved_cases, retrieved_chunks)
    max_similarity = max(
        [c.get("similarity", 0.0) for c in retrieved_cases]
        + [c.get("similarity", 0.0) for c in retrieved_chunks]
        + [0.0]
    )

    retrieval_id = f"RET-{uuid.uuid4().hex[:10].upper()}"
    bundle = {
        "retrieval_id": retrieval_id,
        "machine_id": req.machine_id,
        "machine": machine,
        "symptoms": req.symptoms,
        "observations": req.observations or {},
        "query_text": search_query,
        "symptom_structure": symptom_struct,
        "evidence_sufficiency": sufficiency,
        "max_similarity": round(float(max_similarity), 3),
        "cases": retrieved_cases,
        "chunks": retrieved_chunks,
        "sensor": sensor_findings,
        "timings": {
            "symptom_processing_ms": round(symptom_ms, 2),
            "mysql_ms": round(mysql_ms, 2),
            "embedding_ms": mem_timings.get("embedding_ms", 0.0),
            "faiss_retrieval_ms": mem_timings.get("faiss_ms", 0.0),
            "retrieval_cache_hit": mem_timings.get("cache_hit", False),
            "sensor_ml_ms": round(sensor_findings.get("inference_ms", 0.0), 2) if sensor_findings else 0.0,
            "retrieval_total_ms": round((time.time() - stage_start) * 1000, 2),
        },
    }

    _retrieval_cache[retrieval_id] = bundle
    if len(_retrieval_cache) > RETRIEVAL_CACHE_MAX:
        _retrieval_cache.popitem(last=False)
    return bundle


def _audit(bundle: Dict[str, Any], diagnosis: Dict[str, Any], user: Dict[str, Any]) -> float:
    """Persist the diagnosis for auditability. Returns the write duration in ms."""
    diag_id = f"DIAG-{uuid.uuid4().hex[:8].upper()}"
    diagnosis["diagnosis_id"] = diag_id
    t0 = time.time()
    try:
        db.execute_write(
            "INSERT INTO diagnoses (diagnosis_id, machine_id, user_id, symptoms_analyzed, evidence_sufficiency, likely_cause, affected_component, component_id, confidence_score, reasoning, recommended_inspection, previous_resolution) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
            "INSERT INTO diagnoses (diagnosis_id, machine_id, user_id, symptoms_analyzed, evidence_sufficiency, likely_cause, affected_component, component_id, confidence_score, reasoning, recommended_inspection, previous_resolution) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                diag_id,
                bundle["machine_id"],
                user.get("user_id", "USR-003"),
                json.dumps(diagnosis["symptoms_analyzed"]),
                diagnosis["evidence_sufficiency"],
                diagnosis["likely_causes"][0]["cause"] if diagnosis["likely_causes"] else "None",
                diagnosis["affected_component"],
                diagnosis["component_id"],
                diagnosis["confidence_score"],
                diagnosis["reasoning"],
                json.dumps(diagnosis["recommended_inspection"]),
                diagnosis.get("previous_successful_resolution", ""),
            ),
        )
    except Exception as e:
        print(f"[Diagnose DB Error] {e}")
    return (time.time() - t0) * 1000


@router.post("/retrieve")
def retrieve_evidence(req: DiagnoseRequest, user: dict = Depends(get_current_user)):
    """
    Stage 1 of the diagnosis workflow.

    Returns parsed symptoms, retrieved historical cases, document excerpts and
    sensor evidence in tens of milliseconds so the workstation can display the
    engineering evidence before the local model has finished reasoning.
    """
    bundle = _retrieve(req)
    return {
        "retrieval_id": bundle["retrieval_id"],
        "machine_id": bundle["machine_id"],
        "machine": bundle["machine"],
        "symptoms_analyzed": bundle["symptom_structure"]["raw_symptoms"],
        "symptom_structure": bundle["symptom_structure"],
        "evidence_sufficiency": bundle["evidence_sufficiency"],
        "max_similarity": bundle["max_similarity"],
        "historical_evidence": bundle["cases"],
        "document_evidence": bundle["chunks"],
        "sensor_evidence": bundle["sensor"],
        "timings": bundle["timings"],
    }


@router.post("/reason", response_model=DiagnoseResponse)
def reason_over_evidence(
    payload: Dict[str, Any] = Body(...),
    user: dict = Depends(get_current_user),
):
    """
    Stage 2: run local Qwen reasoning over a previously retrieved evidence bundle.

    If the local AI engine is unavailable the response still carries the retrieved
    evidence and sets reasoning_status='ai_engine_unavailable' so the UI can say so
    rather than showing nothing.
    """
    retrieval_id = payload.get("retrieval_id")
    bundle = _retrieval_cache.get(retrieval_id) if retrieval_id else None
    if bundle is None:
        raise HTTPException(
            status_code=404,
            detail="Retrieval session expired or not found. Re-run the retrieval step.",
        )

    diagnosis = reasoning_engine.diagnose(
        machine_id=bundle["machine_id"],
        symptoms=bundle["symptoms"],
        observations=bundle["observations"],
        retrieved_cases=bundle["cases"],
        retrieved_chunks=bundle["chunks"],
        sensor_findings=bundle["sensor"],
    )
    diagnosis["machine"] = bundle["machine"]
    diagnosis["sensor_evidence"] = bundle["sensor"]
    diagnosis["retrieval_id"] = retrieval_id

    mysql_ms = _audit(bundle, diagnosis, user)

    timings = dict(bundle["timings"])
    timings.update(diagnosis.get("timings", {}))
    timings["mysql_ms"] = round(timings.get("mysql_ms", 0.0) + mysql_ms, 2)
    timings["total_ms"] = round(timings.get("retrieval_total_ms", 0.0) + timings.get("reasoning_total_ms", 0.0) + mysql_ms, 2)
    diagnosis["timings"] = timings
    return diagnosis


@router.post("", response_model=DiagnoseResponse)
def perform_diagnosis(req: DiagnoseRequest, user: dict = Depends(get_current_user)):
    """One-shot diagnosis: retrieval immediately followed by reasoning."""
    bundle = _retrieve(req)
    diagnosis = reasoning_engine.diagnose(
        machine_id=bundle["machine_id"],
        symptoms=bundle["symptoms"],
        observations=bundle["observations"],
        retrieved_cases=bundle["cases"],
        retrieved_chunks=bundle["chunks"],
        sensor_findings=bundle["sensor"],
    )
    diagnosis["machine"] = bundle["machine"]
    diagnosis["sensor_evidence"] = bundle["sensor"]
    diagnosis["retrieval_id"] = bundle["retrieval_id"]

    mysql_ms = _audit(bundle, diagnosis, user)
    timings = dict(bundle["timings"])
    timings.update(diagnosis.get("timings", {}))
    timings["mysql_ms"] = round(timings.get("mysql_ms", 0.0) + mysql_ms, 2)
    timings["total_ms"] = round(timings.get("retrieval_total_ms", 0.0) + timings.get("reasoning_total_ms", 0.0) + mysql_ms, 2)
    diagnosis["timings"] = timings
    return diagnosis


@router.post("/confirm")
def confirm_diagnosis(req: ConfirmDiagnosisRequest, user: dict = Depends(get_current_user)):
    """
    Technician verification loop:
    Promotes verified repair findings into the persistent maintenance_cases knowledge base.
    """
    new_case_id = f"CASE-{uuid.uuid4().hex[:6].upper()}"

    # 1. Insert as verified historical case
    db.execute_write(
        "INSERT INTO maintenance_cases (case_id, machine_id, subsystem, component, failure_mode, symptom, inspection_finding, repair_action, outcome, operating_hours, is_verified, source_type) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 'verified_field_diagnosis')" if db.use_mysql else
        "INSERT INTO maintenance_cases (case_id, machine_id, subsystem, component, failure_mode, symptom, inspection_finding, repair_action, outcome, operating_hours, is_verified, source_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'verified_field_diagnosis')",
        (
            new_case_id,
            req.machine_id,
            "Hydraulic System",
            req.component,
            req.failure_mode,
            req.symptoms,
            req.actual_finding,
            req.repair_performed,
            req.outcome,
            7000,
        )
    )

    # 2. Update diagnosis status if diagnosis_id supplied
    if req.diagnosis_id:
        db.execute_write(
            "UPDATE diagnoses SET verified_by_tech = 1, actual_cause_confirmed = %s WHERE diagnosis_id = %s" if db.use_mysql else
            "UPDATE diagnoses SET verified_by_tech = 1, actual_cause_confirmed = ? WHERE diagnosis_id = ?",
            (req.failure_mode, req.diagnosis_id)
        )

    return {
        "status": "success",
        "message": f"Technician confirmed finding preserved as new knowledge case {new_case_id}",
        "case_id": new_case_id
    }
