import json

with open('backend/runtime/knowledge/matches/all_matches.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
matches = data if isinstance(data, list) else data.get('matches', [])

# Count unique award package_nos vs synthetic
award_pkgs = set()
real_award_pkgs = set()
synthetic_pkgs = set()

for m in matches:
    ap = m.get('package_no_award', '')
    if ap:
        award_pkgs.add(ap)
        if m.get('match_strategy') == 'package_exact':
            real_award_pkgs.add(ap)
        else:
            synthetic_pkgs.add(ap)

print(f"Total matches: {len(matches)}")
print(f"Unique award package_nos: {len(award_pkgs)}")
print(f"Unique real match package_nos: {len(real_award_pkgs)}")
print(f"Unique synthetic package_nos: {len(synthetic_pkgs)}")
print()

# Show sample award package_nos
print("=== Sample award package_nos (REAL matches) ===")
for p in sorted(list(real_award_pkgs))[:30]:
    print(f"  {p}")

print("\n=== Sample award package_nos (SYNTHETIC) ===")
# Group by prefix patterns
prefixes = {}
for p in list(synthetic_pkgs)[:1000]:
    prefix = p.split('/')[0] if '/' in p else p[:20]
    prefixes[prefix] = prefixes.get(prefix, 0) + 1

print("Top prefixes among synthetic package_nos:")
for p, c in sorted(prefixes.items(), key=lambda x: -x[1])[:30]:
    print(f"  {p}: {c}")

# Also check what APP data exists for BADC
with open('backend/runtime/knowledge/app/BADC.json', 'r', encoding='utf-8') as f:
    badc = json.load(f)
badc_pkgs = set(r.get('package_no','') for r in badc if isinstance(r, dict))
print(f"\nBADC APP unique package_nos: {len(badc_pkgs)}")
print("Sample BADC APP package_nos (first 30):")
for p in sorted([p for p in badc_pkgs if p])[:30]:
    print(f"  {p}")

# Check intersection
bd = set(p.strip().lower() for p in badc_pkgs if p)
aw = set(p.strip().lower() for p in synthetic_pkgs if p)
print(f"\nNormalized BADC APP pkg count: {len(bd)}")
print(f"Normalized synthetic award pkg count: {len(aw)}")
common = bd & aw
print(f"Common (would-be matches): {len(common)}")
if common:
    print("Sample common:")
    for p in list(common)[:10]:
        print(f"  {p}")
