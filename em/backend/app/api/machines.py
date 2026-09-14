from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from backend.app.db.mysql_client import db

router = APIRouter(prefix="/api/machines", tags=["Machines"])

@router.get("")
def get_all_machines():
    # Machines with a recorded odometer reading lead the list: they carry enough
    # context to diagnose against, and they are what the workstation should open on
    # rather than whichever placeholder ID happens to sort first.
    query = (
        "SELECT machine_id, machine_model, machine_type, manufacturer, operating_hours, "
        "status, last_maintenance FROM machines "
        "ORDER BY CASE WHEN operating_hours IS NULL OR operating_hours = 0 THEN 1 ELSE 0 END, "
        "machine_id ASC"
    )
    machines = db.execute_query(query)
    return {"machines": machines}

@router.get("/{machine_id}")
def get_machine_detail(machine_id: str):
    q_machine = "SELECT * FROM machines WHERE machine_id = %s" if db.use_mysql else "SELECT * FROM machines WHERE machine_id = ?"
    machines = db.execute_query(q_machine, (machine_id,))
    if not machines:
        raise HTTPException(status_code=404, detail="Machine not found")
    
    machine = machines[0]
    
    # Fetch recent maintenance cases for this machine
    q_cases = "SELECT case_id, subsystem, component, failure_mode, symptom, inspection_finding, repair_action, outcome, operating_hours FROM maintenance_cases WHERE machine_id = %s ORDER BY created_at DESC LIMIT 10" if db.use_mysql else "SELECT case_id, subsystem, component, failure_mode, symptom, inspection_finding, repair_action, outcome, operating_hours FROM maintenance_cases WHERE machine_id = ? ORDER BY created_at DESC LIMIT 10"
    cases = db.execute_query(q_cases, (machine_id,))

    # Fetch recent diagnoses
    q_diag = "SELECT diagnosis_id, timestamp, symptoms_analyzed, evidence_sufficiency, likely_cause, affected_component, component_id, confidence_score, reasoning FROM diagnoses WHERE machine_id = %s ORDER BY timestamp DESC LIMIT 5" if db.use_mysql else "SELECT diagnosis_id, timestamp, symptoms_analyzed, evidence_sufficiency, likely_cause, affected_component, component_id, confidence_score, reasoning FROM diagnoses WHERE machine_id = ? ORDER BY timestamp DESC LIMIT 5"
    diagnoses = db.execute_query(q_diag, (machine_id,))

    # Component status list
    q_comp = "SELECT component_id, component_name, subsystem, mesh_name, description FROM components"
    components = db.execute_query(q_comp)

    return {
        "machine": machine,
        "recent_cases": cases,
        "recent_diagnoses": diagnoses,
        "components": components
    }
