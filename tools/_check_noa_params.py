"""Check SearchNoaServlet form parameters for agency filtering."""
import httpx, re

client = httpx.Client(verify=False, timeout=30)
resp = client.get("https://www.eprocure.gov.bd/SearchNoaServlet")
html = resp.text

# Extract all form fields
selects = re.findall(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', html, re.DOTALL)
for name, inner in selects:
    opts = re.findall(r'<option[^>]*value="([^"]*)"\s*>(.*?)</option>', inner)
    if not opts:
        continue
    print(f"\n=== {name} ({len(opts)} options) ===")
    for v, t in opts[:20]:
        print(f"  {v!r:60s} {t[:40].strip()}")
    if len(opts) > 20:
        print(f"  ... and {len(opts)-20} more")

# Also look for hidden inputs
hiddens = re.findall(r'<input[^>]*type="hidden"[^>]*>', html)
print(f"\n\nHidden inputs: {len(hiddens)}")
for h in hiddens[:10]:
    print(f"  {h[:100]}")
