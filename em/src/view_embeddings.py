import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer

cases = pd.read_csv("data/maintenance_cases.csv")

model = SentenceTransformer("BAAI/bge-small-en-v1.5")

embeddings = model.encode(
    cases["symptom"].tolist(),
    normalize_embeddings=True
)

print("Embedding shape:", embeddings.shape)

print("\nFirst case:")
print(cases.iloc[0]["symptom"])

print("\nFirst 20 embedding values:")
print(embeddings[0][:20])