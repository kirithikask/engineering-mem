"""
Additive schema for the Engineering Memory extension modules.

Design rules (see the platform brief, sections 8 and 23):

* ADD ONLY. No existing table, column or query is modified or dropped. Every
  statement below is ``CREATE TABLE IF NOT EXISTS``, so running this against a
  live MySQL instance or the local SQLite fallback is idempotent and cannot
  damage data that was produced by the original ingestion/analysis scripts.
* One DDL dialect: only column types and clauses that both MySQL 8 and SQLite
  accept. Indexes are created defensively (MySQL has no ``CREATE INDEX IF NOT
  EXISTS``), and a missing index never fails startup.
* Every new knowledge-bearing row keeps the identity contract used by the
  retrieval layer: the relational primary key is stable, and the FAISS vector id
  is recorded beside it in ``embedding_records`` (never derived from a row
  number).
"""

from typing import List, Tuple

from backend.app.db.mysql_client import db

SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Document intelligence: versions, extraction jobs, per-page extraction records
# ---------------------------------------------------------------------------

_EXTENSION_TABLES: List[Tuple[str, str]] = [
(
    "document_versions",
    """
    CREATE TABLE IF NOT EXISTS document_versions (
        version_id VARCHAR(64) PRIMARY KEY,
        document_id VARCHAR(64) NOT NULL,
        revision VARCHAR(50) NOT NULL,
        status VARCHAR(30) NOT NULL DEFAULT 'PENDING_REVIEW',
        effective_date VARCHAR(30),
        superseded_date VARCHAR(30),
        supersedes_version_id VARCHAR(64),
        source VARCHAR(255),
        file_path VARCHAR(500),
        extraction_method VARCHAR(60),
        extraction_confidence FLOAT DEFAULT 0,
        checksum VARCHAR(80),
        approved_by VARCHAR(64),
        approved_at VARCHAR(40),
        note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
),
(
    "ingestion_jobs",
    """
    CREATE TABLE IF NOT EXISTS ingestion_jobs (
        job_id VARCHAR(64) PRIMARY KEY,
        document_id VARCHAR(64),
        version_id VARCHAR(64),
        filename VARCHAR(500),
        status VARCHAR(40) NOT NULL DEFAULT 'QUEUED',
        detected_type VARCHAR(60),
        pipeline_stage VARCHAR(60),
        page_count INT DEFAULT 0,
        text_page_count INT DEFAULT 0,
        extracted_chars INT DEFAULT 0,
        table_count INT DEFAULT 0,
        image_count INT DEFAULT 0,
        ocr_confidence FLOAT DEFAULT 0,
        extraction_confidence FLOAT DEFAULT 0,
        confidence_breakdown TEXT,
        extraction_method VARCHAR(60),
        chunk_count INT DEFAULT 0,
        vector_count INT DEFAULT 0,
        message TEXT,
        created_by VARCHAR(64),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at VARCHAR(40)
    )
    """,
),
(
    "document_extractions",
    """
    CREATE TABLE IF NOT EXISTS document_extractions (
        extraction_id VARCHAR(64) PRIMARY KEY,
        job_id VARCHAR(64),
        document_id VARCHAR(64) NOT NULL,
        version_id VARCHAR(64),
        page_number INT DEFAULT 1,
        block_index INT DEFAULT 0,
        block_kind VARCHAR(40) NOT NULL DEFAULT 'text',
        extraction_method VARCHAR(60),
        extraction_confidence FLOAT DEFAULT 0,
        raw_text TEXT,
        structure_json TEXT,
        review_status VARCHAR(30) DEFAULT 'PENDING_REVIEW',
        reviewer_id VARCHAR(64),
        reviewed_at VARCHAR(40),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
),
(
    "service_reports",
    """
    CREATE TABLE IF NOT EXISTS service_reports (
        report_id VARCHAR(64) PRIMARY KEY,
        machine_id VARCHAR(64),
        investigation_id VARCHAR(64),
        document_id VARCHAR(64),
        report_date VARCHAR(40),
        subsystem VARCHAR(100),
        component VARCHAR(100),
        symptom TEXT,
        finding TEXT,
        action_taken TEXT,
        outcome VARCHAR(255),
        technician_id VARCHAR(64),
        quality_level VARCHAR(30) DEFAULT 'TECHNICIAN_SUBMITTED',
        source_type VARCHAR(50) DEFAULT 'service_report',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
),
(
    "technician_observations",
    """
    CREATE TABLE IF NOT EXISTS technician_observations (
        observation_id VARCHAR(64) PRIMARY KEY,
        machine_id VARCHAR(64),
        investigation_id VARCHAR(64),
        component VARCHAR(100),
        observation_text TEXT NOT NULL,
        context_json TEXT,
        quality_level VARCHAR(30) DEFAULT 'TECHNICIAN_SUBMITTED',
        created_by VARCHAR(64),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
),

# ---------------------------------------------------------------------------
# Investigations, findings, failed-repair memory, verification, photo evidence
# ---------------------------------------------------------------------------

(
    "investigations",
    """
    CREATE TABLE IF NOT EXISTS investigations (
        investigation_id VARCHAR(64) PRIMARY KEY,
        machine_id VARCHAR(64) NOT NULL,
        title VARCHAR(255) NOT NULL,
        problem_statement TEXT,
        symptoms_json TEXT,
        subsystem VARCHAR(100),
        severity VARCHAR(30) DEFAULT 'MEDIUM',
        status VARCHAR(40) NOT NULL DEFAULT 'OPEN',
        opened_by VARCHAR(64),
        opened_by_name VARCHAR(150),
        opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        closed_at VARCHAR(40),
        root_cause VARCHAR(255),
        root_cause_detail TEXT,
        repair_summary TEXT,
        failed_attempt_count INT DEFAULT 0,
        verification_json TEXT,
        evidence_snapshot_json TEXT,
        knowledge_id VARCHAR(64),
        confidence VARCHAR(30),
        source_type VARCHAR(50) DEFAULT 'field_investigation',
        updated_at VARCHAR(40)
    )
    """,
),
(
    "investigation_findings",
    """
    CREATE TABLE IF NOT EXISTS investigation_findings (
        finding_id VARCHAR(64) PRIMARY KEY,
        investigation_id VARCHAR(64) NOT NULL,
        seq INT DEFAULT 0,
        kind VARCHAR(40) NOT NULL DEFAULT 'inspection',
        title VARCHAR(255) NOT NULL,
        detail TEXT,
        value VARCHAR(80),
        unit VARCHAR(40),
        component VARCHAR(100),
        subsystem VARCHAR(100),
        source VARCHAR(255),
        quality_level VARCHAR(30) DEFAULT 'TECHNICIAN_SUBMITTED',
        ruling VARCHAR(30) DEFAULT 'PENDING',
        evidence_json TEXT,
        created_by VARCHAR(64),
        created_by_name VARCHAR(150),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
),
(
    "investigation_events",
    """
    CREATE TABLE IF NOT EXISTS investigation_events (
        event_id VARCHAR(64) PRIMARY KEY,
        investigation_id VARCHAR(64) NOT NULL,
        event_type VARCHAR(50) NOT NULL,
        summary VARCHAR(500) NOT NULL,
        actor_id VARCHAR(64),
        actor_name VARCHAR(150),
        payload_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
),
(
    "repair_attempts",
    """
    CREATE TABLE IF NOT EXISTS repair_attempts (
        attempt_id VARCHAR(64) PRIMARY KEY,
        investigation_id VARCHAR(64),
        machine_id VARCHAR(64),
        symptom_text TEXT,
        action_taken TEXT NOT NULL,
        component VARCHAR(100),
        failure_mode VARCHAR(150),
        result VARCHAR(40) NOT NULL DEFAULT 'UNKNOWN',
        was_successful INT DEFAULT 0,
        technician_note TEXT,
        quality_level VARCHAR(30) DEFAULT 'TECHNICIAN_SUBMITTED',
        created_by VARCHAR(64),
        created_by_name VARCHAR(150),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
),
(
    "repair_verifications",
    """
    CREATE TABLE IF NOT EXISTS repair_verifications (
        verification_id VARCHAR(64) PRIMARY KEY,
        investigation_id VARCHAR(64) NOT NULL,
        checks_json TEXT,
        passed INT DEFAULT 0,
        notes TEXT,
        verified_by VARCHAR(64),
        verified_by_name VARCHAR(150),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
),
(
    "photo_evidence",
    """
    CREATE TABLE IF NOT EXISTS photo_evidence (
        photo_id VARCHAR(64) PRIMARY KEY,
        investigation_id VARCHAR(64),
        machine_id VARCHAR(64),
        file_path VARCHAR(500),
        original_filename VARCHAR(300),
        caption TEXT,
        component_suggested VARCHAR(100),
        component_confirmed VARCHAR(100),
        visual_match VARCHAR(30) DEFAULT 'UNDETERMINED',
        image_analysis_json TEXT,
        related_knowledge_json TEXT,
        created_by VARCHAR(64),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
),

# ---------------------------------------------------------------------------
# Knowledge items, review workflow, sources, safety procedures
# ---------------------------------------------------------------------------

(
    "knowledge_items",
    """
    CREATE TABLE IF NOT EXISTS knowledge_items (
        knowledge_id VARCHAR(64) PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        knowledge_type VARCHAR(40) NOT NULL DEFAULT 'case',
        content TEXT,
        machine_id VARCHAR(64),
        machine_model VARCHAR(100),
        subsystem VARCHAR(100),
        component VARCHAR(100),
        failure_mode VARCHAR(150),
        symptom TEXT,
        root_cause TEXT,
        repair_action TEXT,
        verification TEXT,
        outcome VARCHAR(255),
        operating_condition VARCHAR(255),
        parts_json TEXT,
        failed_attempts_json TEXT,
        quality_level VARCHAR(30) NOT NULL DEFAULT 'UNVERIFIED',
        status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
        source_type VARCHAR(50) DEFAULT 'field_investigation',
        source_ref VARCHAR(120),
        investigation_id VARCHAR(64),
        document_id VARCHAR(64),
        created_by VARCHAR(64),
        created_by_name VARCHAR(150),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        approved_by VARCHAR(64),
        approved_by_name VARCHAR(150),
        approved_at VARCHAR(40),
        vector_id INT,
        confidence VARCHAR(30),
        superseded_by VARCHAR(64),
        superseded_at VARCHAR(40)
    )
    """,
),
(
    "knowledge_reviews",
    """
    CREATE TABLE IF NOT EXISTS knowledge_reviews (
        review_id VARCHAR(64) PRIMARY KEY,
        knowledge_id VARCHAR(64) NOT NULL,
        reviewer_id VARCHAR(64),
        reviewer_name VARCHAR(150),
        reviewer_role VARCHAR(30),
        action VARCHAR(30) NOT NULL,
        prior_status VARCHAR(30),
        new_status VARCHAR(30),
        prior_quality_level VARCHAR(30),
        new_quality_level VARCHAR(30),
        comment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
),
(
    "knowledge_sources",
    """
    CREATE TABLE IF NOT EXISTS knowledge_sources (
        source_id VARCHAR(64) PRIMARY KEY,
        owner_type VARCHAR(30) NOT NULL,
        owner_id VARCHAR(64) NOT NULL,
        source_kind VARCHAR(40) NOT NULL,
        source_ref VARCHAR(120),
        title VARCHAR(255),
        document_id VARCHAR(64),
        version_id VARCHAR(64),
        chunk_id VARCHAR(64),
        case_id VARCHAR(64),
        page_number INT,
        revision VARCHAR(50),
        document_status VARCHAR(30),
        quality_level VARCHAR(30),
        effective_date VARCHAR(30),
        note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
),
(
    "safety_procedures",
    """
    CREATE TABLE IF NOT EXISTS safety_procedures (
        procedure_id VARCHAR(64) PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        subsystem VARCHAR(100),
        task VARCHAR(150),
        steps_json TEXT NOT NULL,
        source_document_id VARCHAR(64),
        source_revision VARCHAR(50),
        source_ref VARCHAR(255),
        quality_level VARCHAR(30) DEFAULT 'VERIFIED',
        approved_by VARCHAR(64),
        active INT DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
),
(
    "evidence_conflicts",
    """
    CREATE TABLE IF NOT EXISTS evidence_conflicts (
        conflict_id VARCHAR(64) PRIMARY KEY,
        topic VARCHAR(255) NOT NULL,
        investigation_id VARCHAR(64),
        machine_id VARCHAR(64),
        source_a_json TEXT,
        source_b_json TEXT,
        comparison_json TEXT,
        severity VARCHAR(30) DEFAULT 'ADVISORY',
        detected_by VARCHAR(60) DEFAULT 'version_intelligence',
        status VARCHAR(30) DEFAULT 'OPEN',
        resolution TEXT,
        resolved_by VARCHAR(64),
        resolved_at VARCHAR(40),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
),

# ---------------------------------------------------------------------------
# Vector index bookkeeping + auditability
# ---------------------------------------------------------------------------

(
    "embedding_records",
    """
    CREATE TABLE IF NOT EXISTS embedding_records (
        embedding_id VARCHAR(64) PRIMARY KEY,
        owner_type VARCHAR(30) NOT NULL,
        owner_id VARCHAR(64) NOT NULL,
        vector_id INT NOT NULL,
        model_name VARCHAR(80) NOT NULL,
        dimension INT NOT NULL,
        index_version_id VARCHAR(64),
        content_hash VARCHAR(80),
        quality_level VARCHAR(30),
        document_status VARCHAR(30),
        machine_model VARCHAR(100),
        component VARCHAR(100),
        subsystem VARCHAR(100),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
),
(
    "vector_index_versions",
    """
    CREATE TABLE IF NOT EXISTS vector_index_versions (
        index_version_id VARCHAR(64) PRIMARY KEY,
        index_path VARCHAR(300),
        mapping_path VARCHAR(300),
        vector_count INT NOT NULL,
        dimension INT NOT NULL,
        model_name VARCHAR(80) NOT NULL,
        operation VARCHAR(40) DEFAULT 'APPEND',
        added_count INT DEFAULT 0,
        is_current INT DEFAULT 1,
        note TEXT,
        created_by VARCHAR(64),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
),
(
    "retrieval_events",
    """
    CREATE TABLE IF NOT EXISTS retrieval_events (
        retrieval_id VARCHAR(64) PRIMARY KEY,
        user_id VARCHAR(64),
        machine_id VARCHAR(64),
        investigation_id VARCHAR(64),
        query_text TEXT,
        filters_json TEXT,
        result_count INT DEFAULT 0,
        top_score FLOAT DEFAULT 0,
        latency_ms FLOAT DEFAULT 0,
        embedding_ms FLOAT DEFAULT 0,
        index_vector_count INT DEFAULT 0,
        index_version_id VARCHAR(64),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
),
(
    "audit_logs",
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
        audit_id VARCHAR(64) PRIMARY KEY,
        user_id VARCHAR(64),
        username VARCHAR(150),
        role VARCHAR(30),
        action VARCHAR(80) NOT NULL,
        entity_type VARCHAR(50),
        entity_id VARCHAR(64),
        machine_id VARCHAR(64),
        investigation_id VARCHAR(64),
        outcome VARCHAR(30) DEFAULT 'OK',
        detail_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
),
(
    "machine_qr_tokens",
    """
    CREATE TABLE IF NOT EXISTS machine_qr_tokens (
        token VARCHAR(64) PRIMARY KEY,
        machine_id VARCHAR(64) NOT NULL,
        label VARCHAR(150),
        active INT DEFAULT 1,
        scan_count INT DEFAULT 0,
        created_by VARCHAR(64),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
),
(
    "schema_migrations",
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        migration_id VARCHAR(80) PRIMARY KEY,
        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        note TEXT
    )
    """,
),
]

# Indexes are a performance detail, created best-effort (MySQL cannot express
# IF NOT EXISTS for an index, so a duplicate-index error is expected and ignored).
_EXTENSION_INDEXES: List[str] = [
    "CREATE INDEX idx_document_versions_doc ON document_versions (document_id)",
    "CREATE INDEX idx_document_chunks_doc_page ON document_chunks (document_id, page_number)",
    "CREATE INDEX idx_investigations_machine ON investigations (machine_id)",
    "CREATE INDEX idx_findings_investigation ON investigation_findings (investigation_id)",
    "CREATE INDEX idx_events_investigation ON investigation_events (investigation_id)",
    "CREATE INDEX idx_attempts_symptom ON repair_attempts (machine_id, component)",
    "CREATE INDEX idx_knowledge_status ON knowledge_items (status, quality_level)",
    "CREATE INDEX idx_embedding_owner ON embedding_records (owner_type, owner_id)",
    "CREATE INDEX idx_audit_created ON audit_logs (created_at)",
]


def ensure_extension_schema(verbose: bool = True) -> dict:
    """Create every extension table in one idempotent pass.

    Returns a small report so the caller (app startup or a maintenance script)
    can log exactly what happened instead of assuming success.
    """
    created, failed = 0, []
    for name, ddl in _EXTENSION_TABLES:
        # db.execute_write swallows driver errors and reports 0 rows affected, so
        # table existence is verified by an explicit probe afterwards rather than
        # inferred from a return value.
        db.execute_write(ddl)
        probe = db.execute_query(f"SELECT 1 AS ok FROM {name} LIMIT 1")
        if probe or _table_exists(name):
            created += 1
        else:
            failed.append(name)

    for statement in _EXTENSION_INDEXES:
        # Neither MySQL nor SQLite supports CREATE INDEX IF NOT EXISTS, so the
        # index name is probed first to keep startup output clean.
        name = statement.split(" ")[2]
        if _index_exists(name):
            continue
        try:
            db.execute_write(statement)
        except Exception:
            pass  # duplicate / unsupported syntax: never fatal

    db.execute_write(
        "REPLACE INTO schema_migrations (migration_id, note) VALUES (%s, %s)"
        if db.use_mysql else
        "INSERT OR REPLACE INTO schema_migrations (migration_id, note) VALUES (?, ?)",
        (f"extensions_v{SCHEMA_VERSION}", "additive engineering memory extension tables"),
    )

    if verbose:
        if failed:
            print(f"[Schema] Extension tables missing: {', '.join(failed)}")
        else:
            print(f"[Schema] Extension schema v{SCHEMA_VERSION} ready ({created} tables).")
    return {"schema_version": SCHEMA_VERSION, "tables": created, "missing": failed}


def _index_exists(name: str) -> bool:
    try:
        if db.use_mysql:
            rows = db.execute_query(
                "SELECT index_name AS n FROM information_schema.statistics "
                "WHERE table_schema = DATABASE() AND index_name = %s",
                (name,),
            )
        else:
            rows = db.execute_query(
                "SELECT name AS n FROM sqlite_master WHERE type = 'index' AND name = ?", (name,)
            )
        return bool(rows)
    except Exception:
        return False


def _table_exists(name: str) -> bool:
    """Dialect-specific existence probe used when a table is legitimately empty."""
    try:
        if db.use_mysql:
            rows = db.execute_query(
                "SELECT table_name AS n FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = %s",
                (name,),
            )
        else:
            rows = db.execute_query(
                "SELECT name AS n FROM sqlite_master WHERE type = 'table' AND name = ?",
                (name,),
            )
        return bool(rows)
    except Exception:
        return False
