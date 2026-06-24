import json
m = json.loads(open(r'D:\A1\procurementflow_final_v3\procurementflow\backend\runtime\knowledge\matches\all_matches.json').read())
print(f"Matches: {m['total']} total, {m['matched']} matched")
mx = [x for x in m['matches'] if x.get('match_strategy') == 'package_no']
print(f"  package_no matches: {len(mx)}")
for x in mx[:5]:
    print(f"  PKG: {x['package_no_app']} == {x['package_no_award']}")
    print(f"  Award: {x.get('award_amount_bdt',0):.0f} BDT, Est: {x.get('estimated_amount_bdt',0):.0f} BDT, NPP: {x.get('npp',0)*100:.1f}%")
    print()
# Also show unmatched counts
unmatched = [x for x in m['matches'] if x.get('match_strategy') == 'unmatched_app']
print(f"  unmatched APP: {len(unmatched)}")
unmatched_award = [x for x in m['matches'] if x.get('match_strategy') == 'unmatched_award']
print(f"  unmatched awards: {len(unmatched_award)}")
