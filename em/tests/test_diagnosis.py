import os
import sys

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("backend"))

from backend.app.services.reasoning_service import parse_symptoms, reasoning_engine

def test_symptom_parsing():
    raw = ["Boom is slow", "Weak digging force", "Oil heats up during long shift"]
    parsed = parse_symptoms(raw)
    assert "boom" in parsed["motion"]
    assert "slow" in parsed["performance"] or "weak" in parsed["performance"]
    assert parsed["temperature_effect"] is True
    print(f"[PASS] Symptom parsing passed: motion={parsed['motion']}, temp_effect={parsed['temperature_effect']}")

def test_insufficient_evidence():
    # If no evidence provided, should return insufficient
    res = reasoning_engine.diagnose("EXC-001", ["Gibberish symptom unrelated"], {}, [], [], {})
    assert res["evidence_sufficiency"] == "insufficient"
    assert len(res["recommended_inspection"]) > 0
    print("[PASS] Insufficient evidence protection passed: No hallucination, returned inspections.")

if __name__ == "__main__":
    print("--- Running Diagnosis Engine Tests ---")
    test_symptom_parsing()
    test_insufficient_evidence()
    print("ALL DIAGNOSIS TESTS PASSED.")
