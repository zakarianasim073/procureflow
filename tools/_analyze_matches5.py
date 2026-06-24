import json

with open('backend/runtime/knowledge/matches/all_matches.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
matches = data if isinstance(data, list) else data.get('matches', [])

real = [m for m in matches if m.get('match_strategy') == 'package_exact']

# Show ALL real matches with details
print(f"ALL {len(real)} REAL MATCHES:")
print("=" * 100)
for m in real:
    print(f"  Agency: {m['agency']:10s} | APP pkg: {m.get('package_no_app',''):55s} | Award pkg: {m.get('package_no_award',''):55s}")
    print(f"  Winner: {m['winner'][:60]}")
    print(f"  Award: {m['award_amount_bdt']:>12,.2f}  APP: {m['estimated_amount_bdt']:>12,.2f}  NPP: {m['npp']:.4f}  Disc: {m['discount_pct']:.2f}%")
    print()

# Now check: what do award package_nos look like for agencies WITH APP data?
# Compare against APP package_nos for the same agency
print("=" * 100)
print("SAMPLE COMPARISON: PWD award pkgs vs PWD APP pkgs")
print("=" * 100)

# Get PWD award package_nos
pwd_award_pkgs = set()
for m in matches:
    if m.get('agency') == 'PWD' and m.get('package_no_award'):
        pwd_award_pkgs.add(m['package_no_award'].upper().strip())

# Get PWD APP package_nos
with open('backend/runtime/knowledge/app/PWD.json', 'r', encoding='utf-8') as f:
    pwd_app = json.load(f)
pwd_app_pkgs = set()
for r in pwd_app:
    if isinstance(r, dict) and r.get('package_no'):
        p = r['package_no'].strip().upper()
        if p:
            pwd_app_pkgs.add(p)

print(f"PWD award unique package_nos: {len(pwd_award_pkgs)}")
print(f"PWD APP unique package_nos: {len(pwd_app_pkgs)}")

# Check overlap
overlap = pwd_award_pkgs & pwd_app_pkgs
print(f"Overlap: {len(overlap)}")
if overlap:
    for p in list(overlap)[:10]:
        print(f"  MATCH: {p}")

# Show award pkgs not in APP
unmatched = pwd_award_pkgs - pwd_app_pkgs
print(f"\nPWD award pkgs NOT in APP ({len(unmatched)} sample 20):")
for p in sorted(list(unmatched))[:20]:
    print(f"  '{p}'")

# Show APP pkgs not matching any award
unused = pwd_app_pkgs - pwd_award_pkgs
print(f"\nPWD APP pkgs NOT in awards ({len(unused)} sample 20):")
for p in sorted(list(unused))[:20]:
    print(f"  '{p}'")
