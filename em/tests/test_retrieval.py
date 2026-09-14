import os
import sys

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("backend"))

from backend.app.services.memory_service import memory_service

def test_faiss_retrieval():
    query = "Boom moves slowly and hydraulic oil temperature is high"
    results = memory_service.search(query, top_k_cases=3, top_k_chunks=2)
    
    assert "cases" in results
    assert "chunks" in results
    assert len(results["cases"]) > 0
    assert len(results["chunks"]) > 0
    
    top_case = results["cases"][0]
    assert "case_id" in top_case
    assert "similarity" in top_case
    assert top_case["similarity"] > 0.4
    
    top_chunk = results["chunks"][0]
    assert "chunk_id" in top_chunk
    assert "document_name" in top_chunk
    
    print(f"[PASS] FAISS Retrieval passed: Top case {top_case['case_id']} ({top_case['component']}) with similarity {top_case['similarity']}")
    print(f"[PASS] Document chunk retrieval passed: {top_chunk['document_name']} Page {top_chunk['page_number']}")

if __name__ == "__main__":
    print("--- Running Retrieval Tests ---")
    test_faiss_retrieval()
    print("ALL RETRIEVAL TESTS PASSED.")
