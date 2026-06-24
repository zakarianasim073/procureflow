import json
import re

def clean_pkg(p):
    """Clean package_no for matching."""
    p = p.strip()
    p = re.sub(r'&nbsp;', '', p)
    p = re.sub(r'&amp;', '&', p)
    p = re.sub(r'&lt;', '<', p)
    p = re.sub(r'&gt;', '>', p)
    p = re.sub(r'\s+', ' ', p).strip()
    return p

# Load all APP files and index by cleaned package_no
app_dir = 'backend/runtime/knowledge/app'
import glob as g
app_by_pkg = {}
for fp in sorted(g.glob(f'{app_dir}/*.json')):
    if fp.endswith('offices_') or fp == f'{app_dir}/dept_tree.json':
        continue
    with open(fp, 'r', encoding='utf-8') as f:
        data = json.load(f)
    records = data if isinstance(data, list) else data.get('records', data.get('data', []))
    for r in records:
        if isinstance(r, dict) and r.get('package_no'):
            pkg = clean_pkg(r['package_no']).upper()
            if pkg:
                app_by_pkg[pkg] = r

print(f"Total cleaned APP package_nos: {len(app_by_pkg)}")

# Load awards from matches (the eContracts scrape output)
with open('backend/runtime/knowledge/matches/all_matches.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
matches = data if isinstance(data, list) else data.get('matches', [])

# Check how many award package_nos would match after cleaning
match_count = 0
unmatched_samples = []
for m in matches:
    award_pkg = m.get('package_no_award', '')
    if not award_pkg:
        continue
    clean_award = clean_pkg(award_pkg).upper()
    if clean_award in app_by_pkg:
        match_count += 1

print(f"Award pkgs that WOULD match after cleaning: {match_count}/{len(matches)}")

# Show what's in app_by_pkg that matches award pkgs
# Check specific patterns
print("\n=== Checking specific patterns ===")
# Does HED-like package_no from awards exist in APP?
hed_prefixes = set()
for m in matches:
    p = m.get('package_no_award', '')
    if p.startswith('138/') or p.startswith('HED/'):
        hed_prefixes.add(p)
print(f"Award pkgs with HED/138 prefix: {len(hed_prefixes)}")
for p in sorted(list(hed_prefixes))[:10]:
    cp = clean_pkg(p).upper()
    print(f"  '{p}' -> '{cp}' in APP? {cp in app_by_pkg}")

# Check LGED-like patterns
lged_prefixes = set()
for m in matches:
    p = m.get('package_no_award', '')
    if 'LGED' in p.upper():
        lged_prefixes.add(p)
print(f"\nAward pkgs with LGED: {len(lged_prefixes)}")
for p in sorted(list(lged_prefixes))[:10]:
    cp = clean_pkg(p).upper()
    print(f"  '{p}' -> '{cp}' in APP? {cp in app_by_pkg}")

# Also check: how many award pkgs would match by tender_id?
# Build app index by tender_id
app_by_tid = {}
for r in records_list if 'records_list' in dir() else []:
    pass
# Load again
app_by_tid = {}
for fp in sorted(g.glob(f'{app_dir}/*.json')):
    if fp.endswith('offices_') or fp == f'{app_dir}/dept_tree.json':
        continue
    with open(fp, 'r', encoding='utf-8') as f:
        data = json.load(f)
    records = data if isinstance(data, list) else data.get('records', data.get('data', []))
    for r in records:
        if isinstance(r, dict) and r.get('tender_id'):
            tid = r['tender_id'].strip()
            if tid and tid.isdigit():
                app_by_tid[tid] = r

tid_match_count = 0
for m in matches:
    tid = m.get('tender_id', '')
    if tid in app_by_tid and m.get('match_strategy') != 'package_exact':
        tid_match_count += 1

print(f"\nAwards that WOULD match by tender_id (besides already matched): {tid_match_count}")
