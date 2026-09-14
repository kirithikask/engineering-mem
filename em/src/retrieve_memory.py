import pandas as pd
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer


# --------------------------------------------------
# 1. Load Engineering Memory
# --------------------------------------------------

index = faiss.read_index(
    "models/engineering_memory.faiss"
)

cases = pd.read_csv(
    "models/engineering_memory_metadata.csv"
)

print("Engineering Memory loaded:", index.ntotal, "cases")


# --------------------------------------------------
# 2. Load BGE model
# --------------------------------------------------

model = SentenceTransformer(
    "BAAI/bge-small-en-v1.5"
)


# --------------------------------------------------
# 3. Get current machine and symptoms
# --------------------------------------------------

machine_id = input(
    "\nEnter Machine ID: "
).strip()

symptoms = input(
    "Enter current symptoms: "
).strip()


# --------------------------------------------------
# 4. Create query
# --------------------------------------------------

query = (
    "Machine: " + machine_id +
    " | Current symptoms: " + symptoms
)


# --------------------------------------------------
# 5. Convert query to embedding
# --------------------------------------------------

query_embedding = model.encode(
    [query],
    normalize_embeddings=True
)

query_embedding = np.array(
    query_embedding,
    dtype="float32"
)


# --------------------------------------------------
# 6. Search FAISS
# --------------------------------------------------

k = min(3, index.ntotal)

scores, results = index.search(
    query_embedding,
    k
)


# --------------------------------------------------
# 7. Display results
# --------------------------------------------------

print("\n" + "=" * 70)
print("ENGINEERING MEMORY — HISTORICAL MATCHES")
print("=" * 70)

for rank, (idx, score) in enumerate(
    zip(results[0], scores[0]),
    start=1
):

    case = cases.iloc[idx]

    print(f"\n#{rank}  Similarity: {score:.3f}")
    print("-" * 70)

    print("Case ID       :", case["case_id"])
    print("Machine       :", case["machine_id"])
    print("Component     :", case["component"])
    print("Symptom       :", case["symptom"])
    print("Failure Mode  :", case["failure_mode"])
    print("Inspection    :", case["inspection_finding"])
    print("Repair        :", case["repair_action"])
    print("Outcome       :", case["outcome"])