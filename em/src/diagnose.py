import requests
import json

def ask_qwen(symptoms, historical_cases):

    evidence = "\n\n".join([
        f"""Case ID: {case['case_id']}
Component: {case['component']}
Symptom: {case['symptom']}
Failure Mode: {case['failure_mode']}
Inspection: {case['inspection_finding']}
Repair: {case['repair_action']}
Outcome: {case['outcome']}
Similarity: {case['similarity']:.3f}"""
        for case in historical_cases
    ])

    prompt = f"""
You are an industrial maintenance engineer.

Analyze the current excavator problem using ONLY the historical
engineering cases provided below.

CURRENT SYMPTOMS:
{symptoms}

HISTORICAL ENGINEERING CASES:
{evidence}

Return a JSON object with:
{{
  "likely_cause": "...",
  "component": "...",
  "reason": "...",
  "recommended_inspection": ["..."],
  "previous_successful_resolution": "..."
}}

Do not invent historical evidence.
"""

    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "qwen3:4b",
            "prompt": prompt,
            "stream": False
        }
    )

    return response.json()["response"]


if __name__ == "__main__":

    cases = [
        {
            "case_id": "CASE-001",
            "component": "Hydraulic Pump",
            "symptom": "Slow boom movement; weak digging force",
            "failure_mode": "Internal pump leakage",
            "inspection_finding": "Hydraulic pressure dropped when oil temperature increased",
            "repair_action": "Hydraulic pump replaced",
            "outcome": "Hydraulic performance restored",
            "similarity": 0.91
        }
    ]

    result = ask_qwen(
        "Excavator has slow boom movement and weak digging force.",
        cases
    )

    print("\nQWEN DIAGNOSIS")
    print("=" * 60)
    print(result)