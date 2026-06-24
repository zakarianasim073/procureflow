import json

with open('backend/runtime/knowledge/matches/all_matches.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

matches = data if isinstance(data, list) else data.get('matches', [])

real = [m for m in matches if m.get('match_type') == 'package_exact' or m.get('match_strategy') == 'package_exact']
synth = [m for m in matches if m.get('match_type') == 'synthetic' or m.get('match_strategy') == 'synthetic']

print(f'Total matches: {len(matches)}')
print(f'Real (package_exact): {len(real)}')
print(f'Synthetic: {len(synth)}')
print()

if real:
    print('=== REAL MATCHES (package_exact) ===')
    for m in real[:30]:
        print(f"  APP pkg: {m.get('app_package_no','?')}  |  Award pkg: {m.get('award_package_no','?')}  |  Agency: {m.get('agency','?')}")

print()
print('=== SYNTHETIC MATCHES (sample 30) ===')
for m in synth[:30]:
    print(f"  Award pkg: {m.get('award_package_no','?')}  |  Agency: {m.get('agency','?')}")
