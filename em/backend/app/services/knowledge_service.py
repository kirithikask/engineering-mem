"""
Knowledge lifecycle: quality levels, revisions, review workflow and the closed loop.

Implements brief §4 (knowledge quality levels), §6 (version intelligence and
evidence conflict), §7/§19 (closed-loop engineering memory) and §7 (safety).

Rules enforced here in code, not only described in the UI:

* Nothing reaches FAISS without a human decision: a knowledge item is embedded
  only after an engineer/admin approval, and the quality level recorded is then
  ENGINEER_REVIEWED or VERIFIED.
* Old revisions are never deleted. Approving a newer revision marks the older
  ones SUPERSEDED with a superseded date and a pointer to the revision that
  replaced them, and the numeric statements of both revisions are compared so a
  real conflict can be shown to the engineer.
* Rejected knowledge stays in the database with its rejection record.
* Safety guidance is only ever assembled from approved sources, or explicitly
  reported as the platform's standing advisory when no approved procedure exists.
"""

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.db.mysql_client import db
from backend.app.services.index_service import index_service
from backend.app.services.retrieval_service import measure_statements, topic_tokens, topics_relate

QUALITY_LEVELS = ["UNVERIFIED", "TECHNICIAN_SUBMITTED", "ENGINEER_REVIEWED", "VERIFIED"]
# Ordered weakest -> strongest, so a reviewer can never downgrade a level.
QUALITY_RANK = {level: index for index, level in enumerate(QUALITY_LEVELS)}

DOCUMENT_STATUSES = ["CURRENT", "SUPERSEDED", "ARCHIVED", "DRAFT", "PENDING_REVIEW"]

REVISION_NOISE = re.compile(
    r"(?i)\b(rev|revision|version|ver|v)\s*\.?\s*\d+(\.\d+)*\b|rendition|\bfinal\b|\(\d+\)|\b20\d{2}[-_]\d{2}[-_]\d{2}\b"
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _json(value: Any) -> str:
    try:
        return json.dumps(value, default=str)
    except Exception:
        return "{}"


def family_key(name: str, document_type: Optional[str]) -> str:
    """Identity of a document across revisions (revision markers stripped)."""
    base = REVISION_NOISE.sub(" ", str(name or "").lower())
    base = re.sub(r"[^a-z0-9]+", " ", base)
    base = " ".join(base.split())
    suffix = re.sub(r"[^a-z0-9]+", "_", str(document_type or "").lower()).strip("_")
    return f"{base}|{suffix}"


class KnowledgeService:
    # ------------------------------------------------------------------
    # Document revisions and version priority
    # ------------------------------------------------------------------
    def list_versions(self, document_id: str) -> Dict[str, Any]:
        docs = db.execute_query(
            "SELECT document_id, document_name, document_type, version, status, file_path, created_at "
            "FROM documents WHERE document_id = {} ".format("%s" if db.use_mysql else "?"),
            (document_id,),
        )
        if not docs:
            return {"document": None, "versions": []}
        document = docs[0]
        key = family_key(document["document_name"], document.get("document_type"))

        all_docs = db.execute_query("SELECT document_id, document_name, document_type, status FROM documents")
        related = {
            row["document_id"]
            for row in all_docs
            if family_key(row["document_name"], row.get("document_type")) == key
        }
        related.add(document_id)

        placeholders = ", ".join(["%s" if db.use_mysql else "?"] * len(related))
        versions = db.execute_query(
            "SELECT version_id, document_id, revision, status, effective_date, superseded_date, source, "
            "extraction_method, extraction_confidence, approved_by, approved_at, note, created_at "
            f"FROM document_versions WHERE document_id IN ({placeholders}) "
            "ORDER BY created_at DESC",
            tuple(related),
        )
        for version in versions:
            rows = db.execute_query(
                "SELECT COUNT(*) AS n FROM document_chunks WHERE document_id = {} ".format("%s" if db.use_mysql else "?"),
                (version["document_id"],),
            )
            version["chunk_count"] = int(rows[0]["n"]) if rows else 0

        conflicts = db.execute_query(
            "SELECT conflict_id, topic, source_a_json, source_b_json, severity, status, created_at "
            "FROM evidence_conflicts WHERE topic LIKE {} ORDER BY created_at DESC LIMIT 25".format(
                "%s" if db.use_mysql else "?"
            ),
            (f"%{document['document_name'].split('.')[0][:40]}%",),
        )

        return {
            "document": document,
            "family_key": key,
            "versions": versions,
            "conflicts": conflicts,
            "status_priority": ["CURRENT/APPROVED", "PENDING_REVIEW", "DRAFT", "SUPERSEDED", "ARCHIVED"],
        }

    def approve_document(
        self,
        *,
        document_id: str,
        version_id: Optional[str],
        user: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Approve a revision, supersede older revisions, then index its chunks."""
        versions = db.execute_query(
            "SELECT version_id, document_id, revision, status FROM document_versions WHERE document_id = {} "
            "ORDER BY created_at DESC".format("%s" if db.use_mysql else "?"),
            (document_id,),
        )
        if not versions:
            return {"status": "error", "detail": "No extracted version exists for this document."}

        target = None
        if version_id:
            target = next((v for v in versions if v["version_id"] == version_id), None)
        if target is None:
            target = versions[0]

        docs = db.execute_query(
            "SELECT document_id, document_name, document_type FROM documents WHERE document_id = {} ".format(
                "%s" if db.use_mysql else "?"
            ),
            (document_id,),
        )
        if not docs:
            return {"status": "error", "detail": "Document not found."}
        document = docs[0]
        key = family_key(document["document_name"], document.get("document_type"))

        superseded: List[Dict[str, Any]] = []
        all_versions = db.execute_query(
            "SELECT v.version_id, v.document_id, v.revision, v.status, d.document_name, d.document_type "
            "FROM document_versions v JOIN documents d ON v.document_id = d.document_id"
        )
        for row in all_versions:
            if row["version_id"] == target["version_id"]:
                continue
            if family_key(row["document_name"], row.get("document_type")) != key:
                continue
            if row["status"] in ("SUPERSEDED", "ARCHIVED", "REJECTED"):
                continue
            db.execute_write(
                "UPDATE document_versions SET status = 'SUPERSEDED', superseded_date = {} WHERE version_id = {}".format(
                    "%s" if db.use_mysql else "?", "%s" if db.use_mysql else "?"
                ),
                (_now(), row["version_id"]),
            )
            db.execute_write(
                "UPDATE documents SET status = {} WHERE document_id = {}".format(
                    "%s" if db.use_mysql else "?", "%s" if db.use_mysql else "?"
                ),
                ("SUPERSEDED", row["document_id"]),
            )
            superseded.append(
                {
                    "version_id": row["version_id"],
                    "revision": row["revision"],
                    "document_id": row["document_id"],
                    "document_name": row["document_name"],
                }
            )

        db.execute_write(
            "UPDATE document_versions SET status = 'CURRENT', approved_by = {}, approved_at = {}, "
            "superseded_date = NULL WHERE version_id = {}".format(
                "%s" if db.use_mysql else "?", "%s" if db.use_mysql else "?", "%s" if db.use_mysql else "?"
            ),
            (user.get("user_id"), _now(), target["version_id"]),
        )
        db.execute_write(
            "UPDATE documents SET status = {} WHERE document_id = {}".format(
                "%s" if db.use_mysql else "?", "%s" if db.use_mysql else "?"
            ),
            ("APPROVED", document_id),
        )
        db.execute_write(
            "UPDATE document_extractions SET review_status = 'APPROVED', reviewer_id = {}, reviewed_at = {} "
            "WHERE document_id = {}".format(
                "%s" if db.use_mysql else "?", "%s" if db.use_mysql else "?", "%s" if db.use_mysql else "?"
            ),
            (user.get("user_id"), _now(), document_id),
        )

        chunks = self._document_chunks_for_indexing(document_id, target["version_id"])
        index_result = index_service.index_document_chunks(document_id, chunks, user)

        db.execute_write(
            "UPDATE documents SET status = {} WHERE document_id = {}".format(
                "%s" if db.use_mysql else "?", "%s" if db.use_mysql else "?"
            ),
            ("INDEXED" if index_result.get("added") else "APPROVED", document_id),
        )
        db.execute_write(
            "UPDATE ingestion_jobs SET status = {}, pipeline_stage = 'INDEXED', vector_count = {}, updated_at = {} "
            "WHERE document_id = {}".format(
                "%s" if db.use_mysql else "?", "%s" if db.use_mysql else "?", "%s" if db.use_mysql else "?", "%s" if db.use_mysql else "?"
            ),
            ("INDEXED", int(index_result.get("added", 0)), _now(), document_id),
        )

        conflicts = self.record_revision_conflicts(
            document=document,
            approved_version=target,
            superseded=superseded,
            user=user,
        )

        return {
            "status": "ok",
            "document_id": document_id,
            "version_id": target["version_id"],
            "revision": target["revision"],
            "version_status": "CURRENT",
            "superseded": superseded,
            "index": index_result,
            "conflicts_recorded": conflicts,
        }

    def reject_document(self, *, document_id: str, user: Dict[str, Any], comment: Optional[str] = None) -> Dict[str, Any]:
        db.execute_write(
            "UPDATE documents SET status = {} WHERE document_id = {}".format(
                "%s" if db.use_mysql else "?", "%s" if db.use_mysql else "?"
            ),
            ("REJECTED", document_id),
        )
        db.execute_write(
            "UPDATE document_versions SET status = 'REJECTED', note = {} WHERE document_id = {}".format(
                "%s" if db.use_mysql else "?", "%s" if db.use_mysql else "?"
            ),
            (comment, document_id),
        )
        db.execute_write(
            "UPDATE document_extractions SET review_status = 'REJECTED', reviewer_id = {}, reviewed_at = {} "
            "WHERE document_id = {}".format(
                "%s" if db.use_mysql else "?", "%s" if db.use_mysql else "?", "%s" if db.use_mysql else "?"
            ),
            (user.get("user_id"), _now(), document_id),
        )
        db.execute_write(
            "UPDATE ingestion_jobs SET status = 'REJECTED', updated_at = {} WHERE document_id = {}".format(
                "%s" if db.use_mysql else "?", "%s" if db.use_mysql else "?"
            ),
            (_now(), document_id),
        )
        return {"status": "ok", "document_id": document_id, "document_status": "REJECTED"}

    def _document_chunks_for_indexing(self, document_id: str, version_id: str) -> List[Dict[str, Any]]:
        versions = db.execute_query(
            "SELECT revision, status FROM document_versions WHERE version_id = {}".format("%s" if db.use_mysql else "?"),
            (version_id,),
        )
        revision = versions[0]["revision"] if versions else None
        rows = db.execute_query(
            "SELECT c.chunk_id, c.document_id, d.document_name, c.page_number, c.section_heading, c.component, "
            "c.chunk_text FROM document_chunks c JOIN documents d ON c.document_id = d.document_id "
            "WHERE c.document_id = {}".format("%s" if db.use_mysql else "?"),
            (document_id,),
        )
        meta = db.execute_query(
            "SELECT owner_id, source_kind, note FROM knowledge_sources WHERE owner_type = 'document_chunk'"
        )
        meta_by_chunk = {row["owner_id"]: row for row in meta}
        out = []
        for row in rows:
            extra = meta_by_chunk.get(row["chunk_id"], {})
            note = {}
            try:
                note = json.loads(extra.get("note") or "{}")
            except Exception:
                note = {}
            out.append(
                {
                    **row,
                    "chunk_kind": extra.get("source_kind") or note.get("chunk_kind") or "text",
                    "revision": revision,
                    "document_status": "CURRENT",
                    "quality_level": "VERIFIED",
                    "subsystem": note.get("subsystem"),
                }
            )
        return out

    # ------------------------------------------------------------------
    # Revision conflict intelligence
    # ------------------------------------------------------------------
    def record_revision_conflicts(
        self,
        *,
        document: Dict[str, Any],
        approved_version: Dict[str, Any],
        superseded: List[Dict[str, Any]],
        user: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Compare numeric engineering statements between revisions.

        Only statements that mention the same quantity (same surrounding wording)
        with different values are reported. Both sources are stored; nothing is
        auto-resolved.
        """
        document_id = (document or {}).get("document_id")
        if not superseded or not document_id:
            return []

        new_text = self._document_text(document_id)
        # Wording is compared by token signature, not by exact string: two revisions
        # can state the same quantity in different sentences.
        new_statements = [
            (topic_tokens(topic), value, unit) for topic, value, unit in measure_statements(new_text)
        ]
        new_statements = [entry for entry in new_statements if entry[0]]
        if not new_statements:
            return []

        recorded: List[Dict[str, Any]] = []
        for older in superseded:
            old_text = self._document_text(older["document_id"])
            for topic, value, unit in measure_statements(old_text):
                tokens = topic_tokens(topic)
                if not tokens:
                    continue
                match = next(
                    (
                        (new_tokens, new_value, new_unit)
                        for new_tokens, new_value, new_unit in new_statements
                        if new_unit == unit and topics_relate(tokens, new_tokens)
                    ),
                    None,
                )
                if match is None:
                    continue
                _new_tokens, new_value, _new_unit = match
                if new_value == value:
                    continue
                source_a = {
                    "id": approved_version["version_id"],
                    "revision": approved_version["revision"],
                    "document": document["document_name"],
                    "value": new_value,
                    "unit": unit,
                    "status": "CURRENT",
                }
                source_b = {
                    "id": older["version_id"],
                    "revision": older["revision"],
                    "document": older["document_name"],
                    "value": value,
                    "unit": unit,
                    "status": "SUPERSEDED",
                }
                if self._conflict_exists(tokens, unit, new_value, value):
                    continue
                db.execute_write(
                    "INSERT INTO evidence_conflicts (conflict_id, topic, source_a_json, source_b_json, comparison_json, "
                    "severity, detected_by, status) VALUES (%s, %s, %s, %s, %s, %s, %s, 'OPEN')" if db.use_mysql else
                    "INSERT INTO evidence_conflicts (conflict_id, topic, source_a_json, source_b_json, comparison_json, "
                    "severity, detected_by, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN')",
                    (
                        f"CONF-{uuid.uuid4().hex[:8].upper()}",
                        topic[:250],
                        _json(source_a),
                        _json(source_b),
                        _json({"quantity": topic, "unit": unit, "values": [new_value, value]}),
                        "REVISION_CONFLICT",
                        "version_intelligence",
                    ),
                )
                recorded.append(
                    {
                        "topic": topic,
                        "unit": unit,
                        "current": source_a,
                        "superseded": source_b,
                        "approved_by": user.get("username"),
                    }
                )
        return recorded

    def _conflict_exists(self, tokens: frozenset, unit: str, value_a: str, value_b: str) -> bool:
        """Avoid recording the same revision conflict twice."""
        rows = db.execute_query(
            "SELECT topic, source_a_json, source_b_json FROM evidence_conflicts WHERE status = 'OPEN' LIMIT 200"
        )
        wanted = {value_a, value_b}
        for row in rows:
            if not topics_relate(tokens, topic_tokens(row.get("topic") or "")):
                continue
            try:
                source_a = json.loads(row.get("source_a_json") or "{}")
                source_b = json.loads(row.get("source_b_json") or "{}")
            except Exception:
                continue
            if source_a.get("unit") != unit:
                continue
            if {str(source_a.get("value")), str(source_b.get("value"))} == wanted:
                return True
        return False

    def _document_text(self, document_id: str) -> str:
        rows = db.execute_query(
            "SELECT chunk_text FROM document_chunks WHERE document_id = {} LIMIT 400".format(
                "%s" if db.use_mysql else "?"
            ),
            (document_id,),
        )
        return " ".join(str(row.get("chunk_text") or "") for row in rows)

    def open_conflicts(self, limit: int = 50) -> List[Dict[str, Any]]:
        rows = db.execute_query(
            "SELECT conflict_id, topic, source_a_json, source_b_json, severity, detected_by, status, resolution, "
            "resolved_by, resolved_at, created_at FROM evidence_conflicts ORDER BY created_at DESC "
            f"LIMIT {int(limit)}"
        )
        for row in rows:
            for key in ("source_a_json", "source_b_json"):
                try:
                    row[key.replace("_json", "")] = json.loads(row.get(key) or "{}")
                except Exception:
                    row[key.replace("_json", "")] = {}
        return rows

    def resolve_conflict(self, conflict_id: str, resolution: str, user: Dict[str, Any]) -> Dict[str, Any]:
        db.execute_write(
            "UPDATE evidence_conflicts SET status = 'RESOLVED', resolution = {}, resolved_by = {}, resolved_at = {} "
            "WHERE conflict_id = {}".format(
                "%s" if db.use_mysql else "?", "%s" if db.use_mysql else "?", "%s" if db.use_mysql else "?", "%s" if db.use_mysql else "?"
            ),
            (resolution, user.get("username"), _now(), conflict_id),
        )
        return {"status": "ok", "conflict_id": conflict_id}

    # ------------------------------------------------------------------
    # Closed loop: case draft -> review -> approval -> FAISS
    # ------------------------------------------------------------------
    def create_case_draft(self, *, investigation: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
        """Assemble the structured case draft from recorded investigation data."""
        findings = db.execute_query(
            "SELECT kind, title, detail, value, unit, component, ruling, created_at FROM investigation_findings "
            "WHERE investigation_id = {} ORDER BY seq ASC".format("%s" if db.use_mysql else "?"),
            (investigation["investigation_id"],),
        )
        attempts = db.execute_query(
            "SELECT action_taken, result, component, technician_note, created_at FROM repair_attempts "
            "WHERE investigation_id = {} ORDER BY created_at ASC".format("%s" if db.use_mysql else "?"),
            (investigation["investigation_id"],),
        )
        verification = db.execute_query(
            "SELECT checks_json, passed, notes, verified_by_name, created_at FROM repair_verifications "
            "WHERE investigation_id = {} ORDER BY created_at DESC LIMIT 1".format("%s" if db.use_mysql else "?"),
            (investigation["investigation_id"],),
        )
        machine = db.execute_query(
            "SELECT machine_id, machine_model, machine_type, manufacturer, operating_hours FROM machines "
            "WHERE machine_id = {}".format("%s" if db.use_mysql else "?"),
            (investigation["machine_id"],),
        )
        machine_row = machine[0] if machine else {}

        failed = [a for a in attempts if str(a.get("result", "")).upper() != "RESOLVED"]
        succeeded = [a for a in attempts if str(a.get("result", "")).upper() == "RESOLVED"]
        checks = []
        if verification:
            try:
                checks = json.loads(verification[0].get("checks_json") or "[]")
            except Exception:
                checks = []

        relevant = [f for f in findings if f.get("kind") in ("inspection", "measurement", "observation")]
        draft = {
            "machine": investigation["machine_id"],
            "model": machine_row.get("machine_model"),
            "machine_type": machine_row.get("machine_type"),
            "operating_hours": machine_row.get("operating_hours"),
            "subsystem": investigation.get("subsystem"),
            "component": investigation.get("root_cause_component")
            or next((f.get("component") for f in relevant if f.get("component")), None),
            "symptoms": investigation.get("symptoms_json"),
            "operating_condition": "field operation",
            "technician_observations": [
                {"title": f.get("title"), "detail": f.get("detail"), "value": f.get("value"), "unit": f.get("unit")}
                for f in relevant
            ],
            "inspection_findings": [
                {"title": f.get("title"), "ruling": f.get("ruling"), "detail": f.get("detail")} for f in findings
            ],
            "root_cause": investigation.get("root_cause"),
            "root_cause_detail": investigation.get("root_cause_detail"),
            "failed_attempts": [a.get("action_taken") for a in failed],
            "successful_repair": investigation.get("repair_summary") or (succeeded[0].get("action_taken") if succeeded else None),
            "parts": [],
            "verification": checks,
            "outcome": "resolved" if verification and verification[0].get("passed") else ("unverified" if not verification else "persisting"),
            "source": "field investigation",
            "technician": investigation.get("opened_by_name"),
            "date": investigation.get("opened_at"),
        }
        return draft

    def upsert_case_draft(
        self,
        *,
        investigation: Dict[str, Any],
        symptom_text: str,
        user: Dict[str, Any],
        overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        overrides = overrides or {}
        draft = self.create_case_draft(investigation=investigation, user=user)
        draft.update({k: v for k, v in overrides.items() if v not in (None, "")})

        existing = db.execute_query(
            "SELECT knowledge_id, status, quality_level FROM knowledge_items WHERE investigation_id = {} ORDER BY created_at DESC LIMIT 1".format(
                "%s" if db.use_mysql else "?"
            ),
            (investigation["investigation_id"],),
        )

        knowledge_id = existing[0]["knowledge_id"] if existing else f"KN-{uuid.uuid4().hex[:8].upper()}"
        title = overrides.get("title") or f"{investigation['machine_id']} — {draft.get('root_cause') or symptom_text[:60]}"
        content = self._draft_content(draft)

        payload = (
            knowledge_id,
            title[:250],
            "case",
            content,
            investigation["machine_id"],
            draft.get("model"),
            draft.get("subsystem"),
            draft.get("component"),
            draft.get("root_cause"),
            symptom_text,
            draft.get("root_cause_detail") or draft.get("root_cause"),
            draft.get("successful_repair"),
            _json(draft.get("verification")),
            draft.get("outcome"),
            draft.get("operating_condition"),
            _json(draft.get("parts")),
            _json(draft.get("failed_attempts")),
            "TECHNICIAN_SUBMITTED",
            "DRAFT",
            "field_investigation",
            investigation["investigation_id"],
            investigation["investigation_id"],
            user.get("user_id"),
            user.get("full_name") or user.get("username"),
        )

        if existing:
            db.execute_write(
                "UPDATE knowledge_items SET title = %s, content = %s, machine_id = %s, machine_model = %s, subsystem = %s, "
                "component = %s, failure_mode = %s, symptom = %s, root_cause = %s, repair_action = %s, verification = %s, "
                "outcome = %s, operating_condition = %s, parts_json = %s, failed_attempts_json = %s, status = 'DRAFT', "
                "created_by = %s, created_by_name = %s WHERE knowledge_id = %s" if db.use_mysql else
                "UPDATE knowledge_items SET title = ?, content = ?, machine_id = ?, machine_model = ?, subsystem = ?, "
                "component = ?, failure_mode = ?, symptom = ?, root_cause = ?, repair_action = ?, verification = ?, "
                "outcome = ?, operating_condition = ?, parts_json = ?, failed_attempts_json = ?, status = 'DRAFT', "
                "created_by = ?, created_by_name = ? WHERE knowledge_id = ?",
                # payload layout: 0 knowledge_id, 1..15 the editable fields, 16 quality,
                # 17 status, 18 source_type, 19/20 investigation ids, 21/22 author.
                payload[1:16] + (payload[21], payload[22], knowledge_id),
            )
        else:
            db.execute_write(
                "INSERT INTO knowledge_items (knowledge_id, title, knowledge_type, content, machine_id, machine_model, "
                "subsystem, component, failure_mode, symptom, root_cause, repair_action, verification, outcome, "
                "operating_condition, parts_json, failed_attempts_json, quality_level, status, source_type, "
                "source_ref, investigation_id, created_by, created_by_name) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                if db.use_mysql else
                "INSERT INTO knowledge_items (knowledge_id, title, knowledge_type, content, machine_id, machine_model, "
                "subsystem, component, failure_mode, symptom, root_cause, repair_action, verification, outcome, "
                "operating_condition, parts_json, failed_attempts_json, quality_level, status, source_type, "
                "source_ref, investigation_id, created_by, created_by_name) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                payload,
            )

        db.execute_write(
            "UPDATE investigations SET knowledge_id = {} WHERE investigation_id = {}".format(
                "%s" if db.use_mysql else "?", "%s" if db.use_mysql else "?"
            ),
            (knowledge_id, investigation["investigation_id"]),
        )
        return {"knowledge_id": knowledge_id, "status": "DRAFT", "quality_level": "TECHNICIAN_SUBMITTED", "draft": draft, "title": title, "content": content}

    def _draft_content(self, draft: Dict[str, Any]) -> str:
        lines = [
            f"Machine: {draft.get('machine')} ({draft.get('model') or 'model not recorded'})",
            f"Symptoms: {draft.get('symptoms')}",
            f"Subsystem: {draft.get('subsystem')} · Component: {draft.get('component')}",
            f"Root cause: {draft.get('root_cause')}",
            f"Repair: {draft.get('successful_repair')}",
        ]
        if draft.get("failed_attempts"):
            lines.append("Failed attempts (did not resolve the symptom): " + "; ".join(str(a) for a in draft["failed_attempts"]))
        if draft.get("verification"):
            lines.append("Verification: " + "; ".join(str(c) for c in draft["verification"]))
        lines.append(f"Outcome: {draft.get('outcome')}")
        return "\n".join(lines)

    def submit_for_review(self, knowledge_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
        db.execute_write(
            "UPDATE knowledge_items SET status = 'PENDING_REVIEW', quality_level = 'TECHNICIAN_SUBMITTED' "
            "WHERE knowledge_id = {} AND status IN ('DRAFT', 'REJECTED')".format("%s" if db.use_mysql else "?"),
            (knowledge_id,),
        )
        self._record_review(knowledge_id, user, "SUBMIT_FOR_REVIEW", "DRAFT", "PENDING_REVIEW", "TECHNICIAN_SUBMITTED", "TECHNICIAN_SUBMITTED", None)
        return self.get_item(knowledge_id)

    def review(
        self,
        *,
        knowledge_id: str,
        action: str,
        user: Dict[str, Any],
        comment: Optional[str] = None,
        edits: Optional[Dict[str, Any]] = None,
        quality_level: Optional[str] = None,
    ) -> Dict[str, Any]:
        action = (action or "").upper()
        items = db.execute_query("SELECT * FROM knowledge_items WHERE knowledge_id = {}".format("%s" if db.use_mysql else "?"), (knowledge_id,))
        if not items:
            return {"status": "error", "detail": "Knowledge item not found."}
        item = items[0]
        prior_status = item.get("status")
        prior_quality = item.get("quality_level")

        if edits:
            allowed = {
                "title", "component", "failure_mode", "symptom", "root_cause", "repair_action",
                "verification", "outcome", "subsystem", "content", "machine_model",
            }
            assignments = {k: v for k, v in edits.items() if k in allowed}
            if assignments:
                columns = ", ".join(f"{k} = {'%s' if db.use_mysql else '?'}" for k in assignments)
                db.execute_write(
                    f"UPDATE knowledge_items SET {columns} WHERE knowledge_id = {'%s' if db.use_mysql else '?'}",
                    tuple(assignments.values()) + (knowledge_id,),
                )

        if action == "REJECT":
            db.execute_write(
                "UPDATE knowledge_items SET status = 'REJECTED' WHERE knowledge_id = {}".format("%s" if db.use_mysql else "?"),
                (knowledge_id,),
            )
            new_status, new_quality = "REJECTED", prior_quality
        elif action == "APPROVE":
            new_quality = quality_level or "VERIFIED"
            new_status = "APPROVED"
            db.execute_write(
                "UPDATE knowledge_items SET status = %s, quality_level = %s, approved_by = %s, approved_by_name = %s, "
                "approved_at = %s WHERE knowledge_id = %s" if db.use_mysql else
                "UPDATE knowledge_items SET status = ?, quality_level = ?, approved_by = ?, approved_by_name = ?, "
                "approved_at = ? WHERE knowledge_id = ?",
                (new_status, new_quality, user.get("user_id"), user.get("full_name") or user.get("username"), _now(), knowledge_id),
            )
        else:
            return {"status": "error", "detail": f"Unsupported review action '{action}'."}

        self._record_review(knowledge_id, user, action, prior_status, new_status, prior_quality, new_quality, comment)

        index_result: Dict[str, Any] = {"status": "skipped", "detail": "not approved"}
        if action == "APPROVE":
            refreshed = self.get_item(knowledge_id)["item"]
            index_result = index_service.index_knowledge_item(refreshed, user)
            if index_result.get("added"):
                db.execute_write(
                    "UPDATE knowledge_items SET vector_id = {} WHERE knowledge_id = {}".format(
                        "%s" if db.use_mysql else "?", "%s" if db.use_mysql else "?"
                    ),
                    (int(index_result.get("first_vector_id", -1)), knowledge_id),
                )
            self._record_sources(knowledge_id, refreshed)

        return {
            "status": "ok",
            "knowledge_id": knowledge_id,
            "action": action,
            "knowledge_status": new_status,
            "quality_level": new_quality if action == "APPROVE" else prior_quality,
            "index": index_result,
            "message": (
                "Engineering Memory Updated — the approved knowledge is now retrievable."
                if action == "APPROVE" and index_result.get("added")
                else ("Approved; already present in the index." if action == "APPROVE" else "Knowledge rejected; the record is retained.")
            ),
        }

    def _record_review(
        self,
        knowledge_id: str,
        user: Dict[str, Any],
        action: str,
        prior_status: Optional[str],
        new_status: Optional[str],
        prior_quality: Optional[str],
        new_quality: Optional[str],
        comment: Optional[str],
    ) -> None:
        db.execute_write(
            "INSERT INTO knowledge_reviews (review_id, knowledge_id, reviewer_id, reviewer_name, reviewer_role, action, "
            "prior_status, new_status, prior_quality_level, new_quality_level, comment) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
            "INSERT INTO knowledge_reviews (review_id, knowledge_id, reviewer_id, reviewer_name, reviewer_role, action, "
            "prior_status, new_status, prior_quality_level, new_quality_level, comment) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"KRV-{uuid.uuid4().hex[:8].upper()}",
                knowledge_id,
                user.get("user_id"),
                user.get("full_name") or user.get("username"),
                user.get("role"),
                action,
                prior_status,
                new_status,
                prior_quality,
                new_quality,
                comment,
            ),
        )

    def _record_sources(self, knowledge_id: str, item: Dict[str, Any]) -> None:
        investigation_id = item.get("investigation_id")
        sources = [("investigation", investigation_id, "field_investigation_record", "Investigation findings and repair record")]
        if item.get("machine_id"):
            sources.append(("machine_record", item["machine_id"], "machine_history", f"Machine {item['machine_id']}"))
        for owner_type, owner_id, kind, title in sources:
            if not owner_id:
                continue
            db.execute_write(
                "INSERT INTO knowledge_sources (source_id, owner_type, owner_id, source_kind, source_ref, title, "
                "quality_level, note) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
                "INSERT INTO knowledge_sources (source_id, owner_type, owner_id, source_kind, source_ref, title, "
                "quality_level, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"SRC-{uuid.uuid4().hex[:10].upper()}",
                    "knowledge",
                    knowledge_id,
                    kind,
                    owner_id[:110],
                    title,
                    item.get("quality_level"),
                    owner_type,
                ),
            )

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def get_item(self, knowledge_id: str) -> Dict[str, Any]:
        items = db.execute_query("SELECT * FROM knowledge_items WHERE knowledge_id = {}".format("%s" if db.use_mysql else "?"), (knowledge_id,))
        if not items:
            return {"item": None, "reviews": [], "sources": []}
        reviews = db.execute_query(
            "SELECT reviewer_name, reviewer_role, action, prior_status, new_status, prior_quality_level, "
            "new_quality_level, comment, created_at FROM knowledge_reviews WHERE knowledge_id = {} "
            "ORDER BY created_at DESC".format("%s" if db.use_mysql else "?"),
            (knowledge_id,),
        )
        sources = db.execute_query(
            "SELECT source_kind, source_ref, title, quality_level, page_number, revision, created_at FROM knowledge_sources "
            "WHERE owner_type = 'knowledge' AND owner_id = {} ORDER BY created_at DESC".format("%s" if db.use_mysql else "?"),
            (knowledge_id,),
        )
        return {"item": items[0], "reviews": reviews, "sources": sources}

    def list_items(
        self,
        *,
        status: Optional[str] = None,
        quality_level: Optional[str] = None,
        knowledge_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        placeholder = "%s" if db.use_mysql else "?"
        conditions, params = [], []
        if status:
            conditions.append(f"status = {placeholder}")
            params.append(status)
        if quality_level:
            conditions.append(f"quality_level = {placeholder}")
            params.append(quality_level)
        if knowledge_type:
            conditions.append(f"knowledge_type = {placeholder}")
            params.append(knowledge_type)
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

        total_rows = db.execute_query(f"SELECT COUNT(*) AS n FROM knowledge_items{where}", tuple(params))
        items = db.execute_query(
            "SELECT knowledge_id, title, knowledge_type, machine_id, machine_model, subsystem, component, failure_mode, "
            "symptom, root_cause, repair_action, outcome, quality_level, status, source_type, investigation_id, "
            "created_by_name, created_at, approved_by_name, approved_at, vector_id "
            f"FROM knowledge_items{where} ORDER BY created_at DESC LIMIT {int(limit)} OFFSET {int(offset)}",
            tuple(params),
        )
        return {
            "items": items,
            "total": int(total_rows[0]["n"]) if total_rows else 0,
            "quality_levels": QUALITY_LEVELS,
        }

    def overview(self) -> Dict[str, Any]:
        def scalar(query: str) -> int:
            rows = db.execute_query(query)
            return int(list(rows[0].values())[0]) if rows else 0

        by_status = db.execute_query(
            "SELECT status, COUNT(*) AS n FROM knowledge_items GROUP BY status"
        )
        by_quality = db.execute_query(
            "SELECT quality_level, COUNT(*) AS n FROM knowledge_items GROUP BY quality_level"
        )
        return {
            "knowledge_items": scalar("SELECT COUNT(*) AS n FROM knowledge_items"),
            "documents": scalar("SELECT COUNT(*) AS n FROM documents"),
            "document_chunks": scalar("SELECT COUNT(*) AS n FROM document_chunks"),
            "document_versions": scalar("SELECT COUNT(*) AS n FROM document_versions"),
            "pending_review_documents": scalar(
                "SELECT COUNT(*) AS n FROM document_versions WHERE status = 'PENDING_REVIEW'"
            ),
            "knowledge_by_status": [{"status": row["status"], "count": int(row["n"])} for row in by_status],
            "knowledge_by_quality": [{"quality_level": row["quality_level"], "count": int(row["n"])} for row in by_quality],
            "open_conflicts": scalar("SELECT COUNT(*) AS n FROM evidence_conflicts WHERE status = 'OPEN'"),
            "pending_reviews": scalar("SELECT COUNT(*) AS n FROM knowledge_items WHERE status = 'PENDING_REVIEW'"),
            "investigations": scalar("SELECT COUNT(*) AS n FROM investigations"),
            "failed_attempts": scalar("SELECT COUNT(*) AS n FROM repair_attempts WHERE was_successful = 0"),
            "verified_safety_procedures": scalar(
                "SELECT COUNT(*) AS n FROM safety_procedures WHERE active = 1"
            ),
            "extraction_records": scalar("SELECT COUNT(*) AS n FROM document_extractions"),
        }

    # ------------------------------------------------------------------
    # Safety
    # ------------------------------------------------------------------
    def safety_for(self, *, component: Optional[str], task: Optional[str], limit: int = 4) -> Dict[str, Any]:
        """Safety guidance for an inspection, from approved sources only."""
        placeholder = "%s" if db.use_mysql else "?"
        rows = db.execute_query(
            "SELECT procedure_id, title, subsystem, task, steps_json, source_document_id, source_revision, "
            "source_ref, quality_level FROM safety_procedures WHERE active = 1"
        )
        matching = []
        needle = " ".join(filter(None, [component, task])).lower()
        for row in rows:
            haystack = " ".join(str(row.get(k) or "") for k in ("title", "subsystem", "task")).lower()
            if not needle or any(word in haystack for word in needle.split() if len(word) > 3):
                try:
                    row["steps"] = json.loads(row.get("steps_json") or "[]")
                except Exception:
                    row["steps"] = []
                matching.append(row)

        # Approved documents that contain safety-relevant passages, with their source.
        doc_rows = db.execute_query(
            "SELECT c.chunk_id, c.document_id, d.document_name, c.page_number, c.section_heading, c.chunk_text, "
            "v.revision, v.status "
            "FROM document_chunks c JOIN documents d ON c.document_id = d.document_id "
            "LEFT JOIN document_versions v ON v.document_id = c.document_id "
            "WHERE v.status IN ('CURRENT','APPROVED') AND ("
            "LOWER(c.chunk_text) LIKE '%relieve%' OR LOWER(c.chunk_text) LIKE '%lockout%' "
            "OR LOWER(c.chunk_text) LIKE '%safety%' OR LOWER(c.chunk_text) LIKE '%caution%' "
            "OR LOWER(c.section_heading) LIKE '%safety%') "
            f"LIMIT {int(limit)}"
        )

        return {
            "approved_procedures": matching[:limit],
            "document_excerpts": doc_rows,
            "standing_advisory": [
                "Apply the machine's lockout/tagout procedure before any physical intervention.",
                "Relieve hydraulic pressure at the accumulator and pilot circuit before opening any line.",
                "Never work under an unblocked attachment.",
            ],
            "standing_advisory_source": (
                "Platform standing advisory — not sourced from an approved document on this machine."
                if not matching and not doc_rows
                else "Platform standing advisory (listed in addition to the approved sources above)."
            ),
            "note": (
                "No approved safety procedure matching this inspection was found in the knowledge base."
                if not matching and not doc_rows
                else "Safety information below is taken from approved documents in the knowledge base."
            ),
        }


knowledge_service = KnowledgeService()
