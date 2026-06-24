"""Find the correct date parameter names for SearchNoaServlet — minimal calls."""
import httpx, re

client = httpx.Client(verify=False, timeout=30, follow_redirects=True)
BASE = "https://www.eprocure.gov.bd/SearchNoaServlet"

def test(params, label):
    resp = client.post(BASE, data={**{"keyword": "BWDB", "pageNo": "1", "size": "10"}, **params})
    total_m = re.search(r'id="totalPages"\s+value="(\d+)"', resp.text)
    pages = int(total_m.group(1)) if total_m else 0
    print(f"{label:40s} pages={pages}")
    return pages

# Baseline
p0 = test({}, "BWDB (no filter)")

# fromDate alone (DD/MM/YYYY)
p1 = test({"fromDate": "03/08/2025"}, "fromDate=03/08/2025")
p2 = test({"contractSignDateFrom": "03/08/2025"}, "contractSignDateFrom")
p3 = test({"signDateFrom": "03/08/2025"}, "signDateFrom")
p4 = test({"advertisementDateFrom": "03/08/2025"}, "advertisementDateFrom")
p5 = test({"awardDateFrom": "03/08/2025"}, "awardDateFrom")
p6 = test({"notifDateFrom": "03/08/2025"}, "notifDateFrom")
