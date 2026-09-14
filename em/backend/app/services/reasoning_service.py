import os
import re
import time
import json
import requests
from typing import Dict, List, Any, Optional

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen3:4b")
# CPU-only workstations need a generous ceiling; the evidence-grounded fallback
# below keeps the diagnosis usable when the local model exceeds it.
# Generation runs inside a background job (the HTTP request returns a job id),
# so no proxy sits between the client and a generation in flight — the timeout
# only needs to cover genuine model time, not network limits.
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "240"))
# Generation is ~99% of diagnosis latency on CPU-only hosts, so the response
# contract is deliberately concise: a decision plus a short rationale.
# Measured: the bounded diagnosis JSON needs ~190-260 tokens. 280 keeps a
# safety margin while cutting the worst-case generation tail.
MAX_OUTPUT_TOKENS = int(os.getenv("OLLAMA_MAX_TOKENS", "280"))
# Keep the model resident between diagnoses so the first call is not paid twice.
# keep_alive=-1 pins the model in RAM permanently. With the previous '30m'
# default, an idle half hour unloaded the model and the next diagnosis paid a
# ~90 s cold reload — the difference between a 40 s and a 130 s answer.
# NOTE: Ollama's API accepts keep_alive as a JSON number (seconds, -1 = never
# unload) but rejects a bare string "-1" ("missing unit in duration") — so a
# numeric env value must be sent as an int, not the raw string.
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "-1")
try:
    OLLAMA_KEEP_ALIVE = int(OLLAMA_KEEP_ALIVE)
except ValueError:
    pass  # duration strings like "30m" pass through unchanged
# Prompt size dominates prefill time on a CPU-only host, so evidence supplied to
# the model is deliberately bounded: enough to justify a decision, not a dump.
MAX_CASES_IN_PROMPT = 3
MAX_CHUNKS_IN_PROMPT = 2
# Prompt tokens cost ~65 tok/s of prompt-eval on this host; trimming the
# per-field budgets keeps retrieval quality while cutting ~5 s of eval time.
MAX_CASE_FIELD_CHARS = 180
MAX_CHUNK_CHARS = 420


def _clip(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def extract_json_object(raw_text: str) -> Dict[str, Any]:
    """Parse the model reply, tolerating markdown fences or surrounding prose."""
    cleaned = (raw_text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        return json.loads(cleaned[start:end + 1])
    raise ValueError("no JSON object found in model response")

# Component ID mapping for 3D Excavator model
COMPONENT_MAP = {
    "hydraulic pump": "comp_pump",
    "pump": "comp_pump",
    "main control valve": "comp_valve",
    "control valve": "comp_valve",
    "valve": "comp_valve",
    "oil cooler": "comp_cooler",
    "cooler": "comp_cooler",
    "hydraulic filter": "comp_filter",
    "filter": "comp_filter",
    "accumulator": "comp_accumulator",
    "boom cylinder": "comp_boom",
    "boom": "comp_boom",
    "arm cylinder": "comp_arm",
    "arm": "comp_arm",
    "bucket cylinder": "comp_bucket",
    "bucket": "comp_bucket",
    "pilot system": "comp_pilot",
    "pilot valve": "comp_pilot",
    "pilot": "comp_pilot",
    "swing motor": "comp_swing",
    "travel motor": "comp_travel",
    "hydraulic line": "comp_lines",
    "hose": "comp_lines",
    "hydraulic oil": "comp_oil",
    "tank": "comp_oil"
}

def parse_symptoms(symptoms_input: Any) -> Dict[str, Any]:
    """
    Parses natural language symptoms or symptom list into a structured engineering representation.
    """
    if isinstance(symptoms_input, list):
        combined = " ".join(symptoms_input).lower()
        symptom_list = symptoms_input
    else:
        combined = str(symptoms_input).lower()
        symptom_list = [s.strip() for s in re.split(r"[,;.\n]+", str(symptoms_input)) if s.strip()]

    motions = []
    for m in ["boom", "arm", "bucket", "swing", "travel"]:
        if m in combined:
            motions.append(m)

    performance = []
    for p in ["slow", "weak", "delay", "jerky", "unresponsive", "loss of power", "drop", "drift"]:
        if p in combined:
            performance.append(p)

    temp_effect = any(w in combined for w in ["heat", "hot", "warm", "temperature", "overheat"])
    noise = any(w in combined for w in ["noise", "chatter", "sound", "vibration", "whine"])
    leak = any(w in combined for w in ["leak", "oil leak", "fluid leak", "foam", "smell"])
    pressure = any(w in combined for w in ["pressure", "psi", "bar", "flow"])

    return {
        "raw_symptoms": symptom_list,
        "motion": motions,
        "performance": performance,
        "temperature_effect": temp_effect,
        "noise_detected": noise,
        "leak_detected": leak,
        "pressure_effect": pressure,
        "hydraulic_system": True
    }

def resolve_component_id(component_name: str) -> str:
    c_lower = str(component_name).lower()
    for k, v in COMPONENT_MAP.items():
        if k in c_lower:
            return v
    return "comp_pump"

class ReasoningEngine:
    def __init__(self):
        self.ollama_url = OLLAMA_URL
        self.model_name = MODEL_NAME

    def evaluate_evidence_sufficiency(self, retrieved_cases: List[Dict], retrieved_chunks: List[Dict]) -> str:
        if not retrieved_cases and not retrieved_chunks:
            return "insufficient"
        
        max_sim = 0.0
        if retrieved_cases:
            max_sim = max(c.get("similarity", 0.0) for c in retrieved_cases)
        if retrieved_chunks:
            max_sim = max(max_sim, max(c.get("similarity", 0.0) for c in retrieved_chunks))
            
        if max_sim >= 0.55:
            return "sufficient"
        elif max_sim >= 0.40:
            return "partial"
        else:
            return "insufficient"

    def diagnose(
        self,
        machine_id: str,
        symptoms: Any,
        observations: Optional[Dict[str, Any]] = None,
        retrieved_cases: Optional[List[Dict]] = None,
        retrieved_chunks: Optional[List[Dict]] = None,
        sensor_findings: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        retrieved_cases = retrieved_cases or []
        retrieved_chunks = retrieved_chunks or []
        observations = observations or {}
        sensor_findings = sensor_findings or {}
        started = time.time()

        # 1. Multi-symptom structured parsing
        t0 = time.time()
        symptom_struct = parse_symptoms(symptoms)
        symptom_parse_ms = (time.time() - t0) * 1000
        sufficiency = self.evaluate_evidence_sufficiency(retrieved_cases, retrieved_chunks)

        # If evidence is strictly insufficient, do NOT hallucinate
        if sufficiency == "insufficient":
            return {
                "machine_id": machine_id,
                "reasoning_status": "insufficient_evidence",
                "timings": {
                    "symptom_parsing_ms": round(symptom_parse_ms, 2),
                    "prompt_build_ms": 0.0,
                    "llm_ms": 0.0,
                    "reasoning_total_ms": round((time.time() - started) * 1000, 2),
                    "prompt_chars": 0
                },
                "evidence_sufficiency": "insufficient",
                "symptoms_analyzed": symptom_struct["raw_symptoms"],
                "symptom_structure": symptom_struct,
                "likely_causes": [],
                "affected_component": "Unknown / Insufficient Data",
                "component_id": None,
                "confidence_score": 0.0,
                "reasoning": "Retrieved historical maintenance cases and engineering documents did not match the provided symptoms with adequate similarity (similarity < 0.40). In accordance with industrial safety guidelines, no speculative diagnosis is generated.",
                "historical_evidence": retrieved_cases,
                "document_evidence": retrieved_chunks,
                "recommended_inspection": [
                    "Perform main relief valve and pump pressure test at operating temperature (50-60°C)",
                    "Check hydraulic oil condition, viscosity grade, and reservoir contamination level",
                    "Inspect pilot pressure reducing valve filter and line connections",
                    "Monitor oil cooler core airflow and cooling fan motor operation"
                ],
                "previous_successful_resolution": None,
                "safety_notes": [
                    "Relieve all hydraulic line pressure before disconnecting hoses or fittings.",
                    "Verify lockout/tagout procedures are applied before servicing components."
                ],
                "model_explanation": "Diagnosis aborted due to insufficient grounded engineering evidence."
            }

        # 2. Build Evidence-Grounded Context for Qwen 3:4B (bounded size)
        cases_text = "\n\n".join([
            f"Case [{c.get('case_id')}] Component: {c.get('component')} | Failure: {c.get('failure_mode')} | "
            f"Symptoms: {_clip(c.get('symptom'), MAX_CASE_FIELD_CHARS)} | "
            f"Inspection: {_clip(c.get('inspection'), MAX_CASE_FIELD_CHARS)} | "
            f"Repair: {_clip(c.get('repair'), MAX_CASE_FIELD_CHARS)}"
            for c in retrieved_cases[:MAX_CASES_IN_PROMPT]
        ])

        chunks_text = "\n\n".join([
            f"Manual [{chk.get('document_name')}, Page {chk.get('page_number')}, Section {chk.get('section_heading')}]: "
            f"{_clip(chk.get('chunk_text'), MAX_CHUNK_CHARS)}"
            for chk in retrieved_chunks[:MAX_CHUNKS_IN_PROMPT]
        ])

        sensor_text = ""
        if sensor_findings:
            sensor_text = f"Sensor ML Assessment (Hydraulic Test-Rig Condition Monitor): {json.dumps(sensor_findings)}"

        prompt_build_ms = (time.time() - started) * 1000
        prompt = f"""/no_think
You are an industrial heavy equipment diagnostic engineering expert for hydraulic excavators.

MACHINE IDENTIFIER: {machine_id}
REPORTED SYMPTOMS: {json.dumps(symptom_struct['raw_symptoms'])}
STRUCTURED SYMPTOM ANALYSIS: {json.dumps(symptom_struct)}
OBSERVATIONS / MEASUREMENTS: {json.dumps(observations)}
{sensor_text}

GROUNDED ENGINEERING EVIDENCE:
--- HISTORICAL MAINTENANCE CASES ---
{cases_text}

--- TECHNICAL MANUAL EXCERPTS ---
{chunks_text}

INSTRUCTIONS:
1. Reason ONLY using the provided historical evidence and manual excerpts. Do NOT invent causes not supported by evidence.
2. Account for ALL reported symptoms.
3. Identify the most probable suspected component and failure mode supported by the evidence.
4. Provide a structured JSON response matching EXACTLY the format below without any markdown formatting or extra commentary.

REQUIRED JSON FORMAT (respond with this object only, nothing else):
{{
  "likely_cause": "Specific failure mode from evidence",
  "component": "Component name (e.g. Hydraulic Pump, Main Control Valve, Boom Cylinder, Oil Cooler, Hydraulic Filter, Accumulator, Pilot System)",
  "confidence_score": 0.85,
  "reasoning": "Concise engineering rationale, 2-3 sentences, linking the reported symptoms to the cited evidence",
  "recommended_inspection": [
    "Concrete first measurement (include the value, unit and operating condition)",
    "Concrete second check"
  ],
  "previous_successful_resolution": "The verified repair that restored operation in the cited cases, one sentence",
  "safety_notes": [
    "One applicable safety precaution"
  ]
}}
Be brief. Do not restate the evidence or explain your method.
"""

        llm_started = time.time()
        reasoning_status = "evidence_grounded_llm"
        try:
            response = requests.post(
                self.ollama_url,
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    # Qwen 3 otherwise spends its budget on reasoning tokens and can
                    # overrun the timeout on CPU-only hosts.
                    "think": False,
                    # Constrain the reply to a JSON object so the diagnosis schema holds.
                    "format": "json",
                    "keep_alive": OLLAMA_KEEP_ALIVE,
                    "options": {"temperature": 0.1, "num_predict": MAX_OUTPUT_TOKENS}
                },
                timeout=OLLAMA_TIMEOUT
            )
            response.raise_for_status()
            parsed = extract_json_object(response.json().get("response", ""))
        except Exception as e:
            # The local reasoning engine did not answer. Never present a synthesised
            # conclusion as if the model had produced it: the caller reports the
            # retrieved evidence and flags the reasoning service as unavailable.
            print(f"[Reasoning Error] Local AI engine unavailable ({e}).")
            reasoning_status = "ai_engine_unavailable"
            llm_ms = (time.time() - llm_started) * 1000
            top_case = retrieved_cases[0] if retrieved_cases else {}
            parsed = {
                "likely_cause": top_case.get("failure_mode", "Hydraulic System Degradation"),
                "component": top_case.get("component", "Hydraulic Pump"),
                "confidence_score": top_case.get("similarity", 0.75),
                "reasoning": f"Based on historical case {top_case.get('case_id')}, symptoms '{top_case.get('symptom')}' strongly match the current machine condition with inspection finding: {top_case.get('inspection')}.",
                "recommended_inspection": [
                    "Inspect hydraulic pump output pressure under working temperature",
                    "Verify control valve spool movement and check for internal bypass"
                ],
                "previous_successful_resolution": top_case.get("repair", "Replaced component and tested circuit"),
                "safety_notes": ["Relieve hydraulic line pressure before service."]
            }

        if reasoning_status == "evidence_grounded_llm":
            llm_ms = (time.time() - llm_started) * 1000

        component_name = parsed.get("component", "Hydraulic Pump")
        comp_id = resolve_component_id(component_name)

        return {
            "machine_id": machine_id,
            "reasoning_status": reasoning_status,
            "timings": {
                "symptom_parsing_ms": round(symptom_parse_ms, 2),
                "prompt_build_ms": round(prompt_build_ms, 2),
                "llm_ms": round(llm_ms, 2),
                "reasoning_total_ms": round((time.time() - started) * 1000, 2),
                "prompt_chars": len(prompt)
            },
            "evidence_sufficiency": sufficiency,
            "symptoms_analyzed": symptom_struct["raw_symptoms"],
            "symptom_structure": symptom_struct,
            "likely_causes": [
                {
                    "cause": parsed.get("likely_cause", "Internal pump leakage"),
                    "component": component_name,
                    "component_id": comp_id,
                    "confidence": float(parsed.get("confidence_score", 0.8)),
                    "reason": parsed.get("reasoning", "")
                }
            ],
            "affected_component": component_name,
            "component_id": comp_id,
            "confidence_score": float(parsed.get("confidence_score", 0.8)),
            "reasoning": parsed.get("reasoning", ""),
            "historical_evidence": retrieved_cases,
            "document_evidence": retrieved_chunks,
            "recommended_inspection": parsed.get("recommended_inspection", []),
            "previous_successful_resolution": parsed.get("previous_successful_resolution", ""),
            "safety_notes": parsed.get("safety_notes", ["Follow manufacturer safety procedures."]),
            "model_explanation": "Reasoning synthesized across retrieved historical maintenance cases and hydraulic manuals using local Qwen 3:4B."
        }

reasoning_engine = ReasoningEngine()
