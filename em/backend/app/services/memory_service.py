import os
import json
import time
from collections import OrderedDict
import numpy as np
import faiss
from typing import List, Dict, Any, Tuple
from sentence_transformers import SentenceTransformer

from backend.app.services.representation import embed_query

INDEX_PATH = "models/engineering_memory.faiss"
MAPPING_PATH = "models/engineering_memory_mapping.json"
MODEL_NAME = "BAAI/bge-small-en-v1.5"

# Repeated diagnoses (and the demo script) re-issue the same symptom text, so the
# embedding + retrieval result is memoised. The cache is keyed on the index
# signature and cleared whenever the index is rebuilt.
CACHE_MAX_ENTRIES = 256


class EngineeringMemoryService:
    _instance = None
    
    def __init__(self):
        self.embedder = None
        self.index = None
        self.mapping = []
        self._cache: "OrderedDict[tuple, Dict[str, Any]]" = OrderedDict()
        self._cache_signature = None
        self.load()
        
    def load(self):
        try:
            # Loaded exactly once at process start and reused for every request.
            print(f"[MemoryService] Loading BGE embedder ({MODEL_NAME})...")
            self.embedder = SentenceTransformer(MODEL_NAME)
            if os.path.exists(INDEX_PATH) and os.path.exists(MAPPING_PATH):
                self.index = faiss.read_index(INDEX_PATH)
                with open(MAPPING_PATH, "r", encoding="utf-8") as f:
                    self.mapping = json.load(f)
                print(f"[MemoryService] FAISS Index loaded ({self.index.ntotal} vectors).")
            else:
                print(f"[MemoryService] FAISS Index not found at {INDEX_PATH}. Please run index builder.")
        except Exception as e:
            print(f"[MemoryService Error] {e}")

    def _signature(self) -> Tuple:
        """Identity of the currently loaded index, used to invalidate the cache."""
        try:
            mtime = os.path.getmtime(INDEX_PATH)
        except OSError:
            mtime = None
        total = self.index.ntotal if self.index is not None else 0
        return (total, mtime)

    def invalidate_cache(self) -> None:
        self._cache.clear()
        self._cache_signature = None

    def search(self, query: str, top_k_cases: int = 4, top_k_chunks: int = 2) -> Dict[str, List[Dict[str, Any]]]:
        if self.index is None or self.embedder is None:
            return {"cases": [], "chunks": []}

        signature = self._signature()
        if signature != self._cache_signature:
            self.invalidate_cache()
            self._cache_signature = signature

        cache_key = (query, top_k_cases, top_k_chunks)
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._cache.move_to_end(cache_key)
            hit = dict(cached)
            hit["timings"] = {"embedding_ms": 0.0, "faiss_ms": 0.0, "cache_hit": True}
            return hit

        # Generate normalized embedding. The BGE retrieval instruction is applied
        # here so every caller gets a correctly-formed query embedding.
        t_embed = time.time()
        query_vec = self.embedder.encode([embed_query(query)], normalize_embeddings=True)
        query_vec = np.array(query_vec, dtype="float32")
        embedding_ms = (time.time() - t_embed) * 1000

        # Search entire index (~4k vectors takes a few ms) to guarantee optimal retrieval of both cases and chunks
        t_faiss = time.time()
        total_k = self.index.ntotal
        scores, indices = self.index.search(query_vec, total_k)
        faiss_ms = (time.time() - t_faiss) * 1000
        
        retrieved_cases = []
        retrieved_chunks = []
        
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1 or idx >= len(self.mapping):
                continue
            item = self.mapping[idx]
            sim = round(float(score), 3)
            
            if item["type"] == "case" and len(retrieved_cases) < top_k_cases:
                retrieved_cases.append({
                    "case_id": item["id"],
                    "machine_id": item.get("machine_id", ""),
                    "component": item.get("component", ""),
                    "failure_mode": item.get("failure_mode", ""),
                    "symptom": item.get("symptom", ""),
                    "inspection": item.get("inspection_finding", ""),
                    "repair": item.get("repair_action", ""),
                    "outcome": item.get("outcome", ""),
                    "source_type": item.get("source_type", "historical"),
                    "similarity": sim
                })
            elif item["type"] == "chunk" and len(retrieved_chunks) < top_k_chunks:
                retrieved_chunks.append({
                    "chunk_id": item["id"],
                    "document_id": item.get("document_id", ""),
                    "document_name": item.get("document_name", ""),
                    "page_number": item.get("page_number", 1),
                    "section_heading": item.get("section_heading", ""),
                    "component": item.get("component", ""),
                    "chunk_text": item.get("chunk_text", ""),
                    "similarity": sim
                })
                
        result = {
            "cases": retrieved_cases,
            "chunks": retrieved_chunks
        }
        timings = {
            "embedding_ms": round(embedding_ms, 2),
            "faiss_ms": round(faiss_ms, 2),
            "cache_hit": False,
        }

        self._cache[cache_key] = result
        if len(self._cache) > CACHE_MAX_ENTRIES:
            self._cache.popitem(last=False)
        return {**result, "timings": timings}


memory_service = EngineeringMemoryService()
