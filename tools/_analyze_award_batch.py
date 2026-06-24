import json

# Sample an award batch file to see if package_no is stored
with open('backend/runtime/knowledge/awards_batch/LGED_batch_015.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
records = data if isinstance(data, list) else data.get('records', data.get('data', []))

print(f"Total records: {len(records)}")
if records:
    r = records[0]
    print(f"\nFirst record keys: {list(r.keys())}")
    print(f"First record:")
    print(json.dumps(r, indent=2, ensure_ascii=False)[:1500])

# Check how many have package_no
has_pkg = sum(1 for r in records if r.get('package_no'))
print(f"\nRecords with package_no: {has_pkg}/{len(records)}")

# Sample some package_nos
if has_pkg:
    pkgs = [r.get('package_no','') for r in records if r.get('package_no')][:15]
    print(f"\nSample package_nos:")
    for p in pkgs:
        print(f"  '{p}'")

# Also check PWD APP data - sample a few records with their package_nos
print("\n\n=== PWD APP records (sample) ===")
with open('backend/runtime/knowledge/app/PWD.json', 'r', encoding='utf-8') as f:
    pwd = json.load(f)
pkg_has = [r for r in pwd if isinstance(r, dict) and r.get('package_no')]
print(f"PWD APP records with package_no: {len(pkg_has)}/{len(pwd)}")
print(f"Sample:")
for r in pkg_has[:10]:
    print(f"  pkg='{r.get('package_no','')}'  src={r.get('source','?')}  agency={r.get('agency_target','?')}")

# Check: does the award batch file have a 'package_no' field stored?
print("\n\n=== Checking raw JSON structure ===")
# Check if package_no exists at the top level of records
for i, r in enumerate(records[:5]):
    print(f"Record {i}: package_no={repr(r.get('package_no', 'NOT_FOUND'))}")
