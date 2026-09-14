-- Engineering Memory Relational Database Schema
-- Compatible with MySQL 8.0+ and SQLite

CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(64) PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'TECHNICIAN',
    full_name VARCHAR(150),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS machines (
    machine_id VARCHAR(64) PRIMARY KEY,
    machine_model VARCHAR(100) NOT NULL,
    machine_type VARCHAR(100) NOT NULL,
    manufacturer VARCHAR(100) NOT NULL,
    operating_hours INT NOT NULL DEFAULT 0,
    status VARCHAR(50) NOT NULL DEFAULT 'Operational',
    last_maintenance DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS technicians (
    technician_id VARCHAR(64) PRIMARY KEY,
    role VARCHAR(100),
    specialization VARCHAR(150),
    primary_certification VARCHAR(150),
    skill_level VARCHAR(50),
    experience_years INT,
    shift VARCHAR(50),
    employment_type VARCHAR(100),
    region VARCHAR(100),
    worksite VARCHAR(100),
    active_status VARCHAR(50),
    source_type VARCHAR(50) DEFAULT 'tata_industry_demo',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS components (
    component_id VARCHAR(64) PRIMARY KEY,
    component_name VARCHAR(100) NOT NULL,
    subsystem VARCHAR(100) NOT NULL,
    mesh_name VARCHAR(100),
    description TEXT
);

CREATE TABLE IF NOT EXISTS failure_modes (
    failure_id VARCHAR(64) PRIMARY KEY,
    failure_name VARCHAR(150) NOT NULL,
    component_id VARCHAR(64),
    description TEXT,
    FOREIGN KEY (component_id) REFERENCES components(component_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS symptoms (
    symptom_id VARCHAR(64) PRIMARY KEY,
    symptom_text VARCHAR(255) NOT NULL,
    category VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS maintenance_cases (
    case_id VARCHAR(64) PRIMARY KEY,
    machine_id VARCHAR(64) NOT NULL,
    subsystem VARCHAR(100),
    component VARCHAR(100) NOT NULL,
    failure_mode VARCHAR(150) NOT NULL,
    symptom TEXT NOT NULL,
    inspection_finding TEXT,
    repair_action TEXT,
    outcome VARCHAR(255),
    operating_hours INT,
    is_verified INT DEFAULT 1,
    source_type VARCHAR(50) DEFAULT 'historical',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS case_symptoms (
    case_id VARCHAR(64) NOT NULL,
    symptom_id VARCHAR(64) NOT NULL,
    PRIMARY KEY (case_id, symptom_id)
);

CREATE TABLE IF NOT EXISTS documents (
    document_id VARCHAR(64) PRIMARY KEY,
    document_name VARCHAR(255) NOT NULL,
    document_type VARCHAR(50) NOT NULL,
    file_path VARCHAR(500),
    file_size_bytes INT,
    version VARCHAR(50) DEFAULT '1.0',
    status VARCHAR(50) DEFAULT 'Indexed',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL,
    page_number INT DEFAULT 1,
    section_heading VARCHAR(255),
    component VARCHAR(100),
    machine_model VARCHAR(100),
    chunk_text TEXT NOT NULL,
    vector_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sensor_records (
    record_id VARCHAR(64) PRIMARY KEY,
    machine_id VARCHAR(64) NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ps1_mean FLOAT, ps2_mean FLOAT, ps3_mean FLOAT,
    ts1_mean FLOAT, ts2_mean FLOAT,
    cooler_condition INT,
    valve_condition INT,
    pump_leakage INT,
    accumulator_pressure INT,
    stable INT
);

CREATE TABLE IF NOT EXISTS model_predictions (
    pred_id VARCHAR(64) PRIMARY KEY,
    machine_id VARCHAR(64) NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    pump_leakage_pred INT NOT NULL,
    pump_leakage_prob FLOAT NOT NULL,
    model_version VARCHAR(50) DEFAULT 'RandomForest_v1.0'
);

CREATE TABLE IF NOT EXISTS retrieval_logs (
    log_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64),
    machine_id VARCHAR(64),
    query_text TEXT NOT NULL,
    retrieved_cases TEXT,
    retrieved_chunks TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS diagnoses (
    diagnosis_id VARCHAR(64) PRIMARY KEY,
    machine_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64),
    symptoms_analyzed TEXT NOT NULL,
    evidence_sufficiency VARCHAR(50) NOT NULL,
    likely_cause VARCHAR(255),
    affected_component VARCHAR(100),
    component_id VARCHAR(64),
    confidence_score FLOAT,
    reasoning TEXT,
    recommended_inspection TEXT,
    previous_resolution TEXT,
    verified_by_tech INT DEFAULT 0,
    actual_cause_confirmed VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS diagnosis_evidence (
    evidence_id VARCHAR(64) PRIMARY KEY,
    diagnosis_id VARCHAR(64) NOT NULL,
    evidence_type VARCHAR(50) NOT NULL,
    source_id VARCHAR(64) NOT NULL,
    title VARCHAR(255),
    content_snippet TEXT,
    similarity_score FLOAT,
    FOREIGN KEY (diagnosis_id) REFERENCES diagnoses(diagnosis_id) ON DELETE CASCADE
);
