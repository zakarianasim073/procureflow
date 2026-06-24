import json
m = json.loads(open(r'D:\A1\procurementflow_final_v3\procurementflow\backend\runtime\knowledge\matches\all_matches.json').read())
for x in m['matches']:
    if x.get('match_strategy') == 'package_exact':
        print(json.dumps(x, indent=2))
        break
