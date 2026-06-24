import json

# Check BADC.json - what offices were crawled?
with open('backend/runtime/knowledge/app/BADC.json', 'r', encoding='utf-8') as f:
    badc = json.load(f)

# Check what offices are represented
if isinstance(badc, list):
    offices = set(r.get('office_name','') for r in badc)
    print(f"BADC APP records: {len(badc)}")
    print(f"BADC APP unique offices: {len(offices)}")
    print("Sample offices (first 20):")
    for o in sorted(list(offices))[:20]:
        print(f"  {o}")

# Check PWD.json similarly
with open('backend/runtime/knowledge/app/PWD.json', 'r', encoding='utf-8') as f:
    pwd = json.load(f)
if isinstance(pwd, list):
    offices = set(r.get('office_name','') for r in pwd)
    print(f"\nPWD APP records: {len(pwd)}")
    print(f"PWD APP unique offices: {len(offices)}")
    print("Sample offices (first 20):")
    for o in sorted(list(offices))[:20]:
        print(f"  {o}")

# Now check agencies in award data - sample synthetic records by agency
with open('backend/runtime/knowledge/matches/all_matches.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
matches = data if isinstance(data, list) else data.get('matches', [])

# Agency distribution
agency_counts = {}
for m in matches:
    a = m.get('agency','UNKNOWN')
    agency_counts[a] = agency_counts.get(a, 0) + 1
print("\nMatch agency distribution:")
for a, c in sorted(agency_counts.items(), key=lambda x: -x[1]):
    print(f"  {a}: {c}")

# Show award package_nos for a few agencies to see patterns
print("\n=== Synthetic award package_nos by agency (sample) ===")
for agency in ['PWD', 'LGED', 'BWDB', 'RHD', 'OTHER', 'EDUCATION', 'POWER', 'HEALTH']:
    pkgs = []
    for m in matches:
        if m.get('agency') == agency and m.get('package_no_award'):
            pkgs.append(m['package_no_award'])
    pkgs = list(set(pkgs))
    print(f"\n{agency} ({len(pkgs)} unique nos, sample 10):")
    for p in sorted(pkgs)[:10]:
        print(f"  {p}")
