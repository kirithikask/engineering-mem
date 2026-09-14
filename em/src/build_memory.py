import pandas as pd
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import os

# --------------------------------------------------
# 1. Load maintenance cases
# --------------------------------------------------

cases = pd.read_csv("data/maintenance_cases.csv")

print("Maintenance cases loaded:", len(cases))


# --------------------------------------------------
# 2. Create searchable engineering memory
# --------------------------------------------------

cases["search_text"] = (
    "Machine: " + cases["machine_id"].astype(str) +
    " | Subsystem: " + cases["subsystem"].astype(str) +
    " | Component: " + cases["component"].astype(str) +
    " | Symptom: " + cases["symptom"].astype(str) +
    " | Failure Mode: " + cases["failure_mode"].astype(str) +
    " | Inspection: " + cases["inspection_finding"].astype(str) +
    " | Repair: " + cases["repair_action"].astype(str) +
    " | Outcome: " + cases["outcome"].astype(str)
)


# --------------------------------------------------
# 3. Load BGE
# --------------------------------------------------

print("Loading BGE model...")

model = SentenceTransformer("BAAI/bge-small-en-v1.5")


# --------------------------------------------------
# 4. Generate embeddings
# --------------------------------------------------

print("Creating embeddings...")

embeddings = model.encode(
    cases["search_text"].tolist(),
    normalize_embeddings=True
)

embeddings = np.array(
    embeddings,
    dtype="float32"
)

print("Embedding shape:", embeddings.shape)


# --------------------------------------------------
# 5. Create FAISS index
# --------------------------------------------------

dimension = embeddings.shape[1]

index = faiss.IndexFlatIP(dimension)

index.add(embeddings)


# --------------------------------------------------
# 6. Save index
# --------------------------------------------------

os.makedirs("models", exist_ok=True)

faiss.write_index(
    index,
    "models/engineering_memory.faiss"
)


# --------------------------------------------------
# 7. Save metadata
# --------------------------------------------------

cases.to_csv(
    "models/engineering_memory_metadata.csv",
    index=False
)


# --------------------------------------------------
# 8. Verify
# --------------------------------------------------

print("\nEngineering Memory created successfully.")

print("Cases indexed     :", index.ntotal)
print("Embedding dimension:", dimension)

print("\nSaved:")
print("models/engineering_memory.faiss")
print("models/engineering_memory_metadata.csv")