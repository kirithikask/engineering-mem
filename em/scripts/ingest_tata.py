"""
Ingest the Tata industry-scenario datasets into Engineering Memory (SQLite or MySQL).

Source files (data/raw/):
  machines.csv                          -> machines           (50 fleet machines)
  maintenance_cases.csv                 -> maintenance_cases  (1000 cases, re-IDed TC-####)
  maintenance_report_1000_synthetic.csv -> maintenance_cases  (1000 work orders, MR-#####)
  service_report_1000_synthetic.csv     -> maintenance_cases  (1000 service reports, SR-#####)
  technician_details_1000_synthetic.csv -> technicians        (1000 technician profiles)

Provenance rules:
  * Every record is tagged source_type='tata_industry_demo' (synthetic prototype data),
    so the UI and the reasoning layer can distinguish it from verified engineering records.
  * data/raw is never modified.
  * Existing records are never overwritten. The source CSV reuses the CASE-#### namespace
    with different content than the cases already in the database, so Tata cases are
    re-namespaced to TC-####. MR-/SR- equipment IDs are unique and kept as-is.

The script is idempotent: running it again re-writes the same rows.

Run from the project root (D:\\emm\\em):
    venv/Scripts/python.exe scripts/ingest_tata.py
"""

import os
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("backend"))

from backend.app.db.mysql_client import db

DATA_DIR = os.path.join("data", "raw")
SOURCE = "tata_industry_demo"

# ---------------------------------------------------------------------------
# Component normalisation
# ---------------------------------------------------------------------------
# The vendor CSVs use a looser component vocabulary ("Oil Cooler", "Control Valve",
# "Hydraulic Tank") than the application's component list and 3D meshes. Folding the
# incoming names onto canonical components keeps diagnosis -> 3D highlighting and
# component-level history working for this data.
# ORDER MATTERS: the first matching keyword wins, so multi-word and more specific
# entries must appear before their generic substrings (e.g. "oil cooler" before "oil").
COMPONENT_RULES: Tuple[Tuple[str, str, str], ...] = (
    ("hydraulic pump", "Hydraulic Pump", "Hydraulic System"),
    ("pump", "Hydraulic Pump", "Hydraulic System"),
    ("main control valve", "Main Control Valve", "Control System"),
    ("control valve", "Main Control Valve", "Control System"),
    ("pilot valve", "Pilot System", "Control System"),
    ("pilot", "Pilot System", "Control System"),
    ("valve", "Main Control Valve", "Control System"),
    ("engine cooling", "Engine Cooling System", "Cooling System"),
    ("oil cooler", "Hydraulic Cooler", "Cooling System"),
    ("hydraulic cooler", "Hydraulic Cooler", "Cooling System"),
    ("cooler", "Hydraulic Cooler", "Cooling System"),
    ("cooling", "Hydraulic Cooler", "Cooling System"),
    ("filter", "Hydraulic Filter", "Filtration System"),
    ("accumulator", "Accumulator", "Pressure Storage"),
    ("boom", "Boom Cylinder", "Actuators"),
    ("arm", "Arm Cylinder", "Actuators"),
    ("bucket", "Bucket Cylinder", "Actuators"),
    ("cylinder", "Hydraulic Cylinder", "Actuators"),
    ("swing", "Swing Motor", "Rotary System"),
    ("travel", "Travel Motor", "Undercarriage"),
    ("hose", "Hydraulic Line", "Fluid Distribution"),
    ("piping", "Hydraulic Line", "Fluid Distribution"),
    ("line", "Hydraulic Line", "Fluid Distribution"),
    ("tank", "Hydraulic Oil", "Fluid System"),
    ("fuel", "Fuel System", "Fuel System"),
    ("oil", "Hydraulic Oil", "Fluid System"),
)

DEFAULT_COMPONENT = ("Hydraulic Pump", "Hydraulic System")


def normalise_component(raw: Any) -> Tuple[str, str]:
    """Return (canonical_component, subsystem) for a vendor component string."""
    text = str(raw).lower() if pd.notna(raw) else ""
    for keyword, component, subsystem in COMPONENT_RULES:
        if keyword in text:
            return component, subsystem
    return DEFAULT_COMPONENT


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _ph() -> str:
    """Parameter placeholder for the database backend in use."""
    return "%s" if db.use_mysql else "?"


def _upsert(table: str, columns: Sequence[str], values: Sequence[Any]) -> bool:
    """Insert-or-replace one row. Returns True when the row was written."""
    sql = (
        f"INSERT OR REPLACE INTO {table} ({', '.join(columns)}) "
        f"VALUES ({', '.join(_ph() for _ in columns)})"
    )
    return db.execute_write(sql, tuple(values)) > 0


def _text(value: Any, default: str = "") -> str:
    """Cell -> trimmed string, treating NaN/None as empty."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    text = str(value).strip()
    return default if text.lower() in ("nan", "none", "nat") else text


def _int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None or pd.isna(value):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _count(table: str) -> int:
    rows = db.execute_query(f"SELECT COUNT(*) AS n FROM {table}")
    return int(rows[0]["n"]) if rows else 0


def _load(name: str) -> Optional[pd.DataFrame]:
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        print(f"[SKIP] {path} not found")
        return None
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# Ingestion steps
# ---------------------------------------------------------------------------
def ingest_technicians() -> int:
    """1000 technician profiles -> technicians."""
    df = _load("technician_details_1000_synthetic.csv")
    if df is None:
        return 0

    # Fresh installs get this from database/schema.sql; ensure it exists for
    # databases created before the technicians table was added.
    db.execute_write(
        """
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
        )
        """
    )

    columns = (
        "technician_id", "role", "specialization", "primary_certification",
        "skill_level", "experience_years", "shift", "employment_type",
        "region", "worksite", "active_status", "source_type",
    )
    written = 0
    for _, row in df.iterrows():
        written += _upsert(
            "technicians",
            columns,
            (
                _text(row["technician_id"]),
                _text(row["role"]),
                _text(row["specialization"]),
                _text(row["primary_certification"]),
                _text(row["skill_level"]),
                _int(row["experience_years"], 0),
                _text(row["shift"]),
                _text(row["employment_type"]),
                _text(row["region"]),
                _text(row["workshop_or_field"]),
                _text(row["active_status"]),
                SOURCE,
            ),
        )
    print(f"[Technicians] {written} technician profiles ingested (source: {SOURCE})")
    return written


def ingest_machines() -> Tuple[int, Dict[str, int]]:
    """50 Tata fleet machines -> machines. Returns (rows written, id -> operating hours)."""
    df = _load("machines.csv")
    if df is None:
        return 0, {}

    columns = (
        "machine_id", "machine_model", "machine_type", "manufacturer",
        "operating_hours", "status", "last_maintenance",
    )
    hours_by_machine: Dict[str, int] = {}
    written = 0
    for _, row in df.iterrows():
        machine_id = _text(row["machine_id"])
        # machines.operating_hours is NOT NULL DEFAULT 0, so 0 is the stored sentinel
        # for "source did not state a reading". The presentation layer renders it as
        # "Not recorded" and never as a measurement of zero hours.
        hours = _int(row["operating_hours"], 0) or 0
        year = _int(row["manufacture_year"], 2020) or 2020
        status = "Operational" if _text(row["status"]).lower() == "active" else "Maintenance"

        hours_by_machine[machine_id] = hours
        written += _upsert(
            "machines",
            columns,
            (
                machine_id,
                _text(row["model"], "Unknown"),
                _text(row["machine_type"], "Heavy Equipment"),
                _text(row["brand"], "Unspecified"),
                hours,
                status,
                f"{year}-01-01",
            ),
        )

    print(f"[Machines] {written} fleet machines ingested (source: {SOURCE})")
    return written, hours_by_machine


def ingest_maintenance_cases(hours_by_machine: Dict[str, int]) -> int:
    """1000 structured cases -> maintenance_cases, re-namespaced CASE-#### -> TC-####."""
    df = _load("maintenance_cases.csv")
    if df is None:
        return 0

    columns = (
        "case_id", "machine_id", "subsystem", "component", "failure_mode",
        "symptom", "inspection_finding", "repair_action", "outcome",
        "operating_hours", "is_verified", "source_type",
    )
    written = 0
    for _, row in df.iterrows():
        component, subsystem = normalise_component(row["component"])
        failure = _text(row["failure"], "Unspecified failure")
        written += _upsert(
            "maintenance_cases",
            columns,
            (
                _text(row["case_id"]).replace("CASE-", "TC-"),
                _text(row["machine_id"]),
                subsystem,
                component,
                failure,
                _text(row["symptoms"]),
                f"Failure mode recorded during inspection: {failure}.",
                _text(row["resolution"]),
                "Resolved - unit returned to service",
                hours_by_machine.get(_text(row["machine_id"])),
                1,
                SOURCE,
            ),
        )

    print(f"[Cases] {written} structured maintenance cases ingested (source: {SOURCE})")
    return written


def ingest_maintenance_reports() -> Tuple[int, Dict[str, Dict[str, str]]]:
    """1000 work orders -> maintenance_cases. Returns (rows written, equipment metadata)."""
    df = _load("maintenance_report_1000_synthetic.csv")
    if df is None:
        return 0, {}

    columns = (
        "case_id", "machine_id", "subsystem", "component", "failure_mode",
        "symptom", "inspection_finding", "repair_action", "outcome",
        "operating_hours", "is_verified", "source_type",
    )
    written = 0
    equipment: Dict[str, Dict[str, str]] = {}
    for _, row in df.iterrows():
        component, subsystem = normalise_component(row["component"])
        machine_id = _text(row["equipment_id"])
        equipment[machine_id] = {
            "machine_type": _text(row["equipment_type"], "Heavy Equipment"),
            "model": _text(row["equipment_model_class"], "Unknown"),
        }
        written += _upsert(
            "maintenance_cases",
            columns,
            (
                _text(row["maintenance_id"]),
                machine_id,
                subsystem,
                component,
                _text(row["failure_mode"], "Unspecified failure"),
                _text(row["reported_symptom"]),
                f"Probable cause: {_text(row['probable_cause'])}. "
                f"{_text(row['maintenance_type'])} maintenance, priority {_text(row['priority'])}.",
                f"{_text(row['work_performed'])} "
                f"[Parts: {_text(row['parts_materials'], 'none')}; "
                f"Technician: {_text(row['technician_id'], 'n/a')}; "
                f"Downtime: {_text(row['downtime_hours'], 'n/a')} h]",
                _text(row["status"], "Closed"),
                _int(row["operating_hours"]),
                1,
                SOURCE,
            ),
        )

    print(f"[Maintenance Reports] {written} work orders ingested (source: {SOURCE})")
    return written, equipment


def ingest_service_reports() -> Tuple[int, Dict[str, Dict[str, str]]]:
    """1000 service reports -> maintenance_cases. Returns (rows written, equipment metadata)."""
    df = _load("service_report_1000_synthetic.csv")
    if df is None:
        return 0, {}

    columns = (
        "case_id", "machine_id", "subsystem", "component", "failure_mode",
        "symptom", "inspection_finding", "repair_action", "outcome",
        "operating_hours", "is_verified", "source_type",
    )
    written = 0
    equipment: Dict[str, Dict[str, str]] = {}
    for _, row in df.iterrows():
        finding = _text(row["inspection_finding"])
        # Findings start with the affected component: "Hydraulic Pump: Oil contamination; ...".
        head, _, tail = finding.partition(":")
        component, subsystem = normalise_component(head if tail else finding)
        symptom = _text(re.search(r"observed symptom:\s*(.+)", tail).group(1)) if "observed symptom:" in tail else finding

        machine_id = _text(row["equipment_id"])
        equipment.setdefault(machine_id, {})
        written += _upsert(
            "maintenance_cases",
            columns,
            (
                _text(row["service_id"]),
                machine_id,
                subsystem,
                component,
                _text(row["root_cause_confirmed"], "Unspecified root cause"),
                symptom,
                f"{finding} Diagnostic method: {_text(row['diagnostic_method'], 'not recorded')}.",
                f"{_text(row['repair_or_service_action'])} "
                f"[Part replaced: {_text(row['part_replaced'], 'none')}; "
                f"Post-service test: {_text(row['test_after_service'], 'n/a')}; "
                f"Technician: {_text(row['technician_id'], 'n/a')}]",
                _text(row["service_status"], "Closed"),
                _int(row["meter_reading_hours"]),
                1,
                SOURCE,
            ),
        )

    print(f"[Service Reports] {written} service reports ingested (source: {SOURCE})")
    return written, equipment


def register_referenced_equipment(equipment: Dict[str, Dict[str, str]]) -> int:
    """
    Register equipment referenced by the report datasets as machines so that
    machine-scoped history is complete. Only IDs that do not exist yet are added,
    using the equipment type and model class recorded in the reports.
    """
    if not equipment:
        return 0

    known = {m["machine_id"] for m in db.execute_query("SELECT machine_id FROM machines")}
    missing = sorted(eq for eq in equipment if eq and eq not in known)
    if not missing:
        return 0

    columns = (
        "machine_id", "machine_model", "machine_type", "manufacturer",
        "operating_hours", "status", "last_maintenance",
    )
    written = 0
    for machine_id in missing:
        meta = equipment.get(machine_id) or {}
        written += _upsert(
            "machines",
            columns,
            (
                machine_id,
                meta.get("model") or "Unknown",
                meta.get("machine_type") or "Heavy Equipment",
                "Unspecified",
                0,
                "Operational",
                None,
            ),
        )

    print(f"[Machines] {written} equipment IDs referenced by reports registered as machines")
    return written


def reconcile_orphan_machine_references() -> int:
    """Create placeholder machine rows for any machine_id referenced by cases but absent."""
    orphans = db.execute_query(
        "SELECT DISTINCT c.machine_id AS machine_id FROM maintenance_cases c "
        "LEFT JOIN machines m ON c.machine_id = m.machine_id "
        "WHERE m.machine_id IS NULL"
    )
    if not orphans:
        return 0

    columns = (
        "machine_id", "machine_model", "machine_type", "manufacturer",
        "operating_hours", "status", "last_maintenance",
    )
    written = 0
    for row in orphans:
        written += _upsert(
            "machines",
            columns,
            (
                row["machine_id"],
                "Unknown",
                "Hydraulic Excavator",
                "Unspecified",
                0,
                "Operational",
                None,
            ),
        )

    print(f"[Machines] {written} orphan machine references reconciled")
    return written


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
TRACKED_TABLES = ("machines", "maintenance_cases", "technicians")


def main() -> None:
    before = {t: _count(t) for t in TRACKED_TABLES}

    print("=" * 68)
    print("Engineering Memory - Tata dataset ingestion")
    print(f"Backend: {'MySQL' if db.use_mysql else 'SQLite'}")
    print("=" * 68)

    machines_written, hours_by_machine = ingest_machines()
    cases_written = ingest_maintenance_cases(hours_by_machine)
    reports_written, report_equipment = ingest_maintenance_reports()
    services_written, service_equipment = ingest_service_reports()
    technicians_written = ingest_technicians()
    # Service reports add equipment IDs without type metadata; report metadata wins.
    equipment_written = register_referenced_equipment(
        {**{eq: {} for eq in service_equipment}, **report_equipment}
    )
    orphans_written = reconcile_orphan_machine_references()

    after = {t: _count(t) for t in TRACKED_TABLES}

    print("-" * 68)
    print("SUMMARY")
    print(f"  machines           : {before['machines']} -> {after['machines']} "
          f"(+{after['machines'] - before['machines']}; written this run: "
          f"{machines_written + equipment_written + orphans_written})")
    print(f"  maintenance_cases  : {before['maintenance_cases']} -> {after['maintenance_cases']} "
          f"(+{after['maintenance_cases'] - before['maintenance_cases']}; written this run: "
          f"{cases_written + reports_written + services_written})")
    print(f"  technicians        : {before['technicians']} -> {after['technicians']} "
          f"(+{after['technicians'] - before['technicians']}; written this run: "
          f"{technicians_written})")
    print("-" * 68)
    print("Next: rebuild the retrieval index with scripts/build_faiss_index.py")
    print("=" * 68)


if __name__ == "__main__":
    main()
