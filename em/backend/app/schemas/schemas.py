from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# Auth Schemas
class LoginRequest(BaseModel):
    username: str
    password: str

class SignupRequest(BaseModel):
    full_name: str
    email: str
    username: str
    password: str
    role: str = "TECHNICIAN"

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]

# Machine Schemas
class MachineSchema(BaseModel):
    machine_id: str
    machine_model: str
    machine_type: str
    manufacturer: str
    operating_hours: int
    status: str
    last_maintenance: Optional[str] = None

# Case Schemas
class MaintenanceCaseSchema(BaseModel):
    case_id: str
    machine_id: str
    subsystem: Optional[str] = "Hydraulic System"
    component: str
    failure_mode: str
    symptom: str
    inspection_finding: Optional[str] = None
    repair_action: Optional[str] = None
    outcome: Optional[str] = None
    operating_hours: Optional[int] = 5000
    is_verified: Optional[int] = 1

class CreateCaseRequest(BaseModel):
    machine_id: str
    component: str
    failure_mode: str
    symptom: str
    inspection_finding: str
    repair_action: str
    outcome: str = "Hydraulic performance restored"
    operating_hours: Optional[int] = 6000

# Diagnosis Schemas
class DiagnoseRequest(BaseModel):
    machine_id: str
    symptoms: List[str]
    observations: Optional[Dict[str, Any]] = None
    sensor_telemetry: Optional[Dict[str, float]] = None

class ConfirmDiagnosisRequest(BaseModel):
    diagnosis_id: Optional[str] = None
    machine_id: str
    component: str
    failure_mode: str
    symptoms: str
    actual_finding: str
    repair_performed: str
    outcome: str = "Successful resolution"

class DiagnoseResponse(BaseModel):
    machine_id: str
    # "evidence_grounded_llm" when local Qwen answered, "ai_engine_unavailable" when
    # it could not, "insufficient_evidence" when no grounded decision is possible.
    reasoning_status: Optional[str] = None
    timings: Optional[Dict[str, Any]] = None
    machine: Optional[Dict[str, Any]] = None
    retrieval_id: Optional[str] = None
    diagnosis_id: Optional[str] = None
    evidence_sufficiency: str
    symptoms_analyzed: List[str]
    symptom_structure: Optional[Dict[str, Any]] = None
    likely_causes: List[Dict[str, Any]]
    affected_component: str
    component_id: Optional[str] = None
    confidence_score: float
    reasoning: str
    historical_evidence: List[Dict[str, Any]]
    document_evidence: List[Dict[str, Any]]
    sensor_evidence: Optional[Dict[str, Any]] = None
    recommended_inspection: List[str]
    previous_successful_resolution: Optional[str] = None
    safety_notes: List[str]
    model_explanation: str
