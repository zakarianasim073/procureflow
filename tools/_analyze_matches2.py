import json

with open('backend/runtime/knowledge/matches/all_matches.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

matches = data if isinstance(data, list) else data.get('matches', [])

# Show field names of first few records
print("=== First real match keys ===")
for m in matches:
    if m.get('match_type') == 'package_exact' or m.get('match_strategy') == 'package_exact':
        print(json.dumps(m, indent=2)[:2000])
        break

print("\n=== First synthetic match keys ===")
for m in matches:
    if m.get('match_type') == 'synthetic' or m.get('match_strategy') == 'synthetic':
        print(json.dumps(m, indent=2)[:2000])
        break

# Show all unique package_no values from awards that have them
print("\n=== Awards WITH package_no (synthetic) ===")
count = 0
for m in matches:
    pkg = m.get('award_package_no') or m.get('package_no') or m.get('award_package')
    mt = m.get('match_type') or m.get('match_strategy')
    if pkg and pkg != '?' and mt != 'package_exact':
        print(f"  [{mt}] pkg={pkg}  agency={m.get('agency','?')}")
        count += 1
        if count >= 20:
            break

# Check how many awards even have a package_no
has_pkg = sum(1 for m in matches if (m.get('award_package_no') or m.get('package_no') or m.get('award_package')) and (m.get('award_package_no') != '?' if m.get('award_package_no') else True))
no_pkg = sum(1 for m in matches if not (m.get('award_package_no') or m.get('package_no') or m.get('award_package')))
pkg_is_q = sum(1 for m in matches if m.get('award_package_no') == '?' or m.get('package_no') == '?')
print(f"\nAwards with package_no: {has_pkg}")
print(f"Awards without package_no field: {no_pkg}")
print(f"Awards with '?' package_no: {pkg_is_q}")
