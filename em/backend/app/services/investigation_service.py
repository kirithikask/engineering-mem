"""
Investigation memory (brief §3 features 4, 5 and 7; §18).

A diagnosis in this platform is not a one-shot answer: it is an investigation
session with a chronological, database-backed timeline. Every recorded finding
changes the evidence set, and the system re-runs retrieval when a finding that
can change the picture is entered.

What this module owns:

* investigation sessions, findings (checked / found / ruled out) and the timeline;
* repair attempts, including FAILED attempts, which are retained as first-class
  engineering evidence and surfaced during future diagnosis;
* re-evaluation: hybrid retrieval + grounded reasoning over the accumulated
  evidence, with the next-best-inspection ranking and approved safety guidance;
* verification of a completed repair and the closed-loop case draft handoff to
  the knowledge service;
* photo evidence: stored and linked to the investigation, with the component
  suggestion and the explicit limits of what was and was not analysed.

Nothing in here fabricates measurements, cases or confidence values. Where a
capability does not exist locally (there is no vision model in this build) the
API says so in the payload rather than inventing an answer.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from backend.app.db.mysql_client import db
from backend.app.services.audit_service import audit_service
from backend.app.services.evidence_reasoning import evidence_reasoning
from backend.app.services.knowledge_service import knowledge_service
from backend.app.services.next_inspection import next_inspection_engine
from backend.app.services.retrieval_service import retrieval_service
from backend.app.utils.multimodal_chunker import detect_component

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover
    Image = None  # type: ignore

EVIDENCE_DIR = os.getenv("EM_EVIDENCE_DIR", "data/evidence")

# Findings of these kinds can change the evidence set, so retrieval is re-run.
RE_EVALUATION_KINDS = {"measurement", "inspection", "observation", "photo", "note"}

STATUS_OPEN = "OPEN"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_VERIFIED = "VERIFIED"
STATUS_CLOSED = "CLOSED"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _json(value: Any) -> str:
    import json

    try:
        return json.dumps(value, default=str)
    except Exception:
        return "{}"


def _loads(value: Any, fallback: Any) -> Any:
    import json

    try:
        return json.loads(value) if value else fallback
    except Exception:
        return fallback


class InvestigationService:
    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------
    def create(
        self,
        *,
        machine_id: str,
        title: str,
        problem_statement: str,
        symptoms: List[str],
        subsystem: Optional[str],
        severity: str,
        user: Dict[str, Any],
    ) -> Dict[str, Any]:
        year = datetime.now(timezone.utc).year
        existing = db.execute_query("SELECT COUNT(*) AS n FROM investigations")
        sequence = int(existing[0]["n"]) + 1 if existing else 1
        investigation_id = f"INV-{year}-{sequence:04d}"

        machine = self._machine(machine_id)
        db.execute_write(
            "INSERT INTO investigations (investigation_id, machine_id, title, problem_statement, symptoms_json, subsystem, "
            "severity, status, opened_by, opened_by_name, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
            "INSERT INTO investigations (investigation_id, machine_id, title, problem_statement, symptoms_json, subsystem, "
            "severity, status, opened_by, opened_by_name, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                investigation_id,
                machine_id,
                title,
                problem_statement,
                _json(symptoms),
                subsystem or "Hydraulic System",
                severity.upper(),
                STATUS_OPEN,
                user.get("user_id"),
                user.get("full_name") or user.get("username"),
                _now(),
            ),
        )
        self.add_event(
            investigation_id=investigation_id,
            event_type="OPENED",
            summary=f"Fault reported: {problem_statement or title}",
            user=user,
            payload={"symptoms": symptoms, "machine_model": machine.get("machine_model"), "severity": severity},
        )
        audit_service.record(
            user=user,
            action="INVESTIGATION_CREATED",
            entity_type="investigation",
            entity_id=investigation_id,
            machine_id=machine_id,
            investigation_id=investigation_id,
            detail={"title": title, "symptoms": symptoms},
        )
        return self.get(investigation_id)

    def get(self, investigation_id: str) -> Dict[str, Any]:
        rows = db.execute_query(
            "SELECT * FROM investigations WHERE investigation_id = {} ".format("%s" if db.use_mysql else "?"),
            (investigation_id,),
        )
        if not rows:
            return {"investigation": None}
        investigation = rows[0]
        investigation["symptoms"] = _loads(investigation.get("symptoms_json"), [])
        investigation["verification"] = _loads(investigation.get("verification_json"), None)
        return {
            "investigation": investigation,
            "machine": self._machine(investigation["machine_id"]),
            "findings": self.findings(investigation_id),
            "events": self.timeline(investigation_id),
            "attempts": self.attempts(investigation_id),
            "photos": self.photos(investigation_id),
            "situation": self.situation(investigation_id),
        }

    def list(
        self,
        *,
        machine_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        placeholder = "%s" if db.use_mysql else "?"
        conditions, params = [], []
        if machine_id:
            conditions.append(f"machine_id = {placeholder}")
            params.append(machine_id)
        if status:
            conditions.append(f"status = {placeholder}")
            params.append(status)
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        rows = db.execute_query(
            "SELECT investigation_id, machine_id, title, problem_statement, symptoms_json, subsystem, severity, status, "
            "opened_by_name, opened_at, closed_at, root_cause, failed_attempt_count, knowledge_id, confidence "
            f"FROM investigations{where} ORDER BY opened_at DESC LIMIT {int(limit)}",
            tuple(params),
        )
        for row in rows:
            row["symptoms"] = _loads(row.get("symptoms_json"), [])
        return rows

    # ------------------------------------------------------------------
    # Findings and re-evaluation
    # ------------------------------------------------------------------
    def add_finding(self, *, investigation_id: str, payload: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
        investigation = self._require(investigation_id)
        if investigation is None:
            return {"status": "error", "detail": "Investigation not found."}

        finding_id = f"FND-{uuid.uuid4().hex[:8].upper()}"
        seq_rows = db.execute_query(
            "SELECT COUNT(*) AS n FROM investigation_findings WHERE investigation_id = {} ".format(
                "%s" if db.use_mysql else "?"
            ),
            (investigation_id,),
        )
        seq = int(seq_rows[0]["n"]) + 1 if seq_rows else 1
        kind = (payload.get("kind") or "inspection").lower()
        title = (payload.get("title") or "").strip() or f"{kind} recorded"
        ruling = (payload.get("ruling") or "PENDING").upper()

        db.execute_write(
            "INSERT INTO investigation_findings (finding_id, investigation_id, seq, kind, title, detail, value, unit, "
            "component, subsystem, source, quality_level, ruling, evidence_json, created_by, created_by_name) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
            "INSERT INTO investigation_findings (finding_id, investigation_id, seq, kind, title, detail, value, unit, "
            "component, subsystem, source, quality_level, ruling, evidence_json, created_by, created_by_name) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                finding_id,
                investigation_id,
                seq,
                kind,
                title[:250],
                payload.get("detail"),
                str(payload.get("value") or "") or None,
                payload.get("unit"),
                payload.get("component") or detect_component(title, payload.get("detail")),
                payload.get("subsystem") or investigation.get("subsystem"),
                payload.get("source") or "field measurement",
                "TECHNICIAN_SUBMITTED",
                ruling,
                _json(payload.get("evidence") or {}),
                user.get("user_id"),
                user.get("full_name") or user.get("username"),
            ),
        )

        measured = f" = {payload.get('value')} {payload.get('unit') or ''}".rstrip() if payload.get("value") else ""
        self.add_event(
            investigation_id=investigation_id,
            event_type="FINDING",
            summary=f"{title}{measured} → {ruling}",
            user=user,
            payload={"finding_id": finding_id, "kind": kind, "ruling": ruling},
        )
        db.execute_write(
            "UPDATE investigations SET status = %s, updated_at = %s WHERE investigation_id = %s AND status = %s"
            if db.use_mysql else
            "UPDATE investigations SET status = ?, updated_at = ? WHERE investigation_id = ? AND status = ?",
            (STATUS_IN_PROGRESS, _now(), investigation_id, STATUS_OPEN),
        )

        re_evaluation = None
        if kind in RE_EVALUATION_KINDS:
            re_evaluation = self.re_evaluate(investigation_id, user=user, trigger=f"finding:{finding_id}")

        audit_service.record(
            user=user,
            action="FINDING_RECORDED",
            entity_type="finding",
            entity_id=finding_id,
            machine_id=investigation["machine_id"],
            investigation_id=investigation_id,
            detail={"title": title, "ruling": ruling, "value": payload.get("value"), "unit": payload.get("unit")},
        )

        return {
            "status": "ok",
            "finding_id": finding_id,
            "seq": seq,
            "re_evaluation": re_evaluation,
            "situation": self.situation(investigation_id),
        }

    def re_evaluate(self, investigation_id: str, *, user: Optional[Dict[str, Any]] = None, trigger: str = "manual") -> Dict[str, Any]:
        """Re-run hybrid retrieval over the accumulated evidence and store the snapshot."""
        investigation = self._require(investigation_id)
        if investigation is None:
            return {"status": "error", "detail": "Investigation not found."}

        findings = self.findings(investigation_id)
        attempts = self.attempts(investigation_id)
        symptoms = _loads(investigation.get("symptoms_json"), [])
        query_parts = list(symptoms)
        for finding in findings:
            text = f"{finding.get('title')} {finding.get('detail') or ''}".strip()
            if finding.get("value"):
                text += f" {finding.get('value')} {finding.get('unit') or ''}"
            if text:
                query_parts.append(text)

        result = retrieval_service.search_text(
            query_parts,
            top_k=8,
            user=user,
            machine_id=investigation["machine_id"],
            investigation_id=investigation_id,
        )
        sufficiency = evidence_reasoning.assess_sufficiency(result["evidence"], query=" ".join(query_parts))
        next_checks = next_inspection_engine.rank(
            evidence=result["evidence"],
            findings=findings,
            failed_attempts=[a for a in attempts if not a.get("was_successful")],
        )
        snapshot = {
            "trigger": trigger,
            "at": _now(),
            "query_parts": query_parts,
            "evidence_sufficiency": sufficiency["level"],
            "sufficiency_reason": sufficiency["reason"],
            "top_evidence": [
                {
                    "id": item.get("id"),
                    "title": item.get("title") or item.get("document_name"),
                    "component": item.get("component"),
                    "similarity": item.get("similarity"),
                    "effective_score": item.get("effective_score"),
                    "quality_level": item.get("quality_level"),
                    "document_status": item.get("document_status"),
                }
                for item in result["evidence"][:8]
            ],
            "next_inspection": next_checks,
            "conflicts": result["conflicts"],
            "latency_ms": result["timings"]["latency_ms"],
            "retrieval_id": result.get("retrieval_id"),
        }
        db.execute_write(
            "UPDATE investigations SET evidence_snapshot_json = %s, confidence = %s, updated_at = %s "
            "WHERE investigation_id = %s" if db.use_mysql else
            "UPDATE investigations SET evidence_snapshot_json = ?, confidence = ?, updated_at = ? "
            "WHERE investigation_id = ?",
            (_json(snapshot), sufficiency["level"], _now(), investigation_id),
        )
        self.add_event(
            investigation_id=investigation_id,
            event_type="RE_EVALUATION",
            summary=(
                f"Evidence re-evaluated ({trigger}): {len(result['evidence'])} sources, "
                f"sufficiency {sufficiency['level']}"
            ),
            user=user,
            payload={k: snapshot[k] for k in ("evidence_sufficiency", "sufficiency_reason", "retrieval_id", "latency_ms")},
        )
        self._warn_failed_attempts(investigation_id, findings, attempts, user=user)

        return {
            "status": "ok",
            "evidence_sufficiency": sufficiency["level"],
            "sufficiency_reason": sufficiency["reason"],
            "evidence": result["evidence"],
            "next_best_inspection": next_checks,
            "conflicts": result["conflicts"],
            "timings": result["timings"],
            "snapshot": snapshot,
        }

    # ------------------------------------------------------------------
    # Repair attempts (failed repair memory)
    # ------------------------------------------------------------------
    def add_attempt(self, *, investigation_id: str, payload: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
        investigation = self._require(investigation_id)
        if investigation is None:
            return {"status": "error", "detail": "Investigation not found."}

        result_value = (payload.get("result") or "UNKNOWN").upper()
        successful = 1 if result_value in ("RESOLVED", "SUCCESSFUL", "FIXED") else 0
        attempt_id = f"ATT-{uuid.uuid4().hex[:8].upper()}"
        symptom_text = payload.get("symptom") or investigation.get("problem_statement") or ""

        db.execute_write(
            "INSERT INTO repair_attempts (attempt_id, investigation_id, machine_id, symptom_text, action_taken, component, "
            "failure_mode, result, was_successful, technician_note, created_by, created_by_name) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
            "INSERT INTO repair_attempts (attempt_id, investigation_id, machine_id, symptom_text, action_taken, component, "
            "failure_mode, result, was_successful, technician_note, created_by, created_by_name) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                attempt_id,
                investigation_id,
                investigation["machine_id"],
                symptom_text,
                payload.get("action_taken") or payload.get("action") or "action not described",
                payload.get("component") or detect_component(str(payload.get("action_taken") or "")),
                payload.get("failure_mode"),
                result_value,
                successful,
                payload.get("note"),
                user.get("user_id"),
                user.get("full_name") or user.get("username"),
            ),
        )
        if not successful:
            db.execute_write(
                "UPDATE investigations SET failed_attempt_count = failed_attempt_count + 1, updated_at = %s "
                "WHERE investigation_id = %s" if db.use_mysql else
                "UPDATE investigations SET failed_attempt_count = failed_attempt_count + 1, updated_at = ? "
                "WHERE investigation_id = ?",
                (_now(), investigation_id),
            )

        self.add_event(
            investigation_id=investigation_id,
            event_type="REPAIR_ATTEMPT",
            summary=(
                f"{payload.get('action_taken')} → "
                + ("problem resolved" if successful else "problem persisted")
            ),
            user=user,
            payload={"attempt_id": attempt_id, "result": result_value},
        )
        audit_service.record(
            user=user,
            action="REPAIR_ATTEMPT_RECORDED",
            entity_type="repair_attempt",
            entity_id=attempt_id,
            machine_id=investigation["machine_id"],
            investigation_id=investigation_id,
            detail={"action": payload.get("action_taken"), "result": result_value},
        )

        return {
            "status": "ok",
            "attempt_id": attempt_id,
            "was_successful": bool(successful),
            "historical_attempts": self.similar_attempts(
                component=payload.get("component"), symptom_text=symptom_text, exclude_attempt_id=attempt_id
            ),
        }

    def similar_attempts(
        self,
        *,
        component: Optional[str] = None,
        symptom_text: Optional[str] = None,
        exclude_attempt_id: Optional[str] = None,
        limit: int = 6,
    ) -> Dict[str, Any]:
        """Historical attempts on comparable symptoms, successes and failures alike."""
        rows = db.execute_query(
            "SELECT attempt_id, investigation_id, machine_id, symptom_text, action_taken, component, failure_mode, "
            "result, was_successful, technician_note, created_at FROM repair_attempts ORDER BY created_at DESC LIMIT 400"
        )
        words = {w for w in str(symptom_text or "").lower().split() if len(w) > 3}
        scored = []
        for row in rows:
            if exclude_attempt_id and row["attempt_id"] == exclude_attempt_id:
                continue
            score = 0.0
            if component and component.lower() in str(row.get("component") or "").lower():
                score += 2.0
            overlap = words & {w for w in str(row.get("symptom_text") or "").lower().split() if len(w) > 3}
            score += 0.5 * len(overlap)
            if score > 0:
                scored.append((score, row))
        scored.sort(key=lambda pair: pair[0], reverse=True)

        failed = [
            {**row, "label": f"{row['action_taken']} — unsuccessful"}
            for _, row in scored
            if not row.get("was_successful")
        ][:limit]
        succeeded = [
            {**row, "label": f"{row['action_taken']} — successful"}
            for _, row in scored
            if row.get("was_successful")
        ][:limit]

        warning = None
        if failed:
            warning = (
                "Similar historical cases indicate this action was previously attempted without resolving the "
                "symptom. This is presented as historical evidence, not as a judgement about the planned repair."
            )
        return {
            "failed_attempts": failed,
            "successful_attempts": succeeded,
            "warning": warning,
            "search_basis": {
                "component": component,
                "symptom_terms": sorted(words),
                "records_scanned": len(rows),
            },
        }

    def _warn_failed_attempts(
        self,
        investigation_id: str,
        findings: List[Dict[str, Any]],
        attempts: List[Dict[str, Any]],
        *,
        user: Optional[Dict[str, Any]],
    ) -> None:
        component = next((f.get("component") for f in findings if f.get("component")), None)
        if not component:
            return
        history = self.similar_attempts(component=component, symptom_text="")
        if not history["failed_attempts"]:
            return
        action_ids = {a.get("action_taken") for a in attempts}
        new_failures = [f for f in history["failed_attempts"] if f.get("action_taken") not in action_ids]
        if not new_failures:
            return
        self.add_event(
            investigation_id=investigation_id,
            event_type="FAILED_ATTEMPT_WARNING",
            summary=(
                f"{len(new_failures)} historical attempt(s) on {component} did not resolve a comparable symptom: "
                + "; ".join(str(item.get("action_taken"))[:80] for item in new_failures[:3])
            ),
            user=user,
            payload={"attempts": new_failures[:3]},
        )

    # ------------------------------------------------------------------
    # Diagnosis over the accumulated evidence
    # ------------------------------------------------------------------
    def diagnose(self, *, investigation_id: str, user: Dict[str, Any], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        investigation = self._require(investigation_id)
        if investigation is None:
            return {"status": "error", "detail": "Investigation not found."}

        findings = self.findings(investigation_id)
        attempts = self.attempts(investigation_id)
        symptoms = _loads(investigation.get("symptoms_json"), [])
        machine = self._machine(investigation["machine_id"])

        observations: Dict[str, Any] = {}
        for finding in findings:
            if finding.get("value"):
                observations[finding.get("title")] = f"{finding.get('value')} {finding.get('unit') or ''}".strip()
        if extra:
            observations.update(extra)

        self.add_event(
            investigation_id=investigation_id,
            event_type="AI_RETRIEVAL",
            summary="Evidence retrieval started over the recorded symptom set and findings",
            user=user,
        )

        retrieval = retrieval_service.search_text(
            symptoms + [f"{f.get('title')} {f.get('detail') or ''}" for f in findings],
            top_k=8,
            user=user,
            machine_id=investigation["machine_id"],
            investigation_id=investigation_id,
        )
        evidence = retrieval["evidence"]
        conflicts = retrieval["conflicts"]

        failed = [a for a in attempts if not a.get("was_successful")]
        succeeded = [a for a in attempts if a.get("was_successful")]

        diagnosis = evidence_reasoning.reason(
            machine_id=investigation["machine_id"],
            investigation_id=investigation_id,
            symptoms=symptoms,
            observations=observations,
            evidence=evidence,
            findings=findings,
            failed_attempts=failed,
            successful_resolutions=succeeded,
            conflicts=conflicts,
            machine=machine,
            sensor_findings=None,
        )
        diagnosis["retrieval_id"] = retrieval.get("retrieval_id")
        diagnosis["timings"] = {**retrieval["timings"], **diagnosis.get("timings", {})}

        next_checks = next_inspection_engine.rank(
            evidence=evidence, findings=findings, failed_attempts=failed
        )
        safety = knowledge_service.safety_for(
            component=(next_checks[0]["component"] if next_checks else None) or (diagnosis.get("affected_component")),
            task=(next_checks[0].get("safety_task") if next_checks else None),
        )
        attempts_history = self.similar_attempts(
            component=(next_checks[0]["component"] if next_checks else None),
            symptom_text=investigation.get("problem_statement") or "",
        )

        diagnosis["next_best_inspection"] = next_checks
        diagnosis["safety"] = safety
        diagnosis["historical_attempts"] = attempts_history
        diagnosis["conflicting_evidence"] = conflicts

        self.add_event(
            investigation_id=investigation_id,
            event_type="AI_RECOMMENDATION",
            summary=(
                f"Grounded reasoning complete: sufficiency {diagnosis.get('evidence_sufficiency')}, "
                f"confidence {diagnosis.get('confidence')}"
                + (f", top cause: {diagnosis['likely_causes'][0]['cause']}" if diagnosis.get("likely_causes") else
                   ", no cause asserted")
            ),
            user=user,
            payload={
                "likely_causes": diagnosis.get("likely_causes"),
                "evidence_sufficiency": diagnosis.get("evidence_sufficiency"),
                "next_inspection": [item.get("inspection") for item in next_checks[:3]],
                "reasoning_status": diagnosis.get("reasoning_status"),
                "timings": diagnosis.get("timings"),
                "unverified_citations": diagnosis.get("unverified_citations"),
            },
        )

        if diagnosis.get("likely_causes"):
            db.execute_write(
                "UPDATE investigations SET root_cause = %s, confidence = %s, updated_at = %s WHERE investigation_id = %s"
                if db.use_mysql else
                "UPDATE investigations SET root_cause = ?, confidence = ?, updated_at = ? WHERE investigation_id = ?",
                (
                    diagnosis["likely_causes"][0]["cause"][:250],
                    diagnosis.get("confidence"),
                    _now(),
                    investigation_id,
                ),
            )

        audit_service.record(
            user=user,
            action="DIAGNOSIS_RUN",
            entity_type="investigation",
            entity_id=investigation_id,
            machine_id=investigation["machine_id"],
            investigation_id=investigation_id,
            detail={
                "evidence_sufficiency": diagnosis.get("evidence_sufficiency"),
                "confidence": diagnosis.get("confidence"),
                "evidence_ids": [item.get("id") for item in evidence[:5]],
                "retrieval_id": retrieval.get("retrieval_id"),
                "reasoning_status": diagnosis.get("reasoning_status"),
            },
        )
        return diagnosis

    # ------------------------------------------------------------------
    # Verification and closure
    # ------------------------------------------------------------------
    def verify(self, *, investigation_id: str, payload: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
        investigation = self._require(investigation_id)
        if investigation is None:
            return {"status": "error", "detail": "Investigation not found."}

        checks = payload.get("checks") or []
        passed = 1 if checks and all(bool(c.get("passed")) for c in checks) else 0
        verification_id = f"VRF-{uuid.uuid4().hex[:8].upper()}"
        db.execute_write(
            "INSERT INTO repair_verifications (verification_id, investigation_id, checks_json, passed, notes, "
            "verified_by, verified_by_name) VALUES (%s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
            "INSERT INTO repair_verifications (verification_id, investigation_id, checks_json, passed, notes, "
            "verified_by, verified_by_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                verification_id,
                investigation_id,
                _json(checks),
                passed,
                payload.get("notes"),
                user.get("user_id"),
                user.get("full_name") or user.get("username"),
            ),
        )
        db.execute_write(
            "UPDATE investigations SET status = %s, verification_json = %s, closed_at = %s, updated_at = %s "
            "WHERE investigation_id = %s" if db.use_mysql else
            "UPDATE investigations SET status = ?, verification_json = ?, closed_at = ?, updated_at = ? "
            "WHERE investigation_id = ?",
            (
                STATUS_VERIFIED if passed else STATUS_IN_PROGRESS,
                _json({"checks": checks, "passed": bool(passed), "notes": payload.get("notes"), "at": _now()}),
                _now() if passed else None,
                _now(),
                investigation_id,
            ),
        )
        if payload.get("root_cause"):
            db.execute_write(
                "UPDATE investigations SET root_cause = %s WHERE investigation_id = %s" if db.use_mysql else
                "UPDATE investigations SET root_cause = ? WHERE investigation_id = ?",
                (payload["root_cause"][:250], investigation_id),
            )
        if payload.get("repair_summary"):
            db.execute_write(
                "UPDATE investigations SET repair_summary = %s WHERE investigation_id = %s" if db.use_mysql else
                "UPDATE investigations SET repair_summary = ? WHERE investigation_id = ?",
                (payload["repair_summary"], investigation_id),
            )

        self.add_event(
            investigation_id=investigation_id,
            event_type="VERIFICATION",
            summary=(
                ("Verification passed: " if passed else "Verification not passed: ")
                + "; ".join(str(c.get("label")) for c in checks)[:300]
            ),
            user=user,
            payload={"checks": checks, "passed": bool(passed)},
        )
        audit_service.record(
            user=user,
            action="REPAIR_VERIFIED" if passed else "VERIFICATION_INCOMPLETE",
            entity_type="investigation",
            entity_id=investigation_id,
            machine_id=investigation["machine_id"],
            investigation_id=investigation_id,
            detail={"checks": checks, "notes": payload.get("notes")},
        )
        return {
            "status": "ok",
            "verification_id": verification_id,
            "passed": bool(passed),
            "investigation": self._require(investigation_id),
        }

    def create_knowledge(
        self, *, investigation_id: str, payload: Dict[str, Any], user: Dict[str, Any]
    ) -> Dict[str, Any]:
        investigation = self._require(investigation_id)
        if investigation is None:
            return {"status": "error", "detail": "Investigation not found."}

        draft = knowledge_service.upsert_case_draft(
            investigation=investigation,
            symptom_text=investigation.get("problem_statement") or "",
            user=user,
            overrides=payload or {},
        )
        self.add_event(
            investigation_id=investigation_id,
            event_type="CASE_DRAFT",
            summary=f"Case report drafted as {draft['knowledge_id']} (pending expert review)",
            user=user,
            payload={"knowledge_id": draft["knowledge_id"], "status": draft["status"]},
        )
        audit_service.record(
            user=user,
            action="CASE_DRAFT_CREATED",
            entity_type="knowledge_item",
            entity_id=draft["knowledge_id"],
            machine_id=investigation["machine_id"],
            investigation_id=investigation_id,
            detail={"title": draft.get("title")},
        )
        return {
            "status": "ok",
            "knowledge_id": draft["knowledge_id"],
            "knowledge_status": draft["status"],
            "quality_level": draft["quality_level"],
            "draft": draft["draft"],
            "title": draft["title"],
            "content": draft["content"],
            "message": "Case draft generated. Submit it for expert review to add it to the Engineering Memory.",
        }

    def close(self, *, investigation_id: str, payload: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
        investigation = self._require(investigation_id)
        if investigation is None:
            return {"status": "error", "detail": "Investigation not found."}
        db.execute_write(
            "UPDATE investigations SET status = %s, root_cause = COALESCE(%s, root_cause), "
            "root_cause_detail = COALESCE(%s, root_cause_detail), repair_summary = COALESCE(%s, repair_summary), "
            "closed_at = %s, updated_at = %s WHERE investigation_id = %s" if db.use_mysql else
            "UPDATE investigations SET status = ?, root_cause = COALESCE(?, root_cause), "
            "root_cause_detail = COALESCE(?, root_cause_detail), repair_summary = COALESCE(?, repair_summary), "
            "closed_at = ?, updated_at = ? WHERE investigation_id = ?",
            (
                STATUS_CLOSED,
                payload.get("root_cause"),
                payload.get("root_cause_detail"),
                payload.get("repair_summary"),
                _now(),
                _now(),
                investigation_id,
            ),
        )
        self.add_event(
            investigation_id=investigation_id,
            event_type="CLOSED",
            summary=f"Investigation closed. Root cause: {payload.get('root_cause') or investigation.get('root_cause')}",
            user=user,
        )
        audit_service.record(
            user=user,
            action="INVESTIGATION_CLOSED",
            entity_type="investigation",
            entity_id=investigation_id,
            machine_id=investigation["machine_id"],
            investigation_id=investigation_id,
            detail=payload,
        )
        return {"status": "ok", "investigation": self._require(investigation_id)}

    # ------------------------------------------------------------------
    # Photo evidence (brief §3 feature 3, §17)
    # ------------------------------------------------------------------
    def add_photo(self, *, investigation_id: str, payload: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
        investigation = self._require(investigation_id)
        if investigation is None:
            return {"status": "error", "detail": "Investigation not found."}

        os.makedirs(EVIDENCE_DIR, exist_ok=True)
        photo_id = f"PHO-{uuid.uuid4().hex[:8].upper()}"
        filename = payload.get("filename") or "photo.jpg"
        # The uploader writes the file and passes its path; falling back to the
        # conventional location keeps direct service calls working too.
        save_path = payload.get("path") or os.path.join(EVIDENCE_DIR, f"{photo_id}_{filename}")

        analysis = (
            self._analyse_image(save_path)
            if os.path.exists(save_path)
            else {"available": False, "detail": "Image file not found on disk."}
        )
        component_context = self._component_context(investigation_id)
        suggestion = self._suggest_component(
            filename=filename,
            caption=payload.get("caption"),
            context_components=component_context,
            confirmed=payload.get("component"),
        )

        related = retrieval_service.search(
            f"{suggestion['component']} inspection failure repair",
            filters={"component": suggestion["component"]} if suggestion["component"] else None,
            top_k=5,
            user=user,
            machine_id=investigation["machine_id"],
            investigation_id=investigation_id,
        ) if suggestion["component"] else {"evidence": [], "conflicts": [], "timings": {"latency_ms": 0.0}}

        db.execute_write(
            "INSERT INTO photo_evidence (photo_id, investigation_id, machine_id, file_path, original_filename, caption, "
            "component_suggested, component_confirmed, visual_match, image_analysis_json, related_knowledge_json, created_by) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
            "INSERT INTO photo_evidence (photo_id, investigation_id, machine_id, file_path, original_filename, caption, "
            "component_suggested, component_confirmed, visual_match, image_analysis_json, related_knowledge_json, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                photo_id,
                investigation_id,
                investigation["machine_id"],
                save_path,
                filename,
                payload.get("caption"),
                suggestion["component"],
                payload.get("component"),
                suggestion["visual_match"],
                _json(analysis),
                _json([{"id": e.get("id"), "title": e.get("title")} for e in related.get("evidence", [])]),
                user.get("user_id"),
            ),
        )
        self.add_event(
            investigation_id=investigation_id,
            event_type="PHOTO",
            summary=f"Photo evidence added: {filename}"
            + (f" — suggested component: {suggestion['component']}" if suggestion["component"] else " — component not determined"),
            user=user,
            payload={"photo_id": photo_id, "visual_match": suggestion["visual_match"]},
        )
        audit_service.record(
            user=user,
            action="PHOTO_EVIDENCE_ADDED",
            entity_type="photo_evidence",
            entity_id=photo_id,
            machine_id=investigation["machine_id"],
            investigation_id=investigation_id,
            detail={"filename": filename, "component": suggestion["component"], "visual_match": suggestion["visual_match"]},
        )

        return {
            "status": "ok",
            "photo_id": photo_id,
            "detected_component": suggestion["component"],
            "component_confirmed": payload.get("component"),
            "visual_match": suggestion["visual_match"],
            "identification_basis": suggestion["basis"],
            "requires_manual_selection": suggestion["component"] is None,
            "image_analysis": analysis,
            "related_knowledge": related.get("evidence", []),
            "conflicts": related.get("conflicts", []),
        }

    def correct_photo(self, *, photo_id: str, component: str, user: Dict[str, Any]) -> Dict[str, Any]:
        rows = db.execute_query(
            "SELECT photo_id, investigation_id, machine_id FROM photo_evidence WHERE photo_id = {} ".format(
                "%s" if db.use_mysql else "?"
            ),
            (photo_id,),
        )
        if not rows:
            return {"status": "error", "detail": "Photo not found."}
        row = rows[0]
        db.execute_write(
            "UPDATE photo_evidence SET component_confirmed = %s, visual_match = 'MANUALLY_CONFIRMED' "
            "WHERE photo_id = %s" if db.use_mysql else
            "UPDATE photo_evidence SET component_confirmed = ?, visual_match = 'MANUALLY_CONFIRMED' "
            "WHERE photo_id = ?",
            (component, photo_id),
        )
        self.add_event(
            investigation_id=row["investigation_id"],
            event_type="PHOTO_CORRECTION",
            summary=f"Component manually corrected to {component} for photo {photo_id}",
            user=user,
        )
        audit_service.record(
            user=user,
            action="PHOTO_COMPONENT_CORRECTED",
            entity_type="photo_evidence",
            entity_id=photo_id,
            machine_id=row["machine_id"],
            investigation_id=row["investigation_id"],
            detail={"component": component},
        )
        return {"status": "ok", "photo_id": photo_id, "component_confirmed": component}

    def _analyse_image(self, path: str) -> Dict[str, Any]:
        """Real pixel measurements only: size, focus, exposure, contrast."""
        if Image is None:
            return {"available": False, "detail": "Image analysis library not available."}
        try:
            with Image.open(path) as image:
                width, height = image.size
                gray = image.convert("L")
                array = np.asarray(gray, dtype=np.float32)
        except Exception as exc:
            return {"available": False, "detail": f"Image could not be decoded: {exc}"}

        if array.shape[0] < 3 or array.shape[1] < 3:
            return {"available": False, "detail": "Image too small to analyse."}

        laplacian = (
            array[:-2, 1:-1]
            + array[2:, 1:-1]
            + array[1:-1, :-2]
            + array[1:-1, 2:]
            - 4.0 * array[1:-1, 1:-1]
        )
        focus_variance = float(laplacian.var())
        brightness = float(array.mean())
        contrast = float(array.std())

        flags = []
        if focus_variance < 40:
            flags.append("possibly_out_of_focus")
        if brightness < 60:
            flags.append("under_exposed")
        elif brightness > 200:
            flags.append("over_exposed")
        if contrast < 15:
            flags.append("low_contrast")

        return {
            "available": True,
            "width": width,
            "height": height,
            "focus_variance": round(focus_variance, 2),
            "mean_brightness": round(brightness, 2),
            "contrast": round(contrast, 2),
            "quality_flags": flags,
            "method": "pixel statistics (Laplacian variance, luminance statistics) computed locally",
            "vision_model": None,
            "note": (
                "No local vision/classification model is configured in this build. These are measured image "
                "statistics, not a visual diagnosis of the component."
            ),
        }

    def _component_context(self, investigation_id: str) -> List[str]:
        findings = self.findings(investigation_id)
        components = [f.get("component") for f in findings if f.get("component")]
        investigation = self._require(investigation_id) or {}
        snapshot = _loads(investigation.get("evidence_snapshot_json"), {}) or {}
        for item in snapshot.get("top_evidence", []) or []:
            if item.get("component"):
                components.append(item["component"])
        seen, ordered = set(), []
        for component in components:
            key = str(component).lower()
            if key in seen or key in ("hydraulic system", ""):
                continue
            seen.add(key)
            ordered.append(str(component))
        return ordered

    def _suggest_component(
        self,
        *,
        filename: str,
        caption: Optional[str],
        context_components: List[str],
        confirmed: Optional[str],
    ) -> Dict[str, Any]:
        if confirmed:
            return {
                "component": confirmed,
                "visual_match": "MANUALLY_CONFIRMED",
                "basis": "Component supplied by the technician; no automatic identification was used.",
            }

        text = " ".join(filter(None, [caption, filename]))
        detected = detect_component(text) if text.strip() else "Hydraulic System"
        if detected != "Hydraulic System":
            return {
                "component": detected,
                "visual_match": "MEDIUM",
                "basis": (
                    "Matched from the text you supplied (caption/file name), not from image content: no local vision "
                    "model is configured in this build."
                ),
            }
        if len(context_components) == 1:
            return {
                "component": context_components[0],
                "visual_match": "LOW",
                "basis": (
                    "Inferred from this investigation's recorded component context, not from image content. "
                    "Confirm or correct the component."
                ),
            }
        return {
            "component": None,
            "visual_match": "UNDETERMINED",
            "basis": (
                "Component identification uncertain. No local vision model is configured and neither the caption nor "
                "the investigation context identifies a single component. Please select the component manually."
            ),
        }

    # ------------------------------------------------------------------
    # Machine passport (brief §3 feature 2, §13)
    # ------------------------------------------------------------------
    def machine_passport(self, machine_id: str, *, base_url: Optional[str] = None, user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        machine = self._machine(machine_id)
        if not machine:
            return {"status": "error", "detail": "Machine not found."}

        cases = db.execute_query(
            "SELECT case_id, subsystem, component, failure_mode, symptom, inspection_finding, repair_action, outcome, "
            "operating_hours, source_type, created_at FROM maintenance_cases WHERE machine_id = {} "
            "ORDER BY created_at DESC LIMIT 50".format("%s" if db.use_mysql else "?"),
            (machine_id,),
        )
        diagnoses = db.execute_query(
            "SELECT diagnosis_id, created_at, symptoms_analyzed, evidence_sufficiency, likely_cause, affected_component, "
            "confidence_score, verified_by_tech FROM diagnoses WHERE machine_id = {} ORDER BY created_at DESC LIMIT 20".format(
                "%s" if db.use_mysql else "?"
            ),
            (machine_id,),
        )
        investigations = self.list(machine_id=machine_id, limit=50)
        attempts = db.execute_query(
            "SELECT attempt_id, investigation_id, action_taken, component, result, was_successful, created_at "
            "FROM repair_attempts WHERE machine_id = {} ORDER BY created_at DESC LIMIT 50".format(
                "%s" if db.use_mysql else "?"
            ),
            (machine_id,),
        )
        documents = db.execute_query(
            "SELECT DISTINCT d.document_id, d.document_name, d.document_type, d.status, d.version, "
            "v.revision, v.status AS version_status, v.extraction_confidence "
            "FROM documents d LEFT JOIN document_versions v ON v.document_id = d.document_id "
            "ORDER BY d.created_at DESC LIMIT 30"
        )
        components = db.execute_query(
            "SELECT component_id, component_name, subsystem, mesh_name, description FROM components"
        )
        sensor_rows = db.execute_query(
            "SELECT record_id, timestamp, ps1_mean, ps2_mean, ps3_mean, ts1_mean, ts2_mean, cooler_condition, "
            "valve_condition, pump_leakage, accumulator_pressure, stable FROM sensor_records WHERE machine_id = {} "
            "ORDER BY timestamp DESC LIMIT 60".format("%s" if db.use_mysql else "?"),
            (machine_id,),
        )
        predictions = db.execute_query(
            "SELECT pred_id, timestamp, pump_leakage_pred, pump_leakage_prob, model_version FROM model_predictions "
            "WHERE machine_id = {} ORDER BY timestamp DESC LIMIT 20".format("%s" if db.use_mysql else "?"),
            (machine_id,),
        )
        knowledge = db.execute_query(
            "SELECT knowledge_id, title, quality_level, status, created_at FROM knowledge_items WHERE machine_id = {} "
            "ORDER BY created_at DESC LIMIT 15".format("%s" if db.use_mysql else "?"),
            (machine_id,),
        )

        intervals = self._maintenance_intervals(cases)
        qr = self.qr_token(machine_id, base_url=base_url, user=user)

        return {
            "machine": machine,
            "qr": qr,
            "open_investigations": [i for i in investigations if i.get("status") in (STATUS_OPEN, STATUS_IN_PROGRESS)],
            "investigations": investigations,
            "failure_history": cases,
            "repair_history": attempts,
            "repair_success_rate": self._success_rate(attempts),
            "diagnoses": diagnoses,
            "components": components,
            "documents": documents,
            "knowledge": knowledge,
            "sensor_history": sensor_rows,
            "sensor_source_label": "HYDRAULIC TEST-RIG CONDITION MONITORING (public condition-monitoring dataset; not live excavator telemetry)",
            "model_predictions": predictions,
            "maintenance_schedule": intervals,
            "subsystem_history": self._subsystem_history(cases),
            "demo_data_notice": (
                "Prototype/demo machine records may be present in this database. Records carrying source_type "
                "'tata_industry_demo' or 'synthetic' are labelled as demo data wherever they appear."
            ),
        }

    def qr_token(self, machine_id: str, *, base_url: Optional[str] = None, user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rows = db.execute_query(
            "SELECT token, scan_count, created_at FROM machine_qr_tokens WHERE machine_id = {} AND active = 1 "
            "ORDER BY created_at DESC LIMIT 1".format("%s" if db.use_mysql else "?"),
            (machine_id,),
        )
        if rows:
            token = rows[0]["token"]
            scan_count = rows[0].get("scan_count") or 0
        else:
            token = f"MQ-{uuid.uuid4().hex[:10].upper()}"
            db.execute_write(
                "INSERT INTO machine_qr_tokens (token, machine_id, label, created_by) VALUES (%s, %s, %s, %s)"
                if db.use_mysql else
                "INSERT INTO machine_qr_tokens (token, machine_id, label, created_by) VALUES (?, ?, ?, ?)",
                (token, machine_id, f"Machine access tag {machine_id}", (user or {}).get("user_id")),
            )
            scan_count = 0

        target = f"{(base_url or '').rstrip('/')}/m/{token}"
        image_data_uri = None
        try:
            import base64
            import io

            import qrcode  # local QR generation, no external service

            qr = qrcode.QRCode(version=None, box_size=8, border=2)
            qr.add_data(target)
            qr.make(fit=True)
            buffer = io.BytesIO()
            qr.make_image(fill_color="#0B2545", back_color="#FFFFFF").save(buffer, format="PNG")
            image_data_uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
        except Exception as exc:
            print(f"[QR] generation failed: {exc}")

        return {
            "token": token,
            "machine_id": machine_id,
            "target_url": target,
            "image_data_uri": image_data_uri,
            "scan_count": int(scan_count),
            "generator": "local qrcode library",
        }

    def scan_machine(self, token: str, *, user: Optional[Dict[str, Any]] = None, base_url: Optional[str] = None) -> Dict[str, Any]:
        """Resolve a scanned QR token (or a raw machine id) to real backend data."""
        rows = db.execute_query(
            "SELECT token, machine_id FROM machine_qr_tokens WHERE token = {} AND active = 1".format(
                "%s" if db.use_mysql else "?"
            ),
            (token,),
        )
        machine_id = rows[0]["machine_id"] if rows else (token if self._machine(token) else None)
        if not machine_id:
            audit_service.record(
                user=user, action="MACHINE_QR_SCAN_FAILED", entity_type="machine_qr", entity_id=token, outcome="NOT_FOUND"
            )
            return {"status": "error", "detail": "Unknown or inactive QR token. No machine matched this code."}

        if rows:
            db.execute_write(
                "UPDATE machine_qr_tokens SET scan_count = scan_count + 1 WHERE token = {} ".format(
                    "%s" if db.use_mysql else "?"
                ),
                (token,),
            )
        audit_service.record(
            user=user,
            action="MACHINE_QR_SCAN",
            entity_type="machine",
            entity_id=machine_id,
            machine_id=machine_id,
            detail={"token": token},
        )
        passport = self.machine_passport(machine_id, base_url=base_url, user=user)
        return {
            "status": "ok",
            "machine_id": machine_id,
            "machine": passport.get("machine"),
            "open_investigations": passport.get("open_investigations"),
            "recent_cases": (passport.get("failure_history") or [])[:5],
            "documents": passport.get("documents"),
            "qr": passport.get("qr"),
            "entry_points": [
                {"action": "OPEN_PASSPORT", "label": "Machine passport"},
                {"action": "START_DIAGNOSIS", "label": "Start diagnosis"},
                {"action": "VIEW_INVESTIGATIONS", "label": "Open investigations"},
            ],
        }

    # ------------------------------------------------------------------
    # Situation summary (drives the workstation panel)
    # ------------------------------------------------------------------
    def situation(self, investigation_id: str) -> Dict[str, Any]:
        findings = self.findings(investigation_id)
        investigation = self._require(investigation_id) or {}
        attempts = self.attempts(investigation_id)

        checked = [f for f in findings if str(f.get("ruling", "")).upper() != "PENDING"]
        found = [f for f in findings if str(f.get("ruling", "")).upper() == "FOUND"]
        ruled_out = [f for f in findings if str(f.get("ruling", "")).upper() == "RULED_OUT"]
        pending = [f for f in findings if str(f.get("ruling", "")).upper() == "PENDING"]

        snapshot = _loads(investigation.get("evidence_snapshot_json"), {}) or {}
        attempts_history = self.similar_attempts(
            component=next((f.get("component") for f in findings if f.get("component")), None),
            symptom_text=investigation.get("problem_statement") or "",
        )
        # Prefer the ranking stored with the last re-evaluation; if the snapshot
        # predates that (or does not exist), rank the retrospective evidence that
        # the snapshot does carry. The workstation panel always shows a derived
        # ranking rather than a generic checklist.
        next_checks = snapshot.get("next_inspection")
        if not next_checks:
            evidence_like = [
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "document_name": item.get("title"),
                    "component": item.get("component"),
                    "evidence_type": "case",
                    "inspection": item.get("inspection"),
                    "similarity": item.get("similarity"),
                    "effective_score": item.get("effective_score"),
                    "quality_level": item.get("quality_level"),
                    "document_status": item.get("document_status"),
                }
                for item in snapshot.get("top_evidence", [])
                if item.get("component")
            ]
            next_checks = next_inspection_engine.rank(
                evidence=evidence_like,
                findings=findings,
                failed_attempts=[a for a in attempts if not a.get("was_successful")],
            )

        return {
            "what_we_know": {
                "problem": investigation.get("problem_statement"),
                "symptoms": _loads(investigation.get("symptoms_json"), []),
                "subsystem": investigation.get("subsystem"),
                "severity": investigation.get("severity"),
                "evidence_sufficiency": snapshot.get("evidence_sufficiency") or investigation.get("confidence"),
            },
            "what_we_checked": checked,
            "what_we_found": found,
            "what_we_ruled_out": ruled_out,
            "what_is_pending": pending,
            "what_should_be_checked_next": next_checks,
            "retrieved_evidence": snapshot.get("top_evidence", []),
            "failed_attempts": [a for a in attempts if not a.get("was_successful")],
            "successful_attempts": [a for a in attempts if a.get("was_successful")],
            "historical_failed_attempts": attempts_history["failed_attempts"],
            "historical_failed_attempt_warning": attempts_history["warning"],
            "latest_re_evaluation": snapshot,
        }

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def findings(self, investigation_id: str) -> List[Dict[str, Any]]:
        return db.execute_query(
            "SELECT finding_id, investigation_id, seq, kind, title, detail, value, unit, component, subsystem, source, "
            "quality_level, ruling, evidence_json, created_by_name, created_at FROM investigation_findings "
            "WHERE investigation_id = {} ORDER BY seq ASC".format("%s" if db.use_mysql else "?"),
            (investigation_id,),
        )

    def attempts(self, investigation_id: str) -> List[Dict[str, Any]]:
        return db.execute_query(
            "SELECT attempt_id, investigation_id, machine_id, symptom_text, action_taken, component, failure_mode, "
            "result, was_successful, technician_note, created_by_name, created_at FROM repair_attempts "
            "WHERE investigation_id = {} ORDER BY created_at ASC".format("%s" if db.use_mysql else "?"),
            (investigation_id,),
        )

    def photos(self, investigation_id: str) -> List[Dict[str, Any]]:
        return db.execute_query(
            "SELECT photo_id, file_path, original_filename, caption, component_suggested, component_confirmed, "
            "visual_match, image_analysis_json, related_knowledge_json, created_at FROM photo_evidence "
            "WHERE investigation_id = {} ORDER BY created_at ASC".format("%s" if db.use_mysql else "?"),
            (investigation_id,),
        )

    def timeline(self, investigation_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        """Chronological events, every row read from the database (brief §18)."""
        return db.execute_query(
            "SELECT event_id, event_type, summary, actor_name, payload_json, created_at FROM investigation_events "
            f"WHERE investigation_id = {'%s' if db.use_mysql else '?'} ORDER BY created_at ASC, event_id ASC "
            f"LIMIT {int(limit)}",
            (investigation_id,),
        )

    def add_event(
        self,
        *,
        investigation_id: str,
        event_type: str,
        summary: str,
        user: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        event_id = f"EVT-{uuid.uuid4().hex[:8].upper()}"
        user = user or {}
        db.execute_write(
            "INSERT INTO investigation_events (event_id, investigation_id, event_type, summary, actor_id, actor_name, "
            "payload_json) VALUES (%s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
            "INSERT INTO investigation_events (event_id, investigation_id, event_type, summary, actor_id, actor_name, "
            "payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event_id,
                investigation_id,
                event_type,
                summary[:480],
                user.get("user_id"),
                user.get("full_name") or user.get("username"),
                _json(payload or {}),
            ),
        )
        return event_id

    # ------------------------------------------------------------------
    def _require(self, investigation_id: str) -> Optional[Dict[str, Any]]:
        rows = db.execute_query(
            "SELECT * FROM investigations WHERE investigation_id = {} ".format("%s" if db.use_mysql else "?"),
            (investigation_id,),
        )
        return rows[0] if rows else None

    def _machine(self, machine_id: str) -> Dict[str, Any]:
        rows = db.execute_query(
            "SELECT machine_id, machine_model, machine_type, manufacturer, operating_hours, status, last_maintenance "
            "FROM machines WHERE machine_id = {} ".format("%s" if db.use_mysql else "?"),
            (machine_id,),
        )
        return rows[0] if rows else {}

    def _success_rate(self, attempts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not attempts:
            return None
        successes = sum(1 for a in attempts if a.get("was_successful"))
        return {
            "recorded_attempts": len(attempts),
            "successful": successes,
            "rate": round(successes / len(attempts), 3),
            "basis": "Computed from recorded repair attempts for this machine only.",
        }

    def _subsystem_history(self, cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        counts: Dict[str, Dict[str, Any]] = {}
        for case in cases:
            key = case.get("subsystem") or "Unclassified"
            entry = counts.setdefault(key, {"subsystem": key, "cases": 0, "components": {}})
            entry["cases"] += 1
            component = case.get("component") or "Unknown"
            entry["components"][component] = entry["components"].get(component, 0) + 1
        out = []
        for entry in counts.values():
            entry["components"] = [
                {"component": name, "cases": count}
                for name, count in sorted(entry["components"].items(), key=lambda pair: pair[1], reverse=True)
            ]
            out.append(entry)
        return sorted(out, key=lambda item: item["cases"], reverse=True)

    def _maintenance_intervals(self, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Interval derived from the machine's own recorded interventions."""
        hours = sorted(
            int(case["operating_hours"]) for case in cases if case.get("operating_hours") is not None
        )
        if len(hours) < 2:
            return {
                "records_used": len(hours),
                "average_interval_hours": None,
                "note": (
                    "Fewer than two recorded interventions with an operating-hours reading: no interval can be "
                    "derived for this machine. No schedule is invented."
                ),
            }
        gaps = [b - a for a, b in zip(hours, hours[1:]) if b - a > 0]
        average = round(sum(gaps) / len(gaps)) if gaps else None
        return {
            "records_used": len(hours),
            "average_interval_hours": average,
            "min_gap_hours": min(gaps) if gaps else None,
            "max_gap_hours": max(gaps) if gaps else None,
            "note": "Derived from the intervals between this machine's own recorded maintenance cases.",
        }


investigation_service = InvestigationService()
