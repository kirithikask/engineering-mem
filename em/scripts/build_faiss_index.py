import os
import sys
import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("backend"))

from backend.app.db.mysql_client import db
from backend.app.services.representation import case_document, chunk_document, embed_document

INDEX_PATH = "models/engineering_memory.faiss"
MAPPING_PATH = "models/engineering_memory_mapping.json"
MODEL_NAME = "BAAI/bge-small-en-v1.5"

def build_index():
    print(f"[Memory] Loading BGE model: {MODEL_NAME}...")
    embedder = SentenceTransformer(MODEL_NAME)
    
    # 1. Fetch all maintenance cases from DB
    cases = db.execute_query("SELECT case_id, machine_id, subsystem, component, failure_mode, symptom, inspection_finding, repair_action, outcome, source_type FROM maintenance_cases WHERE is_verified = 1")
    print(f"[Memory] Loaded {len(cases)} maintenance cases from DB")
    
    # 2. Fetch all document chunks from DB
    chunks = db.execute_query("SELECT c.chunk_id, c.document_id, d.document_name, c.page_number, c.section_heading, c.component, c.chunk_text FROM document_chunks c JOIN documents d ON c.document_id = d.document_id")
    print(f"[Memory] Loaded {len(chunks)} document chunks from DB")
    
    items_to_embed = []
    mapping = []
    
    # Build searchable representations for maintenance cases.
    # The text comes from the canonical representation module so the index side and
    # the query side cannot drift apart.
    for c in cases:
        source = c.get("source_type") or "historical"
        # Synthetic/demo provenance is carried as a structured field through the
        # mapping (and therefore the API and UI). It is deliberately NOT part of the
        # embedded text: a constant marker shared by 3,000 vectors compresses the
        # similarity range without adding any retrieval signal.
        text = embed_document(case_document(c))
        items_to_embed.append(text)
        mapping.append({
            "vector_id": len(mapping),
            "type": "case",
            "id": c["case_id"],
            "machine_id": c["machine_id"],
            "component": c["component"],
            "failure_mode": c["failure_mode"],
            "symptom": c["symptom"],
            "inspection_finding": c.get("inspection_finding", ""),
            "repair_action": c.get("repair_action", ""),
            "outcome": c.get("outcome", ""),
            "source_type": source,
            "text": text
        })
        
    # Build searchable representations for document chunks
    for chk in chunks:
        text = embed_document(chunk_document(chk))
        items_to_embed.append(text)
        mapping.append({
            "vector_id": len(mapping),
            "type": "chunk",
            "id": chk["chunk_id"],
            "document_id": chk["document_id"],
            "document_name": chk["document_name"],
            "page_number": chk["page_number"],
            "section_heading": chk["section_heading"],
            "component": chk["component"],
            "chunk_text": chk["chunk_text"],
            "text": text
        })
        
    print(f"[Memory] Generating embeddings for {len(items_to_embed)} items...")
    embeddings = embedder.encode(items_to_embed, normalize_embeddings=True)
    embeddings = np.array(embeddings, dtype="float32")
    
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim) # Inner product on normalized vectors = Cosine similarity
    index.add(embeddings)
    
    os.makedirs("models", exist_ok=True)
    faiss.write_index(index, INDEX_PATH)
    
    with open(MAPPING_PATH, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)
        
    print(f"[Memory] FAISS Index saved to {INDEX_PATH} (Total vectors: {index.ntotal}, Dim: {dim})")
    print(f"[Memory] Vector mapping saved to {MAPPING_PATH}")

if __name__ == "__main__":
    build_index()
