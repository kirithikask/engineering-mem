"""
FAISS index administration for the extension modules.

Responsibilities (brief §9, §22):

* keep ONE index with ONE mapping file, exactly as the existing builder
  produces them, so the live retrieval path (``memory_service``) keeps working
  unchanged;
* guarantee the identity contract: ``embedding_records`` maps a stable
  relational key (case id / chunk id / knowledge id) to the FAISS vector id.
  The vector id is only ever ``len(mapping)`` at append time — never a dataframe
  or result row number;
* record every index mutation in ``vector_index_versions`` with the real
  observed vector count, dimension and model name (no estimates);
* write both files atomically (temp file + ``os.replace``) and keep one previous
  backup, so an interrupted write cannot leave a half-written index;
* run a full rebuild in a background thread, built into a scratch pair of files
  that is swapped in only after it succeeds.

Nothing here runs on the diagnosis path. It is triggered by document approval,
knowledge approval, or an explicit admin reindex request.
"""

import hashlib
import json
import os
import shutil
import threading
import time
import uuid
from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional, Tuple

import faiss
import numpy as np

from backend.app.db.mysql_client import db
from backend.app.services.memory_service import MODEL_NAME, memory_service
from backend.app.services.representation import case_document, chunk_document, embed_document

INDEX_PATH = "models/engineering_memory.faiss"
MAPPING_PATH = "models/engineering_memory_mapping.json"
BACKUP_INDEX_PATH = "models/engineering_memory.faiss.bak"
BACKUP_MAPPING_PATH = "models/engineering_memory_mapping.json.bak"

REBUILD_JOBS_MAX = 8
_rebuild_jobs: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_rebuild_lock = threading.Lock()
_write_lock = threading.RLock()


def _json(value: Any) -> str:
    try:
        return json.dumps(value, default=str)
    except Exception:
        return "{}"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:40]


class IndexService:
    # ------------------------------------------------------------------
    # Read-side state
    # ------------------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        index = memory_service.index
        mapping = memory_service.mapping or []
        kinds: Dict[str, int] = {}
        for item in mapping:
            key = item.get("type", "unknown")
            kinds[key] = kinds.get(key, 0) + 1

        versions = db.execute_query(
            "SELECT index_version_id, index_path, vector_count, dimension, model_name, operation, added_count, "
            "is_current, note, created_by, created_at FROM vector_index_versions ORDER BY created_at DESC LIMIT 12"
        )
        recorded = db.execute_query(
            "SELECT COUNT(*) AS n FROM embedding_records"
        )
        by_owner = db.execute_query(
            "SELECT owner_type, COUNT(*) AS n FROM embedding_records GROUP BY owner_type"
        )
        try:
            index_mtime = os.path.getmtime(INDEX_PATH)
            mapping_mtime = os.path.getmtime(MAPPING_PATH)
        except OSError:
            index_mtime = mapping_mtime = None

        return {
            "index_path": INDEX_PATH,
            "mapping_path": MAPPING_PATH,
            "loaded": index is not None,
            "vectors": int(index.ntotal) if index is not None else 0,
            "dimension": int(index.d) if index is not None else 0,
            "index_type": type(index).__name__ if index is not None else None,
            "metric": "inner product on L2-normalised vectors (cosine)",
            "embedding_model": MODEL_NAME,
            "mapping_entries": len(mapping),
            "mapping_by_type": kinds,
            "embedding_records": int(recorded[0]["n"]) if recorded else 0,
            "embedding_records_by_owner": [
                {"owner_type": row["owner_type"], "count": int(row["n"])} for row in by_owner
            ],
            "index_mtime_epoch": index_mtime,
            "mapping_mtime_epoch": mapping_mtime,
            "index_versions": versions,
        }

    # ------------------------------------------------------------------
    # Append path
    # ------------------------------------------------------------------
    def index_document_chunks(self, document_id: str, chunks: List[Dict[str, Any]], user: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        items = []
        for chunk in chunks:
            text = chunk_document(chunk)
            items.append(
                {
                    "owner_type": "chunk",
                    "owner_id": chunk["chunk_id"],
                    "text": text,
                    "mapping": {
                        "type": "chunk",
                        "id": chunk["chunk_id"],
                        "document_id": chunk["document_id"],
                        "document_name": chunk.get("document_name", ""),
                        "page_number": chunk.get("page_number", 1),
                        "section_heading": chunk.get("section_heading", ""),
                        "component": chunk.get("component", ""),
                        "chunk_text": chunk.get("chunk_text", ""),
                        "text": text,
                        "chunk_kind": chunk.get("chunk_kind", "text"),
                        "document_status": chunk.get("document_status", "CURRENT"),
                        "revision": chunk.get("revision"),
                        "quality_level": chunk.get("quality_level", "VERIFIED"),
                        "subsystem": chunk.get("subsystem"),
                    },
                    "meta": chunk.get("meta", {}),
                }
            )
        return self.append(items, user=user, operation="APPEND_DOCUMENT_CHUNKS", note=f"document {document_id}")

    def index_knowledge_item(self, knowledge: Dict[str, Any], user: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Embed one approved knowledge item as a retrievable case-style vector.

        The mapping entry deliberately keeps the historical-case field names that
        the existing retrieval path expects (component / failure_mode / symptom /
        inspection_finding / repair_action / outcome), so newly approved closed
        loop knowledge is immediately visible to the existing memory search and
        to the diagnosis engine, with no change to either.
        """
        case_like = {
            "symptom": knowledge.get("symptom") or knowledge.get("title"),
            "component": knowledge.get("component"),
            "failure_mode": knowledge.get("failure_mode"),
            "subsystem": knowledge.get("subsystem"),
        }
        text = case_document(case_like)
        item = {
            "owner_type": "knowledge",
            "owner_id": knowledge["knowledge_id"],
            "text": text,
            "mapping": {
                "type": "case",
                "id": knowledge["knowledge_id"],
                "machine_id": knowledge.get("machine_id", ""),
                "component": knowledge.get("component", ""),
                "failure_mode": knowledge.get("failure_mode", ""),
                "symptom": knowledge.get("symptom", ""),
                "inspection_finding": knowledge.get("root_cause", ""),
                "repair_action": knowledge.get("repair_action", ""),
                "outcome": knowledge.get("outcome", ""),
                "source_type": knowledge.get("source_type", "approved_engineering_knowledge"),
                "text": text,
                "knowledge_type": knowledge.get("knowledge_type"),
                "quality_level": knowledge.get("quality_level", "VERIFIED"),
                "document_status": "CURRENT",
                "investigation_id": knowledge.get("investigation_id"),
                "approved_by_name": knowledge.get("approved_by_name"),
                "verification": knowledge.get("verification"),
            },
            "meta": {
                "quality_level": knowledge.get("quality_level", "VERIFIED"),
                "component": knowledge.get("component"),
                "subsystem": knowledge.get("subsystem"),
                "machine_model": knowledge.get("machine_model"),
            },
        }
        return self.append([item], user=user, operation="APPEND_KNOWLEDGE", note=knowledge["knowledge_id"])

    def append(self, items: List[Dict[str, Any]], user: Optional[Dict[str, Any]] = None, operation: str = "APPEND", note: str = "") -> Dict[str, Any]:
        """Embed and append new items. Already-present content is skipped."""
        if not items:
            return {"status": "noop", "added": 0, "skipped": 0, "vectors": self._vector_count()}
        if memory_service.embedder is None or memory_service.index is None:
            return {
                "status": "unavailable",
                "added": 0,
                "skipped": 0,
                "detail": "Embedding model or FAISS index is not loaded; nothing was indexed.",
                "vectors": 0,
            }

        with _write_lock:
            mapping = list(memory_service.mapping or [])
            existing = {
                (row["owner_type"], row["owner_id"], row["content_hash"])
                for row in db.execute_query("SELECT owner_type, owner_id, content_hash FROM embedding_records")
            }

            pending: List[Dict[str, Any]] = []
            skipped = 0
            for item in items:
                key = (item["owner_type"], item["owner_id"], content_hash(item["text"]))
                if key in existing:
                    skipped += 1
                    continue
                pending.append(item)

            if not pending:
                return {"status": "noop", "added": 0, "skipped": skipped, "vectors": self._vector_count()}

            t0 = time.time()
            vectors = memory_service.embedder.encode(
                [embed_document(item["text"]) for item in pending], normalize_embeddings=True
            )
            vectors = np.array(vectors, dtype="float32")
            embed_ms = (time.time() - t0) * 1000

            index = memory_service.index
            if vectors.shape[1] != index.d:
                return {
                    "status": "error",
                    "added": 0,
                    "skipped": skipped,
                    "detail": f"Embedding dimension {vectors.shape[1]} does not match index dimension {index.d}.",
                    "vectors": self._vector_count(),
                }

            first_vector_id = len(mapping)
            index.add(vectors)

            version_id = f"IDXV-{uuid.uuid4().hex[:8].upper()}"
            for offset, item in enumerate(pending):
                entry = dict(item["mapping"])
                entry["vector_id"] = first_vector_id + offset
                mapping.append(entry)

            self._persist(index, mapping)
            memory_service.mapping = mapping

            for offset, item in enumerate(pending):
                meta = item.get("meta", {}) or {}
                fields = item["mapping"]
                db.execute_write(
                    "INSERT INTO embedding_records (embedding_id, owner_type, owner_id, vector_id, model_name, dimension, "
                    "index_version_id, content_hash, quality_level, document_status, machine_model, component, subsystem) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
                    "INSERT INTO embedding_records (embedding_id, owner_type, owner_id, vector_id, model_name, dimension, "
                    "index_version_id, content_hash, quality_level, document_status, machine_model, component, subsystem) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"EMB-{uuid.uuid4().hex[:12].upper()}",
                        item["owner_type"],
                        item["owner_id"],
                        first_vector_id + offset,
                        MODEL_NAME,
                        int(index.d),
                        version_id,
                        content_hash(item["text"]),
                        fields.get("quality_level") or meta.get("quality_level"),
                        fields.get("document_status") or meta.get("document_status"),
                        meta.get("machine_model"),
                        fields.get("component") or meta.get("component"),
                        meta.get("subsystem"),
                    ),
                )

            self._record_version(
                version_id=version_id,
                operation=operation,
                added=len(pending),
                note=note,
                user=user,
                vectors=int(index.ntotal),
                dimension=int(index.d),
            )
            memory_service.invalidate_cache()

            return {
                "status": "ok",
                "added": len(pending),
                "skipped": skipped,
                "first_vector_id": first_vector_id,
                "vectors": int(index.ntotal),
                "dimension": int(index.d),
                "index_version_id": version_id,
                "embedding_ms": round(embed_ms, 2),
            }

    # ------------------------------------------------------------------
    # Full rebuild
    # ------------------------------------------------------------------
    def collect_rebuild_items(self) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """Read everything that is allowed into the index, from the database."""
        items: List[Dict[str, Any]] = []
        counts: Dict[str, int] = {}

        cases = db.execute_query(
            "SELECT case_id, machine_id, subsystem, component, failure_mode, symptom, inspection_finding, "
            "repair_action, outcome, source_type FROM maintenance_cases WHERE is_verified = 1"
        )
        counts["cases"] = len(cases)
        for case in cases:
            text = case_document(case)
            items.append(
                {
                    "owner_type": "case",
                    "owner_id": case["case_id"],
                    "text": text,
                    "mapping": {
                        "type": "case",
                        "id": case["case_id"],
                        "machine_id": case.get("machine_id", ""),
                        "component": case.get("component", ""),
                        "failure_mode": case.get("failure_mode", ""),
                        "symptom": case.get("symptom", ""),
                        "inspection_finding": case.get("inspection_finding", ""),
                        "repair_action": case.get("repair_action", ""),
                        "outcome": case.get("outcome", ""),
                        "source_type": case.get("source_type") or "historical",
                        "text": text,
                    },
                    "meta": {},
                }
            )

        # Only document chunks whose version has been approved belong in the index.
        chunks = self.approved_chunks()
        counts["chunks"] = len(chunks)
        for chunk in chunks:
            text = chunk_document(chunk)
            items.append(
                {
                    "owner_type": "chunk",
                    "owner_id": chunk["chunk_id"],
                    "text": text,
                    "mapping": {
                        "type": "chunk",
                        "id": chunk["chunk_id"],
                        "document_id": chunk["document_id"],
                        "document_name": chunk.get("document_name", ""),
                        "page_number": chunk.get("page_number", 1),
                        "section_heading": chunk.get("section_heading", ""),
                        "component": chunk.get("component", ""),
                        "chunk_text": chunk.get("chunk_text", ""),
                        "text": text,
                        "document_status": chunk.get("document_status", "CURRENT"),
                        "revision": chunk.get("revision"),
                        "quality_level": chunk.get("quality_level", "VERIFIED"),
                    },
                    "meta": {},
                }
            )

        knowledge = db.execute_query(
            "SELECT knowledge_id, title, knowledge_type, machine_id, machine_model, subsystem, component, "
            "failure_mode, symptom, root_cause, repair_action, verification, outcome, quality_level, source_type, "
            "investigation_id, approved_by_name FROM knowledge_items "
            "WHERE status = 'APPROVED' AND quality_level IN ('VERIFIED','ENGINEER_REVIEWED')"
        )
        counts["knowledge_items"] = len(knowledge)
        for item in knowledge:
            case_like = {
                "symptom": item.get("symptom") or item.get("title"),
                "component": item.get("component"),
                "failure_mode": item.get("failure_mode"),
                "subsystem": item.get("subsystem"),
            }
            text = case_document(case_like)
            items.append(
                {
                    "owner_type": "knowledge",
                    "owner_id": item["knowledge_id"],
                    "text": text,
                    "mapping": {
                        "type": "case",
                        "id": item["knowledge_id"],
                        "machine_id": item.get("machine_id", ""),
                        "component": item.get("component", ""),
                        "failure_mode": item.get("failure_mode", ""),
                        "symptom": item.get("symptom", ""),
                        "inspection_finding": item.get("root_cause", ""),
                        "repair_action": item.get("repair_action", ""),
                        "outcome": item.get("outcome", ""),
                        "source_type": item.get("source_type", "approved_engineering_knowledge"),
                        "text": text,
                        "knowledge_type": item.get("knowledge_type"),
                        "quality_level": item.get("quality_level"),
                        "investigation_id": item.get("investigation_id"),
                    },
                    "meta": {
                        "quality_level": item.get("quality_level"),
                        "component": item.get("component"),
                        "subsystem": item.get("subsystem"),
                        "machine_model": item.get("machine_model"),
                    },
                }
            )
        return items, counts

    def rebuild(self, user: Optional[Dict[str, Any]] = None, note: str = "full rebuild") -> Dict[str, Any]:
        """Rebuild the whole index into scratch files, then swap atomically."""
        if memory_service.embedder is None:
            return {"status": "unavailable", "detail": "Embedding model is not loaded."}

        items, counts = self.collect_rebuild_items()
        if not items:
            return {"status": "noop", "detail": "Nothing to index.", "counts": counts}

        tmp_index = INDEX_PATH + ".rebuild"
        tmp_mapping = MAPPING_PATH + ".rebuild"
        started = time.time()

        t0 = time.time()
        vectors = memory_service.embedder.encode(
            [embed_document(item["text"]) for item in items], normalize_embeddings=True, batch_size=32
        )
        embed_ms = (time.time() - t0) * 1000
        vectors = np.array(vectors, dtype="float32")

        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)

        mapping = []
        for position, item in enumerate(items):
            entry = dict(item["mapping"])
            entry["vector_id"] = position
            mapping.append(entry)

        os.makedirs("models", exist_ok=True)
        faiss.write_index(index, tmp_index)
        with open(tmp_mapping, "w", encoding="utf-8") as handle:
            json.dump(mapping, handle, indent=2)

        with _write_lock:
            self._backup_current()
            os.replace(tmp_index, INDEX_PATH)
            os.replace(tmp_mapping, MAPPING_PATH)
            self._reload_memory_service()

            version_id = f"IDXV-{uuid.uuid4().hex[:8].upper()}"
            db.execute_write("DELETE FROM embedding_records")
            for position, item in enumerate(items):
                meta = item.get("meta", {}) or {}
                db.execute_write(
                    "INSERT INTO embedding_records (embedding_id, owner_type, owner_id, vector_id, model_name, dimension, "
                    "index_version_id, content_hash, quality_level, document_status, machine_model, component, subsystem) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
                    "INSERT INTO embedding_records (embedding_id, owner_type, owner_id, vector_id, model_name, dimension, "
                    "index_version_id, content_hash, quality_level, document_status, machine_model, component, subsystem) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"EMB-{uuid.uuid4().hex[:12].upper()}",
                        item["owner_type"],
                        item["owner_id"],
                        position,
                        MODEL_NAME,
                        int(index.d),
                        version_id,
                        content_hash(item["text"]),
                        meta.get("quality_level"),
                        item["mapping"].get("document_status"),
                        meta.get("machine_model"),
                        item["mapping"].get("component"),
                        meta.get("subsystem"),
                    ),
                )

            self._record_version(
                version_id=version_id,
                operation="REBUILD",
                added=len(items),
                note=f"{note} · {counts}",
                user=user,
                vectors=int(index.ntotal),
                dimension=int(index.d),
            )

        return {
            "status": "ok",
            "index_version_id": version_id,
            "vectors": int(index.ntotal),
            "dimension": int(index.d),
            "counts": counts,
            "embedding_ms": round(embed_ms, 2),
            "total_s": round(time.time() - started, 1),
        }

    def rebuild_start(self, user: Optional[Dict[str, Any]] = None, note: str = "admin reindex") -> Dict[str, Any]:
        """Run the rebuild in a background thread (reindexing must not block a request)."""
        job_id = f"REIDX-{uuid.uuid4().hex[:8].upper()}"
        with _rebuild_lock:
            _rebuild_jobs[job_id] = {
                "job_id": job_id,
                "status": "running",
                "started_at": time.time(),
                "note": note,
                "requested_by": (user or {}).get("username"),
            }
            while len(_rebuild_jobs) > REBUILD_JOBS_MAX:
                _rebuild_jobs.popitem(last=False)

        def _run() -> None:
            try:
                result = self.rebuild(user=user, note=note)
                with _rebuild_lock:
                    _rebuild_jobs[job_id].update(result=result, status=result.get("status", "ok"), finished_at=time.time())
            except Exception as exc:  # pragma: no cover - defensive
                with _rebuild_lock:
                    _rebuild_jobs[job_id].update(status="failed", error=str(exc), finished_at=time.time())

        threading.Thread(target=_run, daemon=True).start()
        return {"job_id": job_id, "status": "running"}

    def rebuild_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        with _rebuild_lock:
            job = _rebuild_jobs.get(job_id)
            if job is None:
                return None
            payload = dict(job)
        if payload.get("started_at"):
            payload["elapsed_s"] = round(time.time() - payload["started_at"], 1)
        return payload

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def approved_chunks(self) -> List[Dict[str, Any]]:
        """Chunks of every document whose version status allows indexing.

        Documents ingested before the versioning layer existed carry no
        ``document_versions`` row. They were indexed by the original pipeline and
        are already approved knowledge, so they are included on the strength of
        their document status instead of being dropped from a rebuild.
        """
        rows = db.execute_query(
            "SELECT c.chunk_id, c.document_id, d.document_name, c.page_number, c.section_heading, c.component, "
            "c.chunk_text, v.revision, v.status AS version_status "
            "FROM document_chunks c "
            "JOIN documents d ON c.document_id = d.document_id "
            "LEFT JOIN document_versions v ON v.document_id = c.document_id "
            "WHERE v.status IN ('CURRENT', 'APPROVED') "
            "   OR (v.version_id IS NULL AND d.status IN ('Indexed', 'INDEXED', 'Approved', 'APPROVED'))"
        )
        out = []
        seen = set()
        for row in rows:
            if row["chunk_id"] in seen:
                continue
            seen.add(row["chunk_id"])
            out.append(
                {
                    "chunk_id": row["chunk_id"],
                    "document_id": row["document_id"],
                    "document_name": row.get("document_name", ""),
                    "page_number": row.get("page_number", 1),
                    "section_heading": row.get("section_heading", ""),
                    "component": row.get("component", ""),
                    "chunk_text": row.get("chunk_text", ""),
                    "revision": row.get("revision"),
                    "document_status": row.get("version_status") or "CURRENT",
                    "quality_level": "VERIFIED",
                }
            )
        return out

    def _vector_count(self) -> int:
        return int(memory_service.index.ntotal) if memory_service.index is not None else 0

    def _persist(self, index, mapping: List[Dict[str, Any]]) -> None:
        os.makedirs("models", exist_ok=True)
        tmp_index = INDEX_PATH + ".tmp"
        tmp_mapping = MAPPING_PATH + ".tmp"
        faiss.write_index(index, tmp_index)
        with open(tmp_mapping, "w", encoding="utf-8") as handle:
            json.dump(mapping, handle, indent=2)
        os.replace(tmp_index, INDEX_PATH)
        os.replace(tmp_mapping, MAPPING_PATH)

    def _backup_current(self) -> None:
        for source, target in ((INDEX_PATH, BACKUP_INDEX_PATH), (MAPPING_PATH, BACKUP_MAPPING_PATH)):
            if os.path.exists(source):
                try:
                    shutil.copy2(source, target)
                except Exception:
                    pass

    def _reload_memory_service(self) -> None:
        memory_service.load()
        memory_service.invalidate_cache()

    def _record_version(
        self,
        *,
        version_id: str,
        operation: str,
        added: int,
        note: str,
        user: Optional[Dict[str, Any]],
        vectors: int,
        dimension: int,
    ) -> None:
        db.execute_write(
            "UPDATE vector_index_versions SET is_current = 0" if db.use_mysql
            else "UPDATE vector_index_versions SET is_current = 0",
        )
        db.execute_write(
            "INSERT INTO vector_index_versions (index_version_id, index_path, mapping_path, vector_count, dimension, "
            "model_name, operation, added_count, is_current, note, created_by) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s)" if db.use_mysql else
            "INSERT INTO vector_index_versions (index_version_id, index_path, mapping_path, vector_count, dimension, "
            "model_name, operation, added_count, is_current, note, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (
                version_id,
                INDEX_PATH,
                MAPPING_PATH,
                vectors,
                dimension,
                MODEL_NAME,
                operation,
                added,
                note,
                (user or {}).get("username"),
            ),
        )


index_service = IndexService()
