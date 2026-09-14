import os
import sys

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("backend"))

from backend.app.db.mysql_client import db
from backend.app.utils.text_chunker import chunk_text_by_paragraphs_or_sections

def ingest():
    doc_path = "data/raw/hydraulics_troubleshooting_guide.txt"
    if not os.path.exists(doc_path):
        print("Document file not found:", doc_path)
        return
        
    with open(doc_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    doc_id = "DOC-HYD-TS-001"
    doc_name = "Hydraulics Troubleshooting Guide (TS-Guide_R)"
    doc_type = "service_manual"
    file_size = len(content.encode("utf-8"))
    
    # 1. Store document metadata
    db.execute_write(
        "INSERT OR REPLACE INTO documents (document_id, document_name, document_type, file_path, file_size_bytes, version, status) VALUES (%s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
        "INSERT OR REPLACE INTO documents (document_id, document_name, document_type, file_path, file_size_bytes, version, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (doc_id, doc_name, doc_type, doc_path, file_size, "1.0", "Indexed")
    )
    
    # 2. Chunk document
    chunks = chunk_text_by_paragraphs_or_sections(doc_id, doc_name, doc_type, content, chunk_size_words=200, overlap_words=40)
    print(f"Generated {len(chunks)} chunks for {doc_name}")
    
    # 3. Store chunks in DB
    for chk in chunks:
        db.execute_write(
            "INSERT OR REPLACE INTO document_chunks (chunk_id, document_id, page_number, section_heading, component, machine_model, chunk_text) VALUES (%s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
            "INSERT OR REPLACE INTO document_chunks (chunk_id, document_id, page_number, section_heading, component, machine_model, chunk_text) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (chk["chunk_id"], chk["document_id"], chk["page_number"], chk["section_heading"], chk["component"], chk["machine_model"], chk["chunk_text"])
        )
        
    print("Document ingestion completed successfully.")

if __name__ == "__main__":
    ingest()
