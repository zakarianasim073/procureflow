"""
Create all expected runtime directories and empty placeholder JSON files
to prevent the V3 backend from hanging on missing JSON files.
"""
from pathlib import Path
import json
import os

BASE = Path("D:/A1/procurementflow_final_v3/procurementflow/runtime")
ROOT = Path("D:/A1/procurementflow_final_v3/procurementflow")

PLACEHOLDER = json.dumps([])  # empty JSON array
PLACEHOLDER_OBJ = json.dumps({})  # empty JSON object

directories = [
    "data_intel",
    "knowledge/app",
    "knowledge/contractordna",
    "knowledge/econtracts",
    "knowledge/eexperience",
    "knowledge/eexperience_all/completed",
    "knowledge/eexperience_all/ongoing",
    "knowledge/npp",
    "knowledge/contractor_dna",
    "knowledge/eexperience/bwdb",
    "knowledge/eexperience/pwd",
    "knowledge/eexperience/lged",
    "market_data",
    "monitor",
    "logs/system",
    "logs/sessions",
    "logs/agents",
    "logs/pipeline",
    "data",
    "outputs",
    "downloads",
]

placeholder_files = [
    "market_data/market_rates.json",
    "market_data/market_indices.json",
    "data_intel/bwdb_live_tenders.json",
    "data_intel/dedup_index.json",
    "data_intel/collection_log.json",
    "data_intel/bwdb_all_tenders.json",
    "knowledge/app/structure.json",
    "knowledge/contractordna/contractors.json",
    "knowledge/econtracts/flat.json",
    "knowledge/eexperience/all_experience.json",
    "knowledge/eexperience_all/completed/all_completed.json",
    "knowledge/eexperience_all/ongoing/all_ongoing.json",
    "monitor/monitor_config.json",
]

count = 0

# Create directories
for d in directories:
    p = BASE / d
    p.mkdir(parents=True, exist_ok=True)
    count += 1
    print(f"  [DIR]  {p.relative_to(BASE) if p.is_relative_to(BASE) else p}")

# Create placeholder files (empty JSON arrays)
for f in placeholder_files:
    p = BASE / f
    p.parent.mkdir(parents=True, exist_ok=True)
    if f.endswith(".json"):
        p.write_text(PLACEHOLDER if "monitor_config" not in f else json.dumps({
            "scan_interval_hours": 24, "alert_email": "", "enabled": False
        }), encoding="utf-8")
    elif f.endswith(".jsonl"):
        p.write_text("", encoding="utf-8")
    count += 1
    print(f"  [FILE] {p.relative_to(BASE) if p.is_relative_to(BASE) else p}")

# Also create SOR monitoring files
sor_base = ROOT / "backend" / "app" / "sor"
for agency in ["bwdb", "pwd", "lged"]:
    agency_file = sor_base / agency / "rates.json"
    if agency_file.exists():
        print(f"  [EXISTS] {agency}/rates.json")

print(f"\nCreated {count} directories/files. All JSON reads will now return empty data safely.")
