"""Audit log API (brief §22). Read-only: audit rows are append-only by design."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from backend.app.api.auth import require_role
from backend.app.services.audit_service import audit_service

router = APIRouter(prefix="/api/audit", tags=["Audit Log"])


@router.get("")
def list_audit(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    machine_id: Optional[str] = None,
    investigation_id: Optional[str] = None,
    user: dict = Depends(require_role("ADMIN")),
):
    return audit_service.list(
        limit=limit,
        offset=offset,
        action=action,
        entity_type=entity_type,
        machine_id=machine_id,
        investigation_id=investigation_id,
    )
