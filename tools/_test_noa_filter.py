"""Test SearchNoaServlet with agency/department filter parameters."""
import httpx, re
from collections import Counter

client = httpx.Client(verify=False, timeout=30, follow_redirects=True)
BASE = "https://www.eprocure.gov.bd/SearchNoaServlet"

def test(params, label):
    resp = client.post(BASE, data=params)
    total_m = re.search(r'id="totalPages"\s+value="(\d+)"', resp.text)
    total_pages = int(total_m.group(1)) if total_m else 0
    records = len(re.findall(r"bgColor", resp.text))
    first_title = ""
    title_m = re.search(r"<a[^>]*>(\d+)", resp.text)
    if title_m:
        first_title = title_m.group(1)
    print(f"{label}: {resp.status_code} | {len(resp.text)}b | {records} recs | {total_pages} pages | first TID={first_title}")
    return resp

# Baseline (no filter)
test({"keyword": "", "pageNo": "1", "size": "10"}, "Unfiltered")

# Try keyword = BWDB
test({"keyword": "BWDB", "pageNo": "1", "size": "10"}, "keyword=BWDB")

# Try departmentId
test({"keyword": "", "pageNo": "1", "size": "10", "departmentId": "7"}, "deptId=7")

# Try department  
test({"keyword": "", "pageNo": "1", "size": "10", "department": "7"}, "department=7")

# Try agency
test({"keyword": "", "pageNo": "1", "size": "10", "agency": "7"}, "agency=7")

# Try with date range (from Aug 2025)
test({"keyword": "", "pageNo": "1", "size": "10", "contractSignDateFrom": "03/08/2025"}, "dateFrom=Aug2025")

# Try keyWord=Bangladesh Water Development Board
test({"keyword": "Bangladesh Water Development Board", "pageNo": "1", "size": "10"}, "keyword=BWDB full")

# Check the first page HTML to understand what params work
print("\n--- Unfiltered HTML (first 1000) ---")
resp = test({"keyword": "", "pageNo": "1", "size": "50"}, "for HTML check")
# Find any hidden fields
hiddens = re.findall(r'<input[^>]+type=[\"\']hidden[\"\'][^>]*>', resp.text)
print(f"Hidden inputs: {len(hiddens)}")
for h in hiddens[:5]:
    print(f"  {h}")
# Find total records
total_rec = re.search(r'Total Records\s*:\s*(\d+)', resp.text)
if total_rec:
    print(f"Total Records: {total_rec.group(1)}")
# Also check the select/dropdown for department
dept_select = re.search(r'<select[^>]*name=["\'](?:department|agency|ministry)["\'][^>]*>', resp.text, re.I)
if dept_select:
    print(f"Found select: {dept_select.group()}")
