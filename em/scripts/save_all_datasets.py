import os
import json

# Let's inspect if the transcript file in temporary storage or brain contains the prompt text
log_dir = r"C:\Users\kirithka\.gemini\antigravity\brain\9d3fb563-02a0-403b-9d8f-3c2542d994b8\.system_generated\logs"
full_log = os.path.join(log_dir, "transcript_full.jsonl")

text = ""
if os.path.exists(full_log):
    with open(full_log, "r", encoding="utf-8") as f:
        text = f.read()

os.makedirs("data/raw", exist_ok=True)

# Extract CASE-0001 to CASE-1000
idx1 = text.find("case_id,machine_id,component,failure,symptoms,resolution")
idx2 = text.find("maintenance_id,service_id,equipment_id")
idx3 = text.find("service_id,maintenance_id,equipment_id")

if idx1 != -1 and idx2 != -1:
    sub1 = text[idx1:idx2]
    # filter lines starting with CASE- or case_id
    lines1 = [l.strip() for l in sub1.replace("\\n", "\n").splitlines() if l.strip().startswith("CASE-") or l.strip().startswith("case_id")]
    with open("data/raw/cases_1000.csv", "w", encoding="utf-8") as f:
        f.write("\n".join(lines1))
    print(f"Saved data/raw/cases_1000.csv with {len(lines1)} lines.")

if idx2 != -1 and idx3 != -1:
    sub2 = text[idx2:idx3]
    lines2 = [l.strip() for l in sub2.replace("\\n", "\n").splitlines() if l.strip().startswith("MR-") or l.strip().startswith("maintenance_id")]
    with open("data/raw/maintenance_records_1000.csv", "w", encoding="utf-8") as f:
        f.write("\n".join(lines2))
    print(f"Saved data/raw/maintenance_records_1000.csv with {len(lines2)} lines.")

if idx3 != -1:
    sub3 = text[idx3:]
    lines3 = [l.strip() for l in sub3.replace("\\n", "\n").splitlines() if l.strip().startswith("SR-") or l.strip().startswith("service_id")]
    with open("data/raw/service_reports_1000.csv", "w", encoding="utf-8") as f:
        f.write("\n".join(lines3))
    print(f"Saved data/raw/service_reports_1000.csv with {len(lines3)} lines.")
