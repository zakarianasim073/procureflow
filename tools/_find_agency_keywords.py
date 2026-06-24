"""Find correct search keywords for each target agency on SearchNoaServlet."""
import httpx, re, time

BASE = "https://www.eprocure.gov.bd/SearchNoaServlet"
client = httpx.Client(verify=False, timeout=30, follow_redirects=True)

AGENCY_KEYWORDS = {
    "BWDB": ["BWDB", "Bangladesh Water Development Board", "Water Development Board"],
    "LGED": ["LGED", "Local Government Engineering"],
    "PWD": ["PWD", "Public Works Department"],
    "RHD": ["RHD", "Roads and Highways", "Road Transport"],
    "BBA": ["BBA", "Bangladesh Bridge Authority"],
    "EDUCATION": ["Education Engineering", "Education Directorate"],
    "BIWTA": ["BIWTA"],
    "BADC": ["BADC"],
    "DISASTER": ["Disaster", "Disaster Management"],
    "POWER": ["Power Division", "REB", "PGCB", "NESCO"],
}

def test_keyword(agency, kw):
    resp = client.post(BASE, data={"keyword": kw, "pageNo": "1", "size": "10"})
    total_m = re.search(r'id="totalPages"\s+value="(\d+)"', resp.text)
    pages = int(total_m.group(1)) if total_m else 0
    records = len(re.findall(r"bgColor", resp.text))
    first_pe = ""
    pe_m = re.search(r"bgColor-white[^>]*>.*?<td[^>]*>(.*?)</td>", resp.text, re.DOTALL)
    if pe_m:
        # Skip to the procuring_entity column (4th td)
        tds = re.findall(r"<td[^>]*>(.*?)</td>", resp.text, re.DOTALL)
        if len(tds) >= 4:
            first_pe = re.sub(r"<[^>]+>", "", tds[3]).strip()[:60]
    print(f"  {kw:40s} -> {pages:5d} pages, {records} recs, PE={first_pe}")
    return pages

for agency, kws in AGENCY_KEYWORDS.items():
    print(f"\n{agency}:")
    pages_list = []
    for kw in kws:
        p = test_keyword(agency, kw)
        pages_list.append((p, kw))
        time.sleep(0.5)  # Avoid rate limiting
    best = max(pages_list, key=lambda x: x[0])
    print(f"  BEST: {best[1]} ({best[0]} pages)")
