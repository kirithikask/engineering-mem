"""
Machine passport and QR access (brief §3 feature 2, §13).

The QR code is functional, not decorative: it encodes a URL containing a token
that resolves through ``POST /api/machines/scan/{token}`` to a real machine id in
the database, and a scan is recorded in the audit log with a scan counter.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.api.auth import get_current_user
from backend.app.services.investigation_service import investigation_service

router = APIRouter(prefix="/api/machines", tags=["Machine Passport"])


def _base_url(request: Request) -> str:
    configured = None
    import os

    configured = os.getenv("EM_PUBLIC_BASE_URL")
    if configured:
        return configured
    return str(request.base_url).rstrip("/")


@router.get("/{machine_id}/passport")
def passport(machine_id: str, request: Request, user: dict = Depends(get_current_user)):
    result = investigation_service.machine_passport(machine_id, base_url=_base_url(request), user=user)
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("detail"))
    return result


@router.post("/{machine_id}/scan")
def scan_machine_code(machine_id: str, request: Request, user: dict = Depends(get_current_user)):
    """Technician scanned this machine's tag: return the passport entry point."""
    result = investigation_service.scan_machine(machine_id, user=user, base_url=_base_url(request))
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("detail"))
    return result


@router.get("/scan/{token}")
def resolve_token(token: str, request: Request, user: dict = Depends(get_current_user)):
    """Resolve a scanned QR token (used by the /m/<token> route on a phone)."""
    result = investigation_service.scan_machine(token, user=user, base_url=_base_url(request))
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("detail"))
    return result


@router.post("/scan/{token}")
def resolve_token_post(token: str, request: Request, user: dict = Depends(get_current_user)):
    result = investigation_service.scan_machine(token, user=user, base_url=_base_url(request))
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("detail"))
    return result


@router.get("/{machine_id}/qr")
def qr(machine_id: str, request: Request, user: dict = Depends(get_current_user)):
    passport_data = investigation_service.machine_passport(machine_id, base_url=_base_url(request), user=user)
    if passport_data.get("status") == "error":
        raise HTTPException(status_code=404, detail=passport_data.get("detail"))
    return {"machine_id": machine_id, "qr": passport_data.get("qr")}
