import json
from collections import Counter
m = json.loads(open(r'D:\A1\procurementflow_final_v3\procurementflow\backend\runtime\knowledge\matches\all_matches.json').read())
strat = Counter(x.get('match_strategy','?') for x in m['matches'])
print(f"Total: {m['total']}, Matched: {m['matched']}")
print(f"Strategies: {dict(strat)}")
print()
if strat.get('package_no',0) > 0:
    for x in m['matches']:
        if x.get('match_strategy') == 'package_no':
            print(f"PKG: {x['package_no_app']} == {x['package_no_award']}")
            print(f"  Award: {x.get('award_amount_bdt',0):.0f} BDT, Est: {x.get('estimated_amount_bdt',0):.0f} BDT, NPP: {x.get('npp',0)*100:.1f}%")
            print()
# Print first match to understand structure
if len(m['matches']) > 0:
    print("First match keys:", list(m['matches'][0].keys()))
    print("First match:", json.dumps(m['matches'][0], indent=2)[:500])
