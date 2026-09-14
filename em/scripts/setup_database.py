import os
import sys
import pandas as pd

# Add root and backend to sys.path
sys.path.insert(0, os.path.abspath("."))
sys.path.insert(0, os.path.abspath("backend"))

from backend.app.db.mysql_client import db, hash_password

def setup():
    print("Setting up database tables and initial data...")
    db.init_sqlite() if not db.use_mysql else None

    # 1. Default Users
    users = [
        ("USR-001", "admin", "admin@engineeringmemory.internal", hash_password("admin_password_2026"), "ADMIN", "Lead Architect"),
        ("USR-002", "engineer", "engineer@engineeringmemory.internal", hash_password("engineer_password_2026"), "ENGINEER", "Senior Maintenance Engineer"),
        ("USR-003", "technician", "tech@engineeringmemory.internal", hash_password("tech_password_2026"), "TECHNICIAN", "Excavator Field Technician")
    ]
    for u in users:
        db.execute_write(
            "INSERT OR REPLACE INTO users (user_id, username, email, password_hash, role, full_name) VALUES (%s, %s, %s, %s, %s, %s)" if db.use_mysql else
            "INSERT OR REPLACE INTO users (user_id, username, email, password_hash, role, full_name) VALUES (?, ?, ?, ?, ?, ?)",
            u
        )
    print(f"Users initialized: {len(users)}")

    # 2. Components with 3D Mesh names
    components = [
        ("comp_pump", "Hydraulic Pump", "Hydraulic System", "hydraulic_pump", "Main variable displacement hydraulic pump"),
        ("comp_cooler", "Hydraulic Cooler", "Cooling System", "oil_cooler", "Hydraulic oil heat exchanger core"),
        ("comp_filter", "Hydraulic Filter", "Filtration System", "hydraulic_filter", "Main return line and suction filter assembly"),
        ("comp_valve", "Main Control Valve", "Control System", "control_valve", "Multi-spool main hydraulic control valve"),
        ("comp_accumulator", "Accumulator", "Pressure Storage", "accumulator", "Nitrogen pre-charged hydraulic pressure accumulator"),
        ("comp_boom", "Boom Cylinder", "Actuators", "boom_cylinder", "Dual boom hoisting hydraulic cylinders"),
        ("comp_arm", "Arm Cylinder", "Actuators", "arm_cylinder", "Stick/arm crowd hydraulic cylinder"),
        ("comp_bucket", "Bucket Cylinder", "Actuators", "bucket_cylinder", "Bucket curl hydraulic cylinder"),
        ("comp_pilot", "Pilot System", "Control System", "pilot_system", "Pilot pressure reducing valve and pilot lines"),
        ("comp_swing", "Swing Motor", "Rotary System", "swing_motor", "Upper structure rotation hydraulic swing motor"),
        ("comp_travel", "Travel Motor", "Undercarriage", "travel_motor", "Left and right track drive hydraulic motors"),
        ("comp_lines", "Hydraulic Line", "Fluid Distribution", "hydraulic_line", "High-pressure hoses and rigid hydraulic piping"),
        ("comp_oil", "Hydraulic Oil", "Fluid System", "hydraulic_tank", "Hydraulic fluid reservoir and oil quality")
    ]
    for c in components:
        db.execute_write(
            "INSERT OR REPLACE INTO components (component_id, component_name, subsystem, mesh_name, description) VALUES (%s, %s, %s, %s, %s)" if db.use_mysql else
            "INSERT OR REPLACE INTO components (component_id, component_name, subsystem, mesh_name, description) VALUES (?, ?, ?, ?, ?)",
            c
        )
    print(f"Components initialized: {len(components)}")

    # 3. Migrate Machines
    machines = [
        ("EXC-001", "ZX210", "Hydraulic Excavator", "Tata Hitachi", 6842, "Operational", "2026-08-15"),
        ("EXC-002", "PC210", "Hydraulic Excavator", "Komatsu", 7210, "Operational", "2026-07-28"),
        ("EXC-003", "EX200", "Hydraulic Excavator", "Hitachi", 5935, "Maintenance", "2026-08-30"),
        ("EXC-004", "320D", "Hydraulic Excavator", "Caterpillar", 8125, "Operational", "2026-08-05"),
        ("EXC-005", "R210", "Hydraulic Excavator", "Hyundai", 4678, "Operational", "2026-08-21")
    ]
    for i in range(1, 21):
        machines.append((f"MC-{i:03d}", "ZX200-5", "Hydraulic Excavator", "Hitachi", 5000 + i * 250, "Operational", "2026-08-01"))

    for m in machines:
        db.execute_write(
            "INSERT OR REPLACE INTO machines (machine_id, machine_model, machine_type, manufacturer, operating_hours, status, last_maintenance) VALUES (%s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
            "INSERT OR REPLACE INTO machines (machine_id, machine_model, machine_type, manufacturer, operating_hours, status, last_maintenance) VALUES (?, ?, ?, ?, ?, ?, ?)",
            m
        )
    print(f"Machines initialized: {len(machines)}")

    # 4. Migrate Maintenance Cases
    case_count = 0
    # Load 8 initial cases
    if os.path.exists("data/maintenance_cases.csv"):
        df8 = pd.read_csv("data/maintenance_cases.csv")
        for _, row in df8.iterrows():
            db.execute_write(
                "INSERT OR REPLACE INTO maintenance_cases (case_id, machine_id, subsystem, component, failure_mode, symptom, inspection_finding, repair_action, outcome, operating_hours, is_verified, source_type) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
                "INSERT OR REPLACE INTO maintenance_cases (case_id, machine_id, subsystem, component, failure_mode, symptom, inspection_finding, repair_action, outcome, operating_hours, is_verified, source_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(row['case_id']), str(row['machine_id']), str(row['subsystem']), str(row['component']), str(row['failure_mode']), str(row['symptom']), str(row['inspection_finding']), str(row['repair_action']), str(row['outcome']), int(row['operating_hours']), 1, 'historical')
            )
            case_count += 1

    # Load 1000 expanded cases
    if os.path.exists("data/raw/cases_1000.csv"):
        df1000 = pd.read_csv("data/raw/cases_1000.csv")
        for _, row in df1000.iterrows():
            db.execute_write(
                "INSERT OR REPLACE INTO maintenance_cases (case_id, machine_id, subsystem, component, failure_mode, symptom, inspection_finding, repair_action, outcome, operating_hours, is_verified, source_type) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)" if db.use_mysql else
                "INSERT OR REPLACE INTO maintenance_cases (case_id, machine_id, subsystem, component, failure_mode, symptom, inspection_finding, repair_action, outcome, operating_hours, is_verified, source_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(row['case_id']), str(row['machine_id']), "Hydraulic System", str(row['component']), str(row['failure']), str(row['symptoms']), f"Inspection finding for {row['failure']}", str(row['resolution']), "Hydraulic performance restored", 6200, 1, 'historical')
            )
            case_count += 1
    print(f"Total maintenance cases migrated: {case_count}")

if __name__ == "__main__":
    setup()
