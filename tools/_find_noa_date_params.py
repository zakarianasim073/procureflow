"""Find the correct date parameter names for SearchNoaServlet."""
import httpx, re

client = httpx.Client(verify=False, timeout=30, follow_redirects=True)
BASE = "https://www.eprocure.gov.bd/SearchNoaServlet"

def test_date(params, label):
    resp = client.post(BASE, data={**{"keyword": "BWDB", "pageNo": "1", "size": "10"}, **params})
    total_m = re.search(r'id="totalPages"\s+value="(\d+)"', resp.text)
    total_pages = int(total_m.group(1)) if total_m else 0
    first_tid = ""
    m = re.search(r"<a[^>]*>(\d+)", resp.text)
    if m:
        first_tid = m.group(1)
    print(f"{label:40s} pages={total_pages:5d} firstTID={first_tid}")
    return total_pages

base = test_date({}, "BWDB (no date)")

# Try various date parameter names
date_params = [
    "fromDate", "toDate", "dateFrom", "dateTo",
    "contractSignDateFrom", "contractSignDateTo",
    "signDateFrom", "signDateTo",
    "awardDateFrom", "awardDateTo",
    "contractFrom", "contractTo",
    "notifDateFrom", "notifDateTo",
]

for param in date_params:
    test_date({param: "03/08/2025"}, f"{param}=03/08/2025")

# Try two-param ranges
test_date({"fromDate": "03/08/2025", "toDate": "11/06/2026"}, "from+to dates")
test_date({"contractSignDateFrom": "03/08/2025", "contractSignDateTo": "11/06/2026"}, "contractSignDate from+to")

# Try date in different formats
test_date({"fromDate": "2025-08-03"}, "fromDate=2025-08-03")
test_date({"fromDate": "08/03/2025"}, "fromDate=08/03/2025")
