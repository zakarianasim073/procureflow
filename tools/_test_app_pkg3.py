"""Test APP search with full parameter set and check response."""
import httpx, re

client = httpx.Client(verify=False, timeout=30, follow_redirects=True)
EGP_BASE = "https://www.eprocure.gov.bd"

# Try with full parameter set like the form would send
# Known good office-based search params + packageNo
params_list = [
    # Simple packageNo search
    {"action": "advSearch", "packageNo": "G-6/Saidpur Upzilla Model Mosque", "pageNo": "1", "size": "50"},
    # packageNo + bTypeId
    {"action": "advSearch", "packageNo": "G-6/Saidpur Upzilla Model Mosque", "bTypeId": "1", "pageNo": "1", "size": "50", "keyWord": "null"},
    # Try without bTypeId but with office
    {"action": "advSearch", "packageNo": "G-6/Saidpur Upzilla Model Mosque", "office": "1", "pageNo": "1", "size": "50"},
    # Try keyword with exact package_no in quotes
    {"action": "advSearch", "keyWord": '"G-6/Saidpur Upzilla Model Mosque"', "pageNo": "1", "size": "50"},
    # Try with office=null 
    {"action": "advSearch", "packageNo": "G-6/Saidpur Upzilla Model Mosque", "bTypeId": "1", "office": "", "pageNo": "1", "size": "50", "keyWord": "null"},
    # The original keyword approach that DOES work for office-based
    {"action": "advSearch", "keyWord": "G-6/Saidpur Upzilla Model Mosque", "pageNo": "1", "size": "50", "bTypeId": "1"},
    # Try exact package search endpoint
    {"action": "packageSearch", "packageNo": "G-6/Saidpur Upzilla Model Mosque", "bTypeId": "1", "pageNo": "1", "size": "50"},
]

# First confirm office-based search still works for this package
# (from our previous PWD crawl, this package exists in PWD APP data)
with open('backend/runtime/knowledge/app/PWD.json', 'r', encoding='utf-8') as f:
    import json
    pwd = json.load(f)

match = None
for r in pwd:
    if isinstance(r, dict) and 'Saidpur' in r.get('package_no', ''):
        match = r
        break

if match:
    print(f"Found in PWD APP: pkg={match.get('package_no')} office_id={match.get('_office_id')} office_name={match.get('_office_name')}")
    # Try searching by that specific office
    office_id = match.get('_office_id')
    if office_id:
        resp = client.post(f"{EGP_BASE}/SearchAPPServlet", data={
            "action": "advSearch", "office": str(office_id), "bTypeId": "1", "pageNo": "1", "size": "50", "keyWord": "null"
        })
        html = resp.text
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
        data_rows = 0
        for row in rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            clean = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            clean = [c for c in clean if c]
            if len(clean) >= 5:
                data_rows += 1
        print(f"Office {office_id} search: {data_rows} rows")

print("\n=== Testing all param combos ===")
for i, data in enumerate(params_list):
    try:
        resp = client.post(f"{EGP_BASE}/SearchAPPServlet", data=data)
        html = resp.text
        has_records = "No Records Found" not in html and len(html) > 200
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
        data_rows = 0
        for row in rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            clean = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            clean = [c for c in clean if c]
            if len(clean) >= 5 and not re.match(r'^(sl|no|serial)$', clean[0], re.IGNORECASE):
                data_rows += 1
        print(f"Combo {i}: rows={data_rows} has_records={has_records}")
    except Exception as e:
        print(f"Combo {i}: ERROR {e}")
