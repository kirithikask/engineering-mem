import os
import uuid
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from typing import List, Dict, Any, Optional
from backend.app.db.mysql_client import db
from backend.app.api.auth import get_current_user
from backend.app.utils.text_chunker import chunk_text_by_paragraphs_or_sections

router = APIRouter(prefix="/api/documents", tags=["Engineering Documents"])

@router.get("")
def list_documents():
    query = "SELECT document_id, document_name, document_type, file_path, file_size_bytes, version, status, created_at FROM documents ORDER BY created_at DESC"
    docs = db.execute_query(query)
    for d in docs:
        q_count = "SELECT COUNT(*) as chunk_count FROM document_chunks WHERE document_id = %s" if db.use_mysql else "SELECT COUNT(*) as chunk_count FROM document_chunks WHERE document_id = ?"
        count_res = db.execute_query(q_count, (d["document_id"],))
        d["chunk_count"] = count_res[0]["chunk_count"] if count_res else 0
    return {"documents": docs}

@router.get("/{document_id}")
def get_document_chunks(document_id: str):
    q_doc = "SELECT * FROM documents WHERE document_id = %s" if db.use_mysql else "SELECT * FROM documents WHERE document_id = ?"
    docs = db.execute_query(q_doc, (document_id,))
    if not docs:
        raise HTTPException(status_code=404, detail="Document not found")
        
    q_chunks = "SELECT chunk_id, page_number, section_heading, component, machine_model, chunk_text FROM document_chunks WHERE document_id = %s ORDER BY page_number ASC" if db.use_mysql else "SELECT chunk_id, page_number, section_heading, component, machine_model, chunk_text FROM document_chunks WHERE document_id = ? ORDER BY page_number ASC"
    chunks = db.execute_query(q_chunks, (document_id,))
    
    return {
        "document": docs[0],
        "chunks": chunks
    }

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    document_name: Optional[str] = Form(None),
    document_type: str = Form("service_manual"),
    user: dict = Depends(get_current_user)
):
    os.makedirs("data/documents", exist_ok=True)
    doc_id = f"DOC-{uuid.uuid4().hex[:8].upper()}"
    filename = file.filename or "uploaded_manual.txt"
    name = document_name or filename
    save_path = os.path.join("data/documents", f"{doc_id}_{filename}")
    
    content_bytes = await file.read()
    with open(save_path, "wb") as f:
        f.write(content_bytes)
        
    try:
        text_content = content_bytes.decode("utf-8", errors="ignore")
    except:
        text_content = "Document content processed"
        
    db.execute_write(
        "INSERT INTO documents (document_id, document_name, document_type, file_path, file_size_bytes, version, status) VALUES (%s, %s, %s, %s, %s, %s, 'Indexed')" if db.use_mysql else
        "INSERT INTO documents (document_id, document_name, document_type, file_path, file_size_bytes, version, status) VALUES (?, ?, ?, ?, ?, ?, 'Indexed')",
        (doc_id, name, document_type, save_path, len(content_bytes), "1.0")
    )
    
    # Generate chunks
    chunks = chunk_text_by_paragraphs_or_sections(doc_id, name, document_type, text_content)
    for chk in chunks:
        db.execute_write(
            "INSERT INTO document_chunks (chunk_id, document_id, page_number, section_heading, component, machine_model, chunk_text) VALUES (%s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
            "INSERT INTO document_chunks (chunk_id, document_id, page_number, section_heading, component, machine_model, chunk_text) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (chk["chunk_id"], doc_id, chk["page_number"], chk["section_heading"], chk["component"], chk["machine_model"], chk["chunk_text"])
        )
        
    return {
        "status": "success",
        "document_id": doc_id,
        "document_name": name,
        "chunks_indexed": len(chunks)
    }
