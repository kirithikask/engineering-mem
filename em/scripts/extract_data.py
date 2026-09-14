import json
import os

log_path = r"C:\Users\kirithka\.gemini\antigravity\brain\9d3fb563-02a0-403b-9d8f-3c2542d994b8\.system_generated\logs\transcript_full.jsonl"

os.makedirs("data/raw", exist_ok=True)

with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        if "case_id,machine_id,component,failure" in line:
            obj = json.loads(line)
            # Find the string inside tool_calls or content
            text = ""
            if "tool_calls" in obj:
                for tc in obj["tool_calls"]:
                    text += str(tc)
            if "content" in obj:
                text += str(obj["content"])
            
            idx1 = text.find("case_id,machine_id,component,failure")
            idx2 = text.find("maintenance_id,service_id,equipment_id")
            idx3 = text.find("service_id,maintenance_id,equipment_id")
            
            if idx1 != -1 and idx2 != -1 and idx3 != -1:
                t1 = text[idx1:idx2]
                t2 = text[idx2:idx3]
                t3 = text[idx3:]
                
                t1_lines = [l.strip() for l in t1.replace('\\n', '\n').splitlines() if l.strip().startswith("CASE-") or l.strip().startswith("case_id")]
                t2_lines = [l.strip() for l in t2.replace('\\n', '\n').splitlines() if l.strip().startswith("MR-") or l.strip().startswith("maintenance_id")]
                t3_lines = [l.strip() for l in t3.replace('\\n', '\n').splitlines() if l.strip().startswith("SR-") or l.strip().startswith("service_id")]
                
                with open("data/raw/cases_1000.csv", "w", encoding="utf-8") as f1:
                    f1.write("\n".join(t1_lines))
                
                with open("data/raw/maintenance_records_1000.csv", "w", encoding="utf-8") as f2:
                    f2.write("\n".join(t2_lines))

                with open("data/raw/service_reports_1000.csv", "w", encoding="utf-8") as f3:
                    f3.write("\n".join(t3_lines))
                
                print("Extracted successfully:")
                print("cases_1000.csv lines:", len(t1_lines))
                print("maintenance_records_1000.csv lines:", len(t2_lines))
                print("service_reports_1000.csv lines:", len(t3_lines))
                break
