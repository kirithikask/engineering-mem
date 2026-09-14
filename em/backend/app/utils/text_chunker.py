import os
import uuid
from typing import List, Dict, Any

def chunk_text_by_paragraphs_or_sections(
    doc_id: str,
    doc_name: str,
    doc_type: str,
    text: str,
    chunk_size_words: int = 250,
    overlap_words: int = 50
) -> List[Dict[str, Any]]:
    """
    Chunks document text preserving section headers, components, and metadata.
    """
    lines = text.splitlines()
    chunks = []
    
    current_section = "General Overview"
    current_component = "Hydraulic System"
    current_page = 1
    
    buffer_words = []
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
            
        # Detect section header
        if stripped.isupper() and len(stripped) < 60:
            current_section = stripped
            # Identify component from section title
            for comp in ["PUMP", "VALVE", "CYLINDER", "MOTOR", "COOLER", "FILTER", "ACCUMULATOR", "BOOSTER", "LINE", "OIL"]:
                if comp in stripped:
                    current_component = comp.capitalize()
                    break
        elif "page" in stripped.lower() and len(stripped) < 20:
            try:
                digits = "".join(filter(str.isdigit, stripped))
                if digits:
                    current_page = int(digits)
            except:
                pass

        words = stripped.split()
        buffer_words.extend(words)
        
        if len(buffer_words) >= chunk_size_words:
            chunk_content = " ".join(buffer_words)
            chunk_id = f"CHK-{uuid.uuid4().hex[:8].upper()}"
            chunks.append({
                "chunk_id": chunk_id,
                "document_id": doc_id,
                "document_name": doc_name,
                "document_type": doc_type,
                "page_number": current_page,
                "section_heading": current_section,
                "component": current_component,
                "machine_model": "All Models / Hydraulic Excavator",
                "chunk_text": chunk_content
            })
            # Preserve overlap
            buffer_words = buffer_words[len(buffer_words) - overlap_words:]
            
    if buffer_words:
        chunk_content = " ".join(buffer_words)
        chunk_id = f"CHK-{uuid.uuid4().hex[:8].upper()}"
        chunks.append({
            "chunk_id": chunk_id,
            "document_id": doc_id,
            "document_name": doc_name,
            "document_type": doc_type,
            "page_number": current_page,
            "section_heading": current_section,
            "component": current_component,
            "machine_model": "All Models / Hydraulic Excavator",
            "chunk_text": chunk_content
        })
        
    return chunks
