"""Fetch APP search page and find the correct form parameter names."""
import httpx, re

client = httpx.Client(verify=False, timeout=30, follow_redirects=True)

# Get the APP search page
resp = client.get("https://www.eprocure.gov.bd/resources/common/AppSearch.jsp")
html = resp.text

# Find all form inputs
inputs = re.findall(r'<input[^>]+>', html, re.DOTALL)
print("=== INPUT FIELDS ===")
for inp in inputs:
    name_m = re.search(r'name=(["\']?)([^"\'\s>]+)\1', inp)
    name = name_m.group(2) if name_m else "NO_NAME"
    type_m = re.search(r'type=(["\']?)([^"\'\s>]+)\1', inp)
    type_ = type_m.group(2) if type_m else ""
    print(f"  name={name:25s} type={type_}")

# Find selects
selects = re.findall(r'<select[^>]+>(.*?)</select>', html, re.DOTALL)
print("\n=== SELECT FIELDS ===")
for sel_html in selects[:1]:
    names = re.findall(r'name=(["\']?)([^"\'\s>]+)\1', sel_html)
    for n in names:
        print(f"  name={n[1]}")

# Find the form action
form_m = re.search(r'<form[^>]+action=(["\']?)([^"\'\s>]+)\1', html)
if form_m:
    print(f"\nForm action: {form_m.group(2)}")

# Also check if there's a separate search servlet
servlet_links = re.findall(r'(SearchAPP[^"\']+)', html)
print(f"\nServlet links: {servlet_links[:5]}")

# Look for package_no field specifically
pkg_inputs = re.findall(r'(?i)(package[^<]+)', html)
print(f"\nPackage-related HTML: {pkg_inputs[:5]}")

# Check form onchange/onclick for combos
scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
for s in scripts[:3]:
    if 'package' in s.lower():
        print(f"\nPackage-related script: {s[:500]}")
