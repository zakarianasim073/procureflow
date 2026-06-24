"""Test APP Package No. search via the Advanced Search endpoint."""
import httpx, re, json, logging
logging.basicConfig(level=logging.INFO)

EGP_BASE = "https://www.eprocure.gov.bd"
client = httpx.Client(verify=False, timeout=30, follow_redirects=True)

# Known award package_nos that should exist in APP
test_pkgs = [
    "G-6/SAIDPUR UPZILLA MODEL MOSQUE",
    "ADP/NARAIL/2025-26/RFQ/W-13",
    "E-TENDER/RAJ1/SRDI VRF/2025-26",
    "DD5/SUB-DIV8/DEVELOPMENT/W3",
    "PWD/SYL/WD 38",
    "XEN/BADC/CUMILLA/B-STRONG/2025-26/R-04",
]

for pkg in test_pkgs:
    resp = client.post(
        f"{EGP_BASE}/SearchAPPServlet",
        data={
            "action": "advSearch",
            "packageNo": pkg,
            "bTypeId": "1",
            "pageNo": "1",
            "size": "50",
            "keyWord": "null",
        }
    )
    html = resp.text
    has_records = "No Records Found" not in html and len(html) > 200
    # Count rows
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    data_rows = 0
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        clean = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        clean = [c for c in clean if c]
        if len(clean) >= 5 and not re.match(r'^(sl|no|serial|s\.?\s*no)$', clean[0], re.IGNORECASE):
            data_rows += 1
    print(f"Pkg: '{pkg[:50]}...' -> Found: {has_records}, Data rows: {data_rows}")
    if data_rows > 0:
        # Show first match
        for row in rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            clean = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            clean = [c for c in clean if c]
            if len(clean) >= 5:
                print(f"  Row: {clean}")
                break
