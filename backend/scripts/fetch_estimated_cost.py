"""Fetch estimated cost from e-GP tender page"""
import httpx, re

c = httpx.Client(verify=False, follow_redirects=True)
r = c.get("https://www.eprocure.gov.bd/resources/common/ViewTender.jsp?id=1290886", timeout=30)
print(f"Status: {r.status_code}, Length: {len(r.text)}")

# Find cost-related content
for line in r.text.split("\n"):
    if re.search(r"estimat|official.?cost|Tk\.?\s*\d|budget|total.?price|Approved|Project Cost", line, re.I):
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if clean:
            print(f"FOUND: {clean}")

# Also dump the table rows that have "ff" class
print("\n=== TABLE ROWS ===")
for line in r.text.split("\n"):
    if 'class="ff"' in line or '<td' in line:
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if clean and len(clean) > 3:
            print(clean)
