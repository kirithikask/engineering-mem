"""
Auditability (brief §22).

Every state-changing action in the extension modules writes one audit row:
who, when, on which machine/investigation, what was retrieved or decided, and what
the operator did next. Rows are append-only; nothing in the platform deletes or
edits them.

Audit writes are best-effort by design: a failed audit write must never abort a
technician's inspection, but it is printed to the server log so it is visible.
"""

import json
import uuid
from typing import Any, Dict, List, Optional

from backend.app.db.mysql_client import db


def _json(value: Any) -> str:
    try:
        return json.dumps(value, default=str)
    except Exception:
        return "{}"


class AuditService:
    def record(
        self,
        *,
        user: Optional[Dict[str, Any]],
        action: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        machine_id: Optional[str] = None,
        investigation_id: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
        outcome: str = "OK",
    ) -> str:
        audit_id = f"AUD-{uuid.uuid4().hex[:10].upper()}"
        user = user or {}
        try:
            db.execute_write(
                "INSERT INTO audit_logs (audit_id, user_id, username, role, action, entity_type, entity_id, machine_id, "
                "investigation_id, outcome, detail_json) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                if db.use_mysql else
                "INSERT INTO audit_logs (audit_id, user_id, username, role, action, entity_type, entity_id, machine_id, "
                "investigation_id, outcome, detail_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    audit_id,
                    user.get("user_id"),
                    user.get("username"),
                    user.get("role"),
                    action,
                    entity_type,
                    entity_id,
                    machine_id,
                    investigation_id,
                    outcome,
                    _json(detail or {}),
                ),
            )
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[Audit] write failed for {action}: {exc}")
        return audit_id

    def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        action: Optional[str] = None,
        entity_type: Optional[str] = None,
        machine_id: Optional[str] = None,
        investigation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        placeholder = "%s" if db.use_mysql else "?"
        conditions, params = [], []
        if action:
            conditions.append(f"action LIKE {placeholder}")
            params.append(f"%{action}%")
        if entity_type:
            conditions.append(f"entity_type = {placeholder}")
            params.append(entity_type)
        if machine_id:
            conditions.append(f"machine_id = {placeholder}")
            params.append(machine_id)
        if investigation_id:
            conditions.append(f"investigation_id = {placeholder}")
            params.append(investigation_id)
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

        total_rows = db.execute_query(f"SELECT COUNT(*) AS n FROM audit_logs{where}", tuple(params))
        rows = db.execute_query(
            "SELECT audit_id, user_id, username, role, action, entity_type, entity_id, machine_id, investigation_id, "
            f"outcome, detail_json, created_at FROM audit_logs{where} ORDER BY created_at DESC "
            f"LIMIT {int(limit)} OFFSET {int(offset)}",
            tuple(params),
        )
        for row in rows:
            try:
                row["detail"] = json.loads(row.pop("detail_json") or "{}")
            except Exception:
                row["detail"] = {}
        return {
            "logs": rows,
            "total": int(total_rows[0]["n"]) if total_rows else 0,
            "limit": int(limit),
            "offset": int(offset),
        }


audit_service = AuditService()
