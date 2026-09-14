import os

# Create data/raw directory
os.makedirs("data/raw", exist_ok=True)

# 1. cases_1000.csv
cases_content = """case_id,machine_id,component,failure,symptoms,resolution
CASE-0001,MC-012,Accumulator,Accumulator pressure loss,jerky start on hydraulic functions after startup on a slope,Replaced accumulator bladder
CASE-0002,MC-013,Oil Cooler,Cooler restriction,gradual power loss tied to running time after a long shift,Cleaned and flushed cooler
CASE-0003,MC-006,Hydraulic Oil,Oil contamination,performance degraded steadily over a month when hot,"Drained oil, replaced breather cap, refilled"
CASE-0004,MC-017,Hydraulic Line,Line restriction,slow function only on one side of the machine under load,Replaced worn hydraulic hose near swing joint
CASE-0005,MC-012,Control Valve,Valve problem,bucket curl function completely unresponsive under load,Cleaned and adjusted spool valve linkage
CASE-0006,MC-005,Hydraulic Filter,Filter blockage,filter warning light on dashboard at high RPM,Cleaned suction strainer contaminated with debris
CASE-0007,MC-008,Arm Cylinder,Cylinder leakage,cylinder slowly drops on its own when parked on a slope,Replaced cylinder holding valve
CASE-0008,MC-007,Control Valve,Valve problem,bucket curl function completely unresponsive when cold,Replaced directional control valve
CASE-0009,MC-009,Boom Cylinder,Cylinder leakage,cylinder slowly drops on its own when parked during digging cycles,Replaced cylinder assembly
CASE-0010,MC-001,Pilot System,Pilot pressure problem,levers feel light and unresponsive when cold,Replaced pilot filter
CASE-0011,MC-019,Hydraulic Line,Line restriction,gradual loss of pressure during long digging cycles at high RPM,Replaced fitting and line section
CASE-0012,MC-014,Hydraulic Oil,Oil contamination,metallic smell from hydraulic tank during simultaneous functions,Replaced with correct oil grade
CASE-0013,MC-002,Oil Cooler,Cooler restriction,machine slows down noticeably after a long shift,Replaced fan belt and cleaned fins
CASE-0014,MC-014,Control Valve,Valve problem,bucket curl function completely unresponsive when hot,Cleaned and lubricated spool valve
CASE-0015,MC-004,Accumulator,Accumulator pressure loss,jerky start on hydraulic functions after startup after refueling,Recharged accumulator to spec pressure
CASE-0016,MC-018,Hydraulic Oil,Oil contamination,foamy oil visible in reservoir sight glass during simultaneous functions,Drained and replaced hydraulic oil
CASE-0017,MC-019,Oil Cooler,Cooler restriction,machine slows down noticeably intermittently,Pressure-washed cooler core
CASE-0018,MC-004,Hydraulic Filter,Filter blockage,filter warning light on dashboard when cold,Replaced hydraulic filter element
CASE-0019,MC-008,Oil Cooler,Cooler restriction,operation fine at start but slows when cold,Replaced seized cooling fan bearing
CASE-0020,MC-004,Oil Cooler,Cooler restriction,gradual power loss tied to running time when hot,Cleaned and flushed cooler
CASE-0021,MC-002,Hydraulic Pump,Internal pump leakage,reduced lifting capacity under load,Rebuilt main pump assembly
CASE-0022,MC-005,Hydraulic Line,Line restriction,gradual loss of pressure during long digging cycles on uneven ground,Replaced hydraulic hose
CASE-0023,MC-011,Hydraulic Oil,Oil contamination,metallic smell from hydraulic tank when cold,Replaced with correct oil grade
CASE-0024,MC-013,Hydraulic Oil,Oil contamination,performance degraded steadily over a month on uneven ground,"Drained oil, replaced breather cap, refilled"
CASE-0025,MC-002,Pilot System,Pilot pressure problem,levers feel light and unresponsive when cold,Replaced pilot filter
CASE-0026,MC-001,Pilot System,Pilot pressure problem,machine feels unresponsive right after startup after refueling,Replaced pilot pressure reducing valve
CASE-0027,MC-006,Hydraulic Pump,Internal pump leakage,boom and arm both weaker than normal after refueling,Replaced pump seal kit
CASE-0028,MC-011,Hydraulic Pump,Internal pump leakage,digging force dropped noticeably during digging cycles,Repaired internal pump components
CASE-0029,MC-016,Accumulator,Accumulator pressure loss,jerky start on hydraulic functions after startup when hot,Recharged accumulator to spec pressure
CASE-0030,MC-020,Hydraulic Line,Line restriction,slow function only on one side of the machine on a slope,Replaced fitting and line section
CASE-0031,MC-009,Control Valve,Valve problem,bucket curl function completely unresponsive at high RPM,Replaced valve seal kit
CASE-0032,MC-015,Hydraulic Filter,Filter blockage,jerky and inconsistent boom motion on a slope,Cleaned suction strainer
CASE-0033,MC-017,Hydraulic Oil,Oil contamination,performance degraded steadily over a month on a slope,Drained and replaced hydraulic oil
CASE-0034,MC-017,Pilot System,Pilot pressure problem,all functions feel weak but pump pressure tests normal during digging cycles,Replaced pilot filter
CASE-0035,MC-018,Oil Cooler,Cooler restriction,machine slows down noticeably after refueling,Replaced fan belt and cleaned fins
CASE-0036,MC-019,Hydraulic Pump,Internal pump leakage,struggles to lift full bucket load during digging cycles,Replaced pump seal kit and flushed system
CASE-0037,MC-020,Control Valve,Valve problem,swing function delayed by a few seconds after refueling,Cleaned and lubricated spool valve
CASE-0038,MC-020,Hydraulic Filter,Filter blockage,jerky and inconsistent boom motion during digging cycles,Replaced hydraulic filter element
CASE-0039,MC-018,Pilot System,Pilot pressure problem,all functions feel weak but pump pressure tests normal after startup,Replaced pilot pressure reducing valve
CASE-0040,MC-019,Arm Cylinder,Cylinder leakage,weak force compared to other functions during digging cycles,Replaced cylinder seal kit
"""

with open("data/raw/cases_1000_sample.csv", "w", encoding="utf-8") as f:
    f.write(cases_content)

print("Created data/raw structure")
