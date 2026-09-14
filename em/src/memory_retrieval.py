import faiss
import pandas as pd
from sentence_transformers import SentenceTransformer


INDEX_PATH = "models/engineering_memory.faiss"
METADATA_PATH = "models/engineering_memory_metadata.csv"

MODEL_NAME = "BAAI/bge-small-en-v1.5"


# Load once when the module starts
embedder = SentenceTransformer(MODEL_NAME)
index = faiss.read_index(INDEX_PATH)
metadata = pd.read_csv(METADATA_PATH)


def search_memory(query, top_k=3):

    # Convert technician query into embedding
    query_embedding = embedder.encode(
        [query],
        normalize_embeddings=True
    )

    # Search FAISS
    scores, indices = index.search(
        query_embedding,
        top_k
    )

    results = []

    for score, idx in zip(scores[0], indices[0]):

        if idx == -1:
            continue

        row = metadata.iloc[idx]

        results.append({
            "case_id": row["case_id"],
            "machine_id": row["machine_id"],
            "component": row["component"],
            "failure_mode": row["failure_mode"],
            "similarity": float(score)
        })

    return results


if __name__ == "__main__":

    query = "Excavator has weak digging force"

    results = search_memory(query)

    print("\n===== ENGINEERING MEMORY =====")

    for result in results:
        print(result)