"""Check if eExperience tender_ids overlap with APP tender_ids for possible matching."""
import json
from pathlib import Path
from collections import defaultdict

# Load eExperience award tender_ids
awards_dir = Path("backend/runtime/knowledge/awards_batch")
award_tids = defaultdict(list)
total_awards = 0

for fp in sorted(awards_dir.glob("*.json")):
    data = json.loads(fp.read_text(encoding="utf-8"))
    records = data if isinstance(data, list) else data.get("records", data.get("data", []))
    for r in records:
        tid = r.get("tender_id", "").strip()
        if tid and tid.isdigit():
            award_tids[tid].append(r)
            total_awards += 1

print(f"eExperience awards with numeric tender_id: {len(award_tids)} unique / {total_awards} total")

# Load ALL APP tender_ids
app_dir = Path("backend/runtime/knowledge/app")
app_tids = set()
total_app = 0

for fp in sorted(app_dir.glob("*.json")):
    if fp.name.startswith("offices_") or fp.name == "dept_tree.json":
        continue
    data = json.loads(fp.read_text(encoding="utf-8"))
    records = data if isinstance(data, list) else data.get("records", data.get("data", []))
    for r in records:
        if isinstance(r, dict):
            tid = r.get("tender_id", "").strip()
            if tid and tid.isdigit():
                app_tids.add(tid)
                total_app += 1

print(f"APP records with numeric tender_id: {len(app_tids)} unique / ~{total_app} total")

# Find overlap
overlap = set(award_tids.keys()) & app_tids
print(f"\nOverlap (tender_ids in BOTH eExperience AND APP): {len(overlap)}")

if overlap:
    print("\nSample overlapping tender_ids:")
    for tid in list(overlap)[:10]:
        award = award_tids[tid][0]
        print(f"  TID {tid}: Award='{award.get('title','')[:60]}' PE='{award.get('procuring_entity','')[:40]}'")
    
    # Check how many eExperience records could be matched
    matched_count = sum(len(v) for k, v in award_tids.items() if k in overlap)
    print(f"\nTotal eExperience awards that COULD match by tender_id: {matched_count} / {total_awards} ({100*matched_count/total_awards:.1f}%)")

# Also check: do APP records have the procuring_entity name?
# If so, we could match by exact PE name
print("\n=== APP procuring_entity names (sample from each file) ===")
for fp in sorted(app_dir.glob("*.json")):
    if fp.name.startswith("offices_") or fp.name == "dept_tree.json":
        continue
    data = json.loads(fp.read_text(encoding="utf-8"))
    records = data if isinstance(data, list) else data.get("records", data.get("data", []))
    pes = set()
    for r in records[:500]:
        if isinstance(r, dict) and r.get("procuring_entity"):
            pes.add(r["procuring_entity"][:60])
    print(f"  {fp.name}: {len(pes)} unique procuring_entities (sample: {list(pes)[:2]})")
