from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

print("Loading BGE model...")

model = SentenceTransformer("BAAI/bge-small-en-v1.5")

texts = [
    "Hydraulic pump internal leakage causes weak digging force.",
    "Hydraulic cooler blockage causes hydraulic oil overheating.",
    "Hydraulic filter blockage causes slow hydraulic response."
]

embeddings = model.encode(texts)

print("Embedding shape:", embeddings.shape)

dimension = embeddings.shape[1]

index = faiss.IndexFlatL2(dimension)
index.add(np.array(embeddings).astype("float32"))

query = "Excavator has weak digging force"

query_embedding = model.encode([query])

distances, results = index.search(
    np.array(query_embedding).astype("float32"),
    2
)

print("\nQuery:", query)

print("\nMost relevant cases:")

for i in results[0]:
    print("-", texts[i])

print("\nBGE + FAISS working successfully.")