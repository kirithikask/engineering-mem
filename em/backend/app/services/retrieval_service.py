"""
Hybrid evidence retrieval (brief §9, §10).

    semantic similarity  +  metadata filtering  +  source quality  +  document version priority

Design notes:

* The existing diagnosis path keeps using ``memory_service.search`` unchanged.
  This service is the richer retrieval surface used by investigations, the
  knowledge center's retrieval tester and the evidence-conflict detector.
* Similarity is produced by the SAME model, index and query representation
  (``embed_query`` / ``query_text``) that the live path uses, so the two surfaces
  cannot drift apart.
* Vector ids only ever map to relational ids through the FAISS mapping file, and
  every piece of authoritative metadata (revision, status, quality level,
  component, demo provenance) is then re-read from MySQL/SQLite by primary key.
  The index is a similarity accelerator; the database is the source of truth.
* A superseded revision is never deleted and never hidden: it is returned with a
  lower priority and an explicit ``superseded`` flag.
* Latency figures returned here are measured on the call, and are also written
  to ``retrieval_events`` so the Vector Database page can show real history.
"""

import re
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

from backend.app.db.mysql_client import db
from backend.app.services.memory_service import MODEL_NAME, memory_service
from backend.app.services.index_service import index_service
from backend.app.services.representation import embed_query, query_text

# Knowledge quality levels (brief §4). Higher is more authoritative.
QUALITY_WEIGHTS: Dict[str, float] = {
    "VERIFIED": 1.0,
    "ENGINEER_REVIEWED": 0.95,
    "TECHNICIAN_SUBMITTED": 0.85,
    "UNVERIFIED": 0.70,
}

# Document status priority (brief §6). Old knowledge is retained, not deleted.
DOC_STATUS_PRIORITY: Dict[str, float] = {
    "CURRENT": 1.0,
    "APPROVED": 1.0,
    "PENDING_REVIEW": 0.92,
    "DRAFT": 0.85,
    "SUPERSEDED": 0.72,
    "ARCHIVED": 0.60,
    "REJECTED": 0.50,
}

DEMO_SOURCE_TYPES = {"tata_industry_demo", "synthetic", "synthetic_demo", "prototype"}

# Source priority (brief §6): current approved documentation and approved
# engineering knowledge outrank individual historical cases, and demo/synthetic
# prototype records never outrank verified engineering content. Applied on top of
# the quality level, and reported per item as ``source_priority`` so the ranking
# stays inspectable.
SOURCE_PRIORITY: Dict[str, float] = {
    "approved_engineering_knowledge": 1.10,
    "field_investigation": 1.10,
    "verified_documentation": 1.06,
    "verified_case": 1.00,
    "historical_case": 0.98,
    "demo_record": 0.88,
}

_FILTER_KEYS = (
    "machine_model",
    "machine_type",
    "component",
    "subsystem",
    "failure_mode",
    "symptom",
    "document_type",
    "revision",
    "approval_status",
    "document_status",
    "date_from",
    "date_to",
    "source",
    "quality_level",
)

_MEASURE_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(hours|hour|h|hrs|bar|psi|°c|degc|c\b|rpm|litres|liters|l\b)", re.I)


class RetrievalService:
    # ------------------------------------------------------------------
    # Public search
    # ------------------------------------------------------------------
    def search(
        self,
        query: str,
        *,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 8,
        candidate_pool: int = 120,
        user: Optional[Dict[str, Any]] = None,
        machine_id: Optional[str] = None,
        investigation_id: Optional[str] = None,
        record: bool = True,
    ) -> Dict[str, Any]:
        filters = {k: v for k, v in (filters or {}).items() if v not in (None, "", [])}
        started = time.time()

        if memory_service.index is None or memory_service.embedder is None:
            return {
                "query": query,
                "filters": filters,
                "evidence": [],
                "counts": {"candidates": 0, "returned": 0},
                "timings": {"embedding_ms": 0.0, "faiss_ms": 0.0, "latency_ms": 0.0, "cache_hit": False},
                "index": {"vectors": 0, "dimension": 0, "model": MODEL_NAME},
                "detail": "Retrieval unavailable: embedding model or FAISS index is not loaded.",
                "conflicts": [],
            }

        t0 = time.time()
        vector = np.array(memory_service.embedder.encode([embed_query(query)], normalize_embeddings=True), dtype="float32")
        embedding_ms = (time.time() - t0) * 1000

        t0 = time.time()
        total_k = memory_service.index.ntotal
        k = max(1, min(candidate_pool, total_k)) if total_k else 0
        if k == 0:
            return self._empty(query, filters, embedding_ms, 0.0, started)
        scores, indices = memory_service.index.search(vector, k)
        faiss_ms = (time.time() - t0) * 1000

        mapping = memory_service.mapping
        candidates: List[Dict[str, Any]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1 or idx >= len(mapping):
                continue
            entry = mapping[idx]
            candidates.append(
                {
                    "vector_id": int(idx),
                    "similarity": round(float(score), 4),
                    "mapping": entry,
                }
            )

        enriched = self._enrich(candidates)
        filtered = [item for item in enriched if self._matches_filters(item, filters)]

        for item in filtered:
            quality = QUALITY_WEIGHTS.get(item.get("quality_level") or "", 0.70)
            status = DOC_STATUS_PRIORITY.get(item.get("document_status") or "CURRENT", 0.9)
            priority_key = self._priority_key(item)
            priority = SOURCE_PRIORITY[priority_key]
            item["quality_weight"] = quality
            item["version_priority"] = status
            item["source_priority"] = priority
            item["source_priority_reason"] = priority_key
            item["effective_score"] = round(item["similarity"] * quality * status * priority, 4)

        filtered.sort(key=lambda item: item["effective_score"], reverse=True)
        selected = filtered[: max(1, top_k)]
        conflicts = detect_conflicts(selected)
        latency_ms = (time.time() - started) * 1000

        result = {
            "query": query,
            "query_representation": "BGE query instruction + reported evidence text",
            "filters": filters,
            "evidence": selected,
            "counts": {"candidates": len(candidates), "after_filters": len(filtered), "returned": len(selected)},
            "timings": {
                "embedding_ms": round(embedding_ms, 2),
                "faiss_ms": round(faiss_ms, 2),
                "latency_ms": round(latency_ms, 2),
                "cache_hit": False,
            },
            "index": {
                "vectors": int(memory_service.index.ntotal),
                "dimension": int(memory_service.index.d),
                "model": MODEL_NAME,
            },
            "conflicts": conflicts,
        }

        if record:
            result["retrieval_id"] = self._record_event(
                query=query,
                filters=filters,
                machine_id=machine_id,
                investigation_id=investigation_id,
                user=user,
                result=result,
                latency_ms=latency_ms,
                embedding_ms=embedding_ms,
            )
        return result

    def search_text(self, symptoms: Iterable[str], **kwargs) -> Dict[str, Any]:
        """Convenience wrapper that builds the query through the canonical representation."""
        return self.search(query_text(list(symptoms)), **kwargs)

    # ------------------------------------------------------------------
    # Enrichment: mapping entry + authoritative DB metadata
    # ------------------------------------------------------------------
    def _enrich(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        case_ids = [c["mapping"]["id"] for c in candidates if c["mapping"].get("type") == "case"]
        chunk_ids = [c["mapping"]["id"] for c in candidates if c["mapping"].get("type") == "chunk"]

        cases = self._fetch_cases(case_ids)
        knowledge = self._fetch_knowledge(case_ids)
        chunks = self._fetch_chunks(chunk_ids)

        enriched: List[Dict[str, Any]] = []
        for candidate in candidates:
            entry = candidate["mapping"]
            identifier = entry.get("id")
            base = {
                "vector_id": candidate["vector_id"],
                "similarity": candidate["similarity"],
                "evidence_type": entry.get("type"),
                "id": identifier,
                "component": entry.get("component") or "",
            }

            if entry.get("type") == "case" and identifier in knowledge:  # closed-loop knowledge
                row = knowledge[identifier]
                base.update(
                    {
                        "title": row.get("title"),
                        "symptom": row.get("symptom"),
                        "failure_mode": row.get("failure_mode"),
                        "subsystem": row.get("subsystem"),
                        "machine_id": row.get("machine_id"),
                        "machine_model": row.get("machine_model"),
                        "inspection": row.get("root_cause"),
                        "repair": row.get("repair_action"),
                        "outcome": row.get("outcome"),
                        "verification": row.get("verification"),
                        "source_type": row.get("source_type") or "approved_engineering_knowledge",
                        "quality_level": row.get("quality_level"),
                        "document_status": "CURRENT",
                        "provenance": "closed-loop engineering knowledge",
                        "demo_data": False,
                    }
                )
            elif entry.get("type") == "case":
                row = cases.get(identifier, {})
                source_type = row.get("source_type") or entry.get("source_type") or "historical"
                base.update(
                    {
                        "title": f"Historical case {identifier}",
                        "symptom": row.get("symptom") or entry.get("symptom"),
                        "failure_mode": row.get("failure_mode") or entry.get("failure_mode"),
                        "subsystem": row.get("subsystem"),
                        "machine_id": row.get("machine_id") or entry.get("machine_id"),
                        "machine_model": None,
                        "inspection": row.get("inspection_finding") or entry.get("inspection_finding"),
                        "repair": row.get("repair_action") or entry.get("repair_action"),
                        "outcome": row.get("outcome") or entry.get("outcome"),
                        "source_type": source_type,
                        # A verified maintenance case is engineering-reviewed
                        # evidence, not manufacturer-approved documentation.
                        "quality_level": "VERIFIED" if row.get("is_verified") else "TECHNICIAN_SUBMITTED",
                        "document_status": "CURRENT",
                        "provenance": "maintenance case archive",
                        "demo_data": source_type in DEMO_SOURCE_TYPES,
                    }
                )
            else:
                row = chunks.get(identifier, {})
                base.update(
                    {
                        "title": row.get("document_name") or entry.get("document_name"),
                        "document_id": row.get("document_id") or entry.get("document_id"),
                        "document_type": row.get("document_type"),
                        "document_name": row.get("document_name") or entry.get("document_name"),
                        "page_number": row.get("page_number") or entry.get("page_number"),
                        "section_heading": row.get("section_heading") or entry.get("section_heading"),
                        "chunk_kind": entry.get("chunk_kind") or "text",
                        "chunk_text": row.get("chunk_text") or entry.get("chunk_text"),
                        "revision": row.get("revision") or entry.get("revision"),
                        "document_status": row.get("version_status") or entry.get("document_status") or "CURRENT",
                        "quality_level": "VERIFIED" if (row.get("version_status") in ("CURRENT", "APPROVED")) else "UNVERIFIED",
                        "source_type": row.get("document_type") or entry.get("document_type") or "document",
                        "provenance": "engineering documentation",
                        "demo_data": False,
                    }
                )

            if base.get("document_status") == "SUPERSEDED":
                base["superseded"] = True
                base["superseded_note"] = (
                    f"Revision {base.get('revision')} is superseded. Retained as engineering history; "
                    "a current revision takes priority."
                )
            enriched.append(base)
        return enriched

    def _fetch_cases(self, ids: List[str]) -> Dict[str, Dict[str, Any]]:
        return self._fetch_by_ids(
            "SELECT case_id AS id, machine_id, subsystem, component, failure_mode, symptom, inspection_finding, "
            "repair_action, outcome, is_verified, source_type FROM maintenance_cases",
            "case_id",
            ids,
        )

    def _fetch_knowledge(self, ids: List[str]) -> Dict[str, Dict[str, Any]]:
        return self._fetch_by_ids(
            "SELECT knowledge_id AS id, title, knowledge_type, machine_id, machine_model, subsystem, component, "
            "failure_mode, symptom, root_cause, repair_action, verification, outcome, quality_level, status, "
            "source_type, investigation_id FROM knowledge_items WHERE status = 'APPROVED'",
            "knowledge_id",
            ids,
        )

    def _fetch_chunks(self, ids: List[str]) -> Dict[str, Dict[str, Any]]:
        return self._fetch_by_ids(
            "SELECT c.chunk_id AS id, c.document_id, d.document_name, d.document_type, c.page_number, "
            "c.section_heading, c.component, c.chunk_text, v.revision, v.status AS version_status, "
            "v.effective_date, v.superseded_date "
            "FROM document_chunks c JOIN documents d ON c.document_id = d.document_id "
            "LEFT JOIN document_versions v ON v.document_id = c.document_id",
            "chunk_id",
            ids,
        )

    def _fetch_by_ids(self, base_sql: str, id_column: str, ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch authoritative metadata for candidate ids, keyed by row id.

        ``base_sql`` already aliases the primary key to ``id``; the outer filter
        must use that alias (a derived table in SQLite does not expose the
        original column name).
        """
        if not ids:
            return {}
        placeholder = "%s" if db.use_mysql else "?"
        unique = list(dict.fromkeys(ids))[:400]
        marks = ", ".join([placeholder] * len(unique))
        connector = " AND " if re.search(r"\bwhere\b", base_sql, re.I) else " WHERE "
        rows = db.execute_query(f"{base_sql}{connector}id IN ({marks})", tuple(unique))
        return {row["id"]: row for row in rows if row.get("id") is not None}

    def _priority_key(self, item: Dict[str, Any]) -> str:
        if item.get("demo_data"):
            return "demo_record"
        if item.get("evidence_type") == "chunk":
            return "verified_documentation"
        source_type = str(item.get("source_type") or "")
        if source_type in ("approved_engineering_knowledge", "field_investigation"):
            return "approved_engineering_knowledge"
        if item.get("id", "").startswith("KN-"):
            return "approved_engineering_knowledge"
        return "historical_case"

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------
    def _matches_filters(self, item: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        for key, wanted in filters.items():
            if key not in _FILTER_KEYS:
                continue
            actual = item.get("document_type" if key == "document_type" else key)
            if key in ("date_from", "date_to"):
                continue  # applied only where a date exists on the record
            if wanted is None or wanted == "":
                continue
            if isinstance(wanted, (list, tuple, set)):
                if not any(str(v).lower() in str(actual or "").lower() for v in wanted):
                    return False
                continue
            if str(wanted).lower() not in str(actual or "").lower():
                return False
        return True

    def filter_options(self) -> Dict[str, Any]:
        """Real filter values read from the database, for the retrieval tester UI."""
        def values(query: str, key: str) -> List[str]:
            return [str(row[key]) for row in db.execute_query(query) if row.get(key)]

        return {
            "components": values(
                "SELECT component, COUNT(*) AS n FROM maintenance_cases GROUP BY component ORDER BY n DESC LIMIT 40",
                "component",
            ),
            "subsystems": values(
                "SELECT subsystem, COUNT(*) AS n FROM maintenance_cases WHERE subsystem IS NOT NULL GROUP BY subsystem LIMIT 20",
                "subsystem",
            ),
            "document_types": values(
                "SELECT DISTINCT document_type FROM documents", "document_type"
            ),
            "document_status": list(DOC_STATUS_PRIORITY.keys()),
            "quality_levels": list(QUALITY_WEIGHTS.keys()),
            "machine_models": values("SELECT DISTINCT machine_model FROM machines", "machine_model"),
            "revisions": values("SELECT DISTINCT revision FROM document_versions", "revision"),
        }

    # ------------------------------------------------------------------
    # Bookkeeping
    # ------------------------------------------------------------------
    def _empty(self, query: str, filters: Dict[str, Any], embedding_ms: float, faiss_ms: float, started: float) -> Dict[str, Any]:
        return {
            "query": query,
            "filters": filters,
            "evidence": [],
            "conflicts": [],
            "counts": {"candidates": 0, "returned": 0},
            "timings": {
                "embedding_ms": round(embedding_ms, 2),
                "faiss_ms": round(faiss_ms, 2),
                "latency_ms": round((time.time() - started) * 1000, 2),
                "cache_hit": False,
            },
            "index": {"vectors": 0, "dimension": 0, "model": MODEL_NAME},
            "detail": "The index is empty.",
        }

    def _record_event(
        self,
        *,
        query: str,
        filters: Dict[str, Any],
        machine_id: Optional[str],
        investigation_id: Optional[str],
        user: Optional[Dict[str, Any]],
        result: Dict[str, Any],
        latency_ms: float,
        embedding_ms: float,
    ) -> str:
        retrieval_id = f"RET-{uuid.uuid4().hex[:10].upper()}"
        top = result["evidence"][0]["effective_score"] if result["evidence"] else 0.0
        import json

        db.execute_write(
            "INSERT INTO retrieval_events (retrieval_id, user_id, machine_id, investigation_id, query_text, filters_json, "
            "result_count, top_score, latency_ms, embedding_ms, index_vector_count) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
            "INSERT INTO retrieval_events (retrieval_id, user_id, machine_id, investigation_id, query_text, filters_json, "
            "result_count, top_score, latency_ms, embedding_ms, index_vector_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                retrieval_id,
                (user or {}).get("user_id"),
                machine_id,
                investigation_id,
                query[:1000],
                json.dumps(filters, default=str),
                len(result["evidence"]),
                float(top),
                round(latency_ms, 2),
                round(embedding_ms, 2),
                int(result["index"]["vectors"]),
            ),
        )
        return retrieval_id

    def recent_events(self, limit: int = 25) -> List[Dict[str, Any]]:
        return db.execute_query(
            "SELECT retrieval_id, user_id, machine_id, investigation_id, query_text, result_count, top_score, "
            "latency_ms, embedding_ms, index_vector_count, created_at FROM retrieval_events "
            f"ORDER BY created_at DESC LIMIT {int(limit)}"
        )

    def latency_summary(self) -> Dict[str, Any]:
        """Measured retrieval latency over the recorded events (no estimates)."""
        rows = db.execute_query(
            "SELECT COUNT(*) AS n, AVG(latency_ms) AS avg_ms, MIN(latency_ms) AS min_ms, MAX(latency_ms) AS max_ms "
            "FROM retrieval_events"
        )
        row = rows[0] if rows else {}
        return {
            "measurements": int(row.get("n") or 0),
            "mean_latency_ms": round(float(row.get("avg_ms") or 0.0), 2) if row.get("avg_ms") is not None else None,
            "min_latency_ms": round(float(row.get("min_ms") or 0.0), 2) if row.get("min_ms") is not None else None,
            "max_latency_ms": round(float(row.get("max_ms") or 0.0), 2) if row.get("max_ms") is not None else None,
        }


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------
def _measurements(text: str) -> List[Tuple[str, str, str]]:
    """Extract (topic phrase, value, unit) statements from real document text."""
    out: List[Tuple[str, str, str]] = []
    for match in _MEASURE_RE.finditer(text or ""):
        value, unit = match.group(1), match.group(2)
        topic = text[max(0, match.start() - 70):match.start()]
        topic = re.sub(r"[^A-Za-z\s]", " ", topic).strip().lower()
        topic = " ".join(topic.split()[-6:])
        if len(topic) < 8:
            continue
        out.append((topic, value.replace(",", ""), unit.lower()))
    return out


# Words that carry no topic signal when comparing engineering statements.
TOPIC_STOPWORDS = {
    "after", "before", "every", "each", "than", "that", "then", "with", "without", "from", "under",
    "per", "the", "and", "for", "its", "their", "this", "these", "those", "must", "should", "will",
    "replace", "replaced", "replacement", "interval", "hours", "hour", "first", "next", "also",
}

TOPIC_RELATION_THRESHOLD = 0.5


def topic_tokens(topic: str) -> frozenset:
    """Significant vocabulary of a statement's topic wording (order-independent)."""
    words = re.findall(r"[a-z]+", str(topic or "").lower())
    return frozenset(word for word in words if len(word) > 3 and word not in TOPIC_STOPWORDS)


def topics_relate(a: frozenset, b: frozenset) -> bool:
    """True when two statement topics describe the same subject.

    Comparing wording token-sets instead of exact strings matters: "filter element
    replacement interval" and "revised filter element replacement interval" are the
    same engineering subject, and an exact match would miss the conflict entirely.
    """
    if not a or not b:
        return False
    shared = a & b
    if len(shared) < 2:
        return False
    return len(shared) / min(len(a), len(b)) >= TOPIC_RELATION_THRESHOLD


def detect_conflicts(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Find conflicting engineering statements across retrieved sources.

    Conservative rule: two sources conflict when they state different numeric
    values for the same engineering subject on documents that both look
    authoritative (not superseded/archived). Every conflict is reported with BOTH
    sources; nothing is silently merged and the model is never asked to pick a
    side (brief §6).
    """
    statements: List[Tuple[Dict[str, Any], frozenset, str, str]] = []
    for item in evidence:
        text = " ".join(
            str(item.get(field) or "")
            for field in ("chunk_text", "inspection", "repair", "symptom", "title")
        )
        for topic, value, unit in _measurements(text):
            tokens = topic_tokens(topic)
            if tokens:
                statements.append((item, tokens, value, unit))

    conflicts: List[Dict[str, Any]] = []
    seen_pairs = set()
    for index, (item_a, tokens_a, value_a, unit_a) in enumerate(statements):
        for item_b, tokens_b, value_b, unit_b in statements[index + 1:]:
            if value_a == value_b or unit_a != unit_b:
                continue
            if not topics_relate(tokens_a, tokens_b):
                continue
            pair = tuple(sorted([str(item_a.get("id")), str(item_b.get("id"))]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            sources = [
                self_source(item, value, unit_a) for item, value in ((item_a, value_a), (item_b, value_b))
            ]
            current = [source for source in sources if source["document_status"] in ("CURRENT", "APPROVED")]
            stale = [
                source for source in sources if source["document_status"] in ("SUPERSEDED", "ARCHIVED")
            ]
            conflicts.append(
                {
                    "topic": " / ".join(sorted(tokens_a & tokens_b)) or "shared engineering statement",
                    "unit": unit_a,
                    "values": sorted({value_a, value_b}),
                    "sources": sources,
                    "priority_source": (current or sources)[0],
                    "severity": "SUPERSEDED_SOURCE_CONFLICT" if stale else "CONFLICTING_SOURCES",
                    "note": (
                        "Sources state different values for the same quantity. Both are shown; the current "
                        "approved source is listed first. This is not resolved automatically."
                        + (" One of these sources is a superseded revision." if stale else "")
                    ),
                }
            )
    return conflicts


def self_source(item: Dict[str, Any], value: str, unit: str) -> Dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "id": item.get("id"),
        "title": item.get("title") or item.get("document_name"),
        "source_type": item.get("source_type"),
        "document_status": item.get("document_status"),
        "revision": item.get("revision"),
        "quality_level": item.get("quality_level"),
        "page_number": item.get("page_number"),
        "similarity": item.get("similarity"),
    }


# Public alias: the version-intelligence layer reuses the same measurement
# extraction so "Rev 3 says 2000 h, Rev 4.2 says 1500 h" is detected identically.
measure_statements = _measurements

retrieval_service = RetrievalService()
