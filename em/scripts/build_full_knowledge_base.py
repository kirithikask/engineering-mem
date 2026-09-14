import os
import random
import pandas as pd
import numpy as np

os.makedirs("data/raw", exist_ok=True)
os.makedirs("data/processed", exist_ok=True)

# 1. Expand / ensure cases_1000.csv
components = [
    "Hydraulic Pump", "Main Control Valve", "Boom Cylinder", "Arm Cylinder",
    "Bucket Cylinder", "Oil Cooler", "Hydraulic Filter", "Accumulator",
    "Pilot System", "Swing Motor", "Travel Motor", "Hydraulic Line", "Hydraulic Oil"
]

failure_modes = [
    "Internal pump leakage", "Valve spool binding", "Cylinder seal wear",
    "Cooler restriction", "Filter blockage", "Accumulator pressure loss",
    "Pilot pressure drop", "Line restriction", "Oil contamination", "Air ingress"
]

symptom_patterns = [
    ("Boom is slow", "Arm is slow", "Weak digging force"),
    ("Hydraulic oil temperature high", "Performance degrades when hot", "Slow speed"),
    ("Jerky cylinder movement", "Inconsistent control response", "System noise"),
    ("Functions drift down when idle", "Pressure drop under load", "Sluggish response"),
    ("Filter indicator light on", "System-wide power loss", "Foamy oil in reservoir"),
    ("Levers feel light and unresponsive", "Delayed function response", "Uneven function speed")
]

resolutions = [
    "Rebuilt main pump assembly and replaced seals",
    "Cleaned spool valve linkage and replaced valve seals",
    "Replaced cylinder seals and holding valve",
    "Flushed oil cooler core and replaced fan motor",
    "Replaced hydraulic filter element and cleaned suction strainer",
    "Recharged accumulator pre-charge to specification",
    "Replaced pilot pressure reducing valve and pilot filter",
    "Replaced worn hydraulic hose near swing joint",
    "Drained hydraulic oil, flushed system, replaced breather cap, refilled",
    "Bled hydraulic lines and replaced damaged fittings"
]

machines = [f"MC-0{i:02d}" for i in range(1, 21)] + [f"EXC-0{i:02d}" for i in range(1, 10)]

cases_rows = []
for i in range(1, 1001):
    case_id = f"CASE-{i:04d}"
    mc = random.choice(machines)
    comp = random.choice(components)
    fail = random.choice(failure_modes)
    sym_tup = random.choice(symptom_patterns)
    syms = "; ".join(sym_tup)
    res = random.choice(resolutions)
    cases_rows.append({
        "case_id": case_id,
        "machine_id": mc,
        "component": comp,
        "failure": fail,
        "symptoms": syms,
        "resolution": res
    })

df_cases = pd.DataFrame(cases_rows)
df_cases.to_csv("data/raw/cases_1000.csv", index=False)
print("Saved data/raw/cases_1000.csv (1000 rows)")

# 2. Maintenance Records
mr_rows = []
equip_types = ["Hydraulic Excavator", "Crawler Dozer", "Wheel Loader", "Backhoe Loader", "Motor Grader"]
equip_classes = ["20T Class Excavator", "30T Class Excavator", "45T Class Excavator", "25T Class Dozer", "35T Class Dozer"]
sites = [f"SITE-0{i}" for i in range(1, 9)]
parts = ["Cylinder seal kit", "Pump seal kit", "Valve O-rings", "Hydraulic filter", "Cooler gasket set", "Return filter element", "Hydraulic hose", "Hydraulic oil"]

for i in range(1, 1001):
    mr_id = f"MR-{i:05d}"
    sr_id = f"SR-{i:05d}"
    eq_id = f"EQ-0{random.randint(100, 240):03d}"
    eq_type = random.choice(equip_types)
    eq_class = random.choice(equip_classes)
    site = random.choice(sites)
    m_type = random.choice(["Corrective", "Preventive", "Condition-Based", "Inspection"])
    prio = random.choice(["Low", "Medium", "High", "Critical"])
    op_hours = random.randint(1500, 18500)
    comp = random.choice(components)
    fail = random.choice(failure_modes)
    sym = random.choice([
        "hydraulic flow is low at operating temperature",
        "hydraulic oil temperature rises during continuous operation",
        "travel function loses power on incline",
        "arm movement slow after hydraulic oil warms",
        "bucket cylinder leaking externally",
        "pump noise increases during operation"
    ])
    cause = random.choice(["blocked cooler core", "contaminated hydraulic oil", "high oil temperature", "damaged cylinder seal", "air entering suction line", "loss of accumulator pre-charge"])
    work = random.choice(["inspected hydraulic circuit and isolated affected component", "drained contaminated oil, flushed circuit and refilled with filtered oil", "tested pilot pressure and inspected pilot circuit", "replaced damaged hose and pressure-tested circuit"])
    part = random.choice(parts)
    tech = f"TECH-0{random.randint(100, 999):03d}"
    labor_h = round(random.uniform(1.0, 16.0), 2)
    down_h = round(random.uniform(0.25, 12.0), 2)
    mat_cost = round(random.uniform(1000.0, 65000.0), 2)
    lab_cost = round(random.uniform(500.0, 15000.0), 2)
    tot_cost = round(mat_cost + lab_cost, 2)
    status = random.choice(["Completed", "Closed", "Completed - Monitor", "Follow-up Required"])

    mr_rows.append({
        "maintenance_id": mr_id,
        "service_id": sr_id,
        "equipment_id": eq_id,
        "equipment_type": eq_type,
        "equipment_model_class": eq_class,
        "site_id": site,
        "maintenance_date": "2024-05-15",
        "maintenance_type": m_type,
        "priority": prio,
        "operating_hours": op_hours,
        "component": comp,
        "failure_mode": fail,
        "reported_symptom": sym,
        "probable_cause": cause,
        "work_performed": work,
        "parts_materials": part,
        "technician_id": tech,
        "labor_hours": labor_h,
        "downtime_hours": down_h,
        "material_cost": mat_cost,
        "labor_cost": lab_cost,
        "total_cost": tot_cost,
        "status": status
    })

df_mr = pd.DataFrame(mr_rows)
df_mr.to_csv("data/raw/maintenance_records_1000.csv", index=False)
print("Saved data/raw/maintenance_records_1000.csv (1000 rows)")

# 3. Service Reports
sr_rows = []
for r in mr_rows:
    sr_rows.append({
        "service_id": r["service_id"],
        "maintenance_id": r["maintenance_id"],
        "equipment_id": r["equipment_id"],
        "technician_id": r["technician_id"],
        "service_date": r["maintenance_date"],
        "service_type": r["maintenance_type"],
        "service_shift": random.choice(["Day", "Evening", "Night"]),
        "meter_reading_hours": r["operating_hours"],
        "inspection_finding": f"{r['component']}: {r['failure_mode']}; observed symptom: {r['reported_symptom']}.",
        "diagnostic_method": random.choice(["Visual inspection and pressure test", "Temperature and pressure checks", "Filter inspection and fluid condition check", "Operational test under load"]),
        "root_cause_confirmed": r["probable_cause"],
        "repair_or_service_action": r["work_performed"],
        "part_replaced": r["parts_materials"],
        "test_after_service": random.choice(["Pressure test passed", "Operational test passed", "Leak test passed", "Functional test passed"]),
        "service_duration_hours": r["labor_hours"],
        "downtime_hours": r["downtime_hours"],
        "service_cost": r["total_cost"],
        "next_service_due": "2024-11-15",
        "service_status": r["status"],
        "technician_notes": f"Technician checked {r['component']}, recorded reported symptom, performed required service action, and completed post-service test."
    })

df_sr = pd.DataFrame(sr_rows)
df_sr.to_csv("data/raw/service_reports_1000.csv", index=False)
print("Saved data/raw/service_reports_1000.csv (1000 rows)")
