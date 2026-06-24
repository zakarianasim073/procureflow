"""Test APP Package No. search with various parameter combinations."""
import httpx, re, json

client = httpx.Client(verify=False, timeout=30, follow_redirects=True)
EGP_BASE = "https://www.eprocure.gov.bd"

# Try different parameter combinations for a known matching package
test_pkg = "G-6/SAIDPUR UPZILLA MODEL MOSQUE"
test_pkg2 = "G-6/Saidpur Upzilla Model Mosque"

combos = [
    {"action": "advSearch", "keyWord": test_pkg, "pageNo": "1", "size": "50"},
    {"action": "advSearch", "packageNo": test_pkg, "pageNo": "1", "size": "50"},
    {"action": "advSearch", "packageNo": test_pkg, "bTypeId": "1", "pageNo": "1", "size": "50", "keyWord": "null"},
    {"action": "advSearch", "packageNo": test_pkg2, "bTypeId": "1", "pageNo": "1", "size": "50", "keyWord": "null"},
    {"action": "advSearch", "keyWord": test_pkg, "bTypeId": "1", "pageNo": "1", "size": "50"},
    {"action": "packageSearch", "packageNo": test_pkg, "pageNo": "1", "size": "50"},
]

for i, data in enumerate(combos):
    try:
        resp = client.post(f"{EGP_BASE}/SearchAPPServlet", data=data)
        html = resp.text
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
        data_rows = 0
        for row in rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            clean = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            clean = [c for c in clean if c]
            if len(clean) >= 5 and not re.match(r'^(sl|no|serial|s\.?\s*no)$', clean[0], re.IGNORECASE):
                data_rows += 1
        print(f"Combo {i}: {list(data.keys())} -> Rows: {data_rows}, 'No Records': {'No Records Found' in html}")
        if data_rows > 0:
            for row in rows:
                cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                clean = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
                clean = [c for c in clean if c]
                if len(clean) >= 5:
                    print(f"  First row: {clean}")
                    break
    except Exception as e:
        print(f"Combo {i}: Error - {e}")
