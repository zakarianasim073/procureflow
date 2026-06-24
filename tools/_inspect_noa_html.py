"""Inspect SearchNoaServlet HTML to find search form parameters."""
import httpx, re

client = httpx.Client(verify=False, timeout=30)
resp = client.get("https://www.eprocure.gov.bd/SearchNoaServlet")
html = resp.text

print("Length:", len(html))

# Look for ComboServlet or department-loading URLs
for pat in [r'"(/[^"]*(?:ComboServlet|combo|department|ministry)[^"]*)"',
            r"'(/[^']*(?:ComboServlet|combo|department|ministry)[^']*)'"]:
    matches = re.findall(pat, html, re.I)
    for m in matches[:10]:
        print("Found:", m)

# Print the form/script section
# Find everything between <form> and </form> or just the search section
idx = html.find("Search Panel")
if idx == -1:
    idx = html.find("search")
if idx > 0:
    print("\n--- HTML around search ---")
    print(html[max(0,idx-200):idx+1500])
else:
    # Just find script blocks that define combos
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    for s in scripts:
        if "ComboServlet" in s or "department" in s.lower() or "combo" in s.lower():
            print("\n--- Script with combo references ---")
            print(s[:2000])
            break
    else:
        print("\n--- First 4000 chars of HTML ---")
        print(html[:4000])
