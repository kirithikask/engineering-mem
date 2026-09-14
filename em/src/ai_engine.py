import pandas as pd
import numpy as np
import faiss
import requests
import json
from sentence_transformers import SentenceTransformer

INDEX = "models/engineering_memory.faiss"
META = "models/engineering_memory_metadata.csv"

model = SentenceTransformer("BAAI/bge-small-en-v1.5")
index = faiss.read_index(INDEX)
cases = pd.read_csv(META)


def diagnose(machine_id, symptoms):

    query = f"Machine: {machine_id} | Current symptoms: {symptoms}"

    embedding = model.encode(
        [query],
        normalize_embeddings=True
    ).astype("float32")

    scores, results = index.search(
        embedding,
        min(3, index.ntotal)
    )

    # Check whether enough historical evidence exists
    best_score = float(scores[0][0])

    if best_score < 0.45:
        return {
            "machine_id": machine_id,
            "evidence_sufficiency": "insufficient",
            "likely_causes": [],
            "recommended_inspection": [
                "Collect additional machine symptoms",
                "Check hydraulic pressure",
                "Check hydraulic oil temperature"
            ],
            "previous_successful_resolution": None,
            "historical_evidence": []
        }

    historical_cases = []

    for idx, score in zip(results[0], scores[0]):

        case = cases.iloc[idx]

        historical_cases.append({
            "case_id": case["case_id"],
            "component": case["component"],
            "symptom": case["symptom"],
            "failure_mode": case["failure_mode"],
            "inspection": case["inspection_finding"],
            "repair": case["repair_action"],
            "outcome": case["outcome"],
            "similarity": round(float(score), 3)
        })

    evidence = "\n\n".join(
        str(c) for c in historical_cases
    )

    prompt = f"""
You are an industrial maintenance diagnosis engine.

Machine: {machine_id}

Current symptoms:
{symptoms}

Historical engineering evidence:
{evidence}

Use ONLY the historical evidence.

Return ONLY valid JSON. No markdown.

Format:

{{
  "machine_id": "{machine_id}",
  "evidence_sufficiency": "sufficient",
  "likely_causes": [
    {{
      "cause": "...",
      "component": "...",
      "score": 0.0,
      "reason": "..."
    }}
  ],
  "recommended_inspection": [
    "..."
  ],
  "previous_successful_resolution": "...",
  "historical_evidence": []
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

    raw = response.json()["response"]

    try:
        result = json.loads(raw)

    except Exception:
        result = {
            "machine_id": machine_id,
            "evidence_sufficiency": "insufficient",
            "likely_causes": [],
            "recommended_inspection": [],
            "previous_successful_resolution": None,
            "historical_evidence": historical_cases,
            "raw_response": raw
        }

    result["historical_evidence"] = historical_cases

    return result


if __name__ == "__main__":

    result = diagnose(
        "EXC-001",
        "Slow boom movement and weak digging force"
    )

    print("\nENGINEERING MEMORY DIAGNOSIS")
    print("=" * 60)

    print(json.dumps(result, indent=2))