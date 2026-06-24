"""Check what fields eExperience award data has and how to match with APP."""
import json
from pathlib import Path

awards_dir = Path("backend/runtime/knowledge/awards_batch")

# Check all batch files for fields
all_fields = set()
total_records = 0
sample_records = []
for fp in sorted(awards_dir.glob("*.json")):
    data = json.loads(fp.read_text(encoding="utf-8"))
    records = data if isinstance(data, list) else data.get("records", data.get("data", []))
    total_records += len(records)
    for r in records[:5]:
        if len(sample_records) < 10:
            sample_records.append(r)
        all_fields.update(r.keys())

print(f"Total eExperience records: {total_records}")
print(f"Fields available: {sorted(all_fields)}")
print()

# Check if any have package_no
has_pkg = 0
for fp in sorted(awards_dir.glob("*.json")):
    data = json.loads(fp.read_text(encoding="utf-8"))
    records = data if isinstance(data, list) else data.get("records", data.get("data", []))
    for r in records:
        if r.get("package_no"):
            has_pkg += 1
            if has_pkg <= 3:
                print(f"  Record with package_no: {r.get('package_no')}")

print(f"\nRecords with package_no: {has_pkg}/{total_records}")
print(f"Records WITHOUT package_no: {total_records - has_pkg}")

# Show sample record fields
print("\n=== Sample eExperience record ===")
r = sample_records[0]
for k, v in r.items():
    print(f"  {k}: {str(v)[:80]}")

# Search APP by procuring entity office name  
# The procuring_entity in eExperience often contains the PE office name
print("\n=== Procuring Entity patterns (first 20) ===")
pes = set()
for fp in sorted(awards_dir.glob("*.json")):
    data = json.loads(fp.read_text(encoding="utf-8"))
    records = data if isinstance(data, list) else data.get("records", data.get("data", []))
    for r in records:
        pe = r.get("procuring_entity", "")
        if pe:
            # Extract office name pattern
            parts = pe.split(",")
            for p in parts:
                if "executive engineer" in p.lower() or "office of the" in p.lower() or "xen" in p.lower():
                    pes.add(p.strip()[:60])
                    break
            else:
                pes.add(parts[-1].strip()[:60] if len(parts) > 1 else pe[:60])

for pe in sorted(list(pes))[:20]:
    print(f"  {pe}")

# Check: do eExperience awards have agency_target?
agencies = {}
for fp in sorted(awards_dir.glob("*.json")):
    data = json.loads(fp.read_text(encoding="utf-8"))
    records = data if isinstance(data, list) else data.get("records", data.get("data", []))
    for r in records:
        a = r.get("agency_target", "UNKNOWN")
        agencies[a] = agencies.get(a, 0) + 1

print(f"\n=== Agency distribution in eExperience ===")
for a, c in sorted(agencies.items(), key=lambda x: -x[1])[:15]:
    print(f"  {a}: {c}")
