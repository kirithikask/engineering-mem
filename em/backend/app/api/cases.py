import uuid
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from backend.app.schemas.schemas import CreateCaseRequest
from backend.app.api.auth import get_current_user
from backend.app.db.mysql_client import db

router = APIRouter(prefix="/api/cases", tags=["Historical Cases"])

MAX_PAGE_SIZE = 500


@router.get("")
def list_cases(
    component: Optional[str] = None,
    machine_id: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Browse the case archive. Returns a real total so clients can paginate."""
    ph = "%s" if db.use_mysql else "?"
    conditions = []
    params: List[Any] = []

    if component:
        conditions.append(f"component LIKE {ph}")
        params.append(f"%{component}%")
    if machine_id:
        conditions.append(f"machine_id = {ph}")
        params.append(machine_id)
    if q:
        conditions.append(
            f"(case_id LIKE {ph} OR symptom LIKE {ph} OR failure_mode LIKE {ph} "
            f"OR component LIKE {ph} OR repair_action LIKE {ph})"
        )
        params.extend([f"%{q}%"] * 5)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    total_rows = db.execute_query(f"SELECT COUNT(*) AS n FROM maintenance_cases{where}", tuple(params))
    total = int(total_rows[0]["n"]) if total_rows else 0

    limit = max(1, min(limit, MAX_PAGE_SIZE))
    offset = max(0, offset)
    query = (
        "SELECT case_id, machine_id, subsystem, component, failure_mode, symptom, "
        "inspection_finding, repair_action, outcome, operating_hours, is_verified, "
        f"source_type, created_at FROM maintenance_cases{where} "
        f"ORDER BY created_at DESC, case_id ASC LIMIT {ph} OFFSET {ph}"
    )
    cases = db.execute_query(query, tuple(params + [limit, offset]))
    return {"cases": cases, "total": total, "limit": limit, "offset": offset}

@router.get("/{case_id}")
def get_case_detail(case_id: str):
    query = "SELECT * FROM maintenance_cases WHERE case_id = %s" if db.use_mysql else "SELECT * FROM maintenance_cases WHERE case_id = ?"
    cases = db.execute_query(query, (case_id,))
    if not cases:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"case": cases[0]}

@router.post("")
def create_case(req: CreateCaseRequest, user: dict = Depends(get_current_user)):
    case_id = f"CASE-{uuid.uuid4().hex[:6].upper()}"
    db.execute_write(
        "INSERT INTO maintenance_cases (case_id, machine_id, subsystem, component, failure_mode, symptom, inspection_finding, repair_action, outcome, operating_hours, is_verified, source_type) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 'field_entry')" if db.use_mysql else
        "INSERT INTO maintenance_cases (case_id, machine_id, subsystem, component, failure_mode, symptom, inspection_finding, repair_action, outcome, operating_hours, is_verified, source_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'field_entry')",
        (
            case_id,
            req.machine_id,
            "Hydraulic System",
            req.component,
            req.failure_mode,
            req.symptom,
            req.inspection_finding,
            req.repair_action,
            req.outcome,
            req.operating_hours
        )
    )
    return {"status": "success", "case_id": case_id}
