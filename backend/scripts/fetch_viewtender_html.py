"""Fetch ViewTender.jsp HTML for tender 1290886 and extract document links"""
import sys, re
sys.path.insert(0, ".")
sys.path.insert(0, "app")

from app.agents.credentials import get_credentials
from app.agents.egp_client import eGPClient, BASE_URL

TENDER_ID = "1290886"

creds = get_credentials()
client = eGPClient(email=creds.egp.email, password=creds.egp.password)
client.login()

# Fetch ViewTender.jsp
resp = client.client.get(
    f"{BASE_URL}/resources/common/ViewTender.jsp",
    params={"id": TENDER_ID, "h": "t"},
    timeout=60,
)
html = resp.text
print(f"ViewTender.jsp returned {len(html)} bytes, status={resp.status_code}")

# Save to file for analysis
with open(f"debug_viewtender_{TENDER_ID}.html", "w", encoding="utf-8") as f:
    f.write(html)

# Check for tender ID in page
if TENDER_ID in html:
    idx = html.find(TENDER_ID)
    print(f"\nTender ID found at position {idx}")

# Look for document links
doc_keywords = ["document", "download", "pdf", "boq", "nit", "tds", "notice", "bill", "form"]
for kw in doc_keywords:
    positions = [m.start() for m in re.finditer(kw, html, re.IGNORECASE)]
    if positions:
        print(f"\n'{kw}' found at {len(positions)} positions:")
        for pos in positions[:5]:
            snippet = html[max(0,pos-80):pos+80]
            print(f"  [{pos}] ...{snippet}...")

# Find all hrefs with tender-related patterns
hrefs = re.findall(r'href=["\']([^"\']*?tender[^"\']*?)["\']', html, re.IGNORECASE)
print(f"\nTender-related hrefs ({len(hrefs)}):")
for h in hrefs:
    print(f"  {h}")

# Find all onclick/link references
onclicks = re.findall(r'onclick=["\'][^"\']*?(?:location|window\.open|href)[^"\']*?["\']', html, re.IGNORECASE)
print(f"\nOnclick navigations ({len(onclicks)}):")
for o in onclicks[:10]:
    print(f"  {o[:200]}")

# Look for form/boq links specifically
boq_refs = re.findall(r'[^.]*?boq[^.]*\.', html, re.IGNORECASE)
print(f"\nBOQ references ({len(boq_refs)}):")
for b in boq_refs[:5]:
    print(f"  {b[:200]}")

# Find iframes or embed tags
iframes = re.findall(r'<iframe[^>]*src=["\']([^"\']+)["\']', html, re.IGNORECASE)
print(f"\nIframes ({len(iframes)}):")
for i in iframes:
    print(f"  {i}")

embeds = re.findall(r'<embed[^>]*src=["\']([^"\']+)["\']', html, re.IGNORECASE)
print(f"\nEmbeds ({len(embeds)}):")
for e in embeds:
    print(f"  {e}")

# Check for "View Tender / Proposal Document" section
section_start = html.find("View Tender")
if section_start >= 0:
    section = html[section_start:section_start+3000]
    print(f"\n\n'View Tender' section:")
    print(section[:2000])

client.close()
