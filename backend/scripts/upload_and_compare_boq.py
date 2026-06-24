"""Upload BOQ PDF and run SOR comparison via API"""
import httpx, json, sys, time

api = "http://localhost:8000/api"

# Step 1: Check server is up
try:
    resp = httpx.get(f"{api}/health", timeout=5)
    print(f"Server health: {resp.status_code}")
except Exception as e:
    print(f"Server not reachable: {e}")
    sys.exit(1)

# Step 2: Upload BOQ file
print("\\n=== Step 1: Upload BOQ PDF ===")
boq_path = "uploads/1290886/docs/Section6_Bill of Quantities/Section6_Bill of Quantities.pdf"
with open(boq_path, "rb") as f:
    resp = httpx.post(
        f"{api}/boq/upload",
        files={"file": ("boq.pdf", f, "application/pdf")},
        timeout=60,
    )
print(f"Status: {resp.status_code}")
result = resp.json()
print(json.dumps(result, indent=2))

file_id = result.get("file_id", "")
if not file_id:
    print("\\nERROR: No file_id returned")
    sys.exit(1)

print(f"\\nFile ID: {file_id}")

# Step 3: Compare with SOR (Zone B = Chattogram)
print("\\n=== Step 2: Run BOQ Comparison ===")
resp2 = httpx.post(
    f"{api}/boq/compare",
    data={
        "boq_file_id": file_id,
        "sor_agency": "BWDB",
        "zone": "B",
        "tender_info": json.dumps({
            "tender_id": "1290886",
            "title": "Construction of Regulator (3-Vent: 1.50m x 1.80m)",
            "entity": "BWDB",
            "location": "Cox's Bazar",
        }),
    },
    timeout=300,
)
print(f"Status: {resp2.status_code}")

try:
    d = resp2.json()
except Exception as e:
    print(f"JSON parse error: {e}")
    print(resp2.text[:1000])
    sys.exit(1)

if resp2.status_code == 200:
    print(f"\\n=== BOQ Comparison Results ===")
    print(f"Total items: {d.get('total_items', '?')}")
    print(f"Mismatches: {d.get('mismatches', '?')}")
    print(f"Variances: {d.get('variances', '?')}")
    print(f"Matches: {d.get('matches', '?')}")
    print(f"Below SOR: {d.get('below_sor', '?')}")
    print(f"SOR Agency: {d.get('sor_agency', '?')}")
    print(f"Zone: {d.get('zone', '?')}")

    summary = d.get("summary", {})
    if summary:
        print(f"\\nSummary:")
        print(f"  Total SOR: {summary.get('total_sor', 0):,.2f}")
        print(f"  Total Quoted: {summary.get('total_quoted', 0):,.2f}")
        print(f"  Discount: {summary.get('discount_pct', 0):.2f}%")

    excel_path = d.get("excel_path", "")
    docx_path = d.get("docx_path", "")
    if excel_path:
        print(f"\\nExcel report: {excel_path}")
    if docx_path:
        print(f"DOCX report: {docx_path}")

    # Show first 5 items
    print(f"\\n=== First 5 BOQ Items ===")
    data_items = d.get("data", [])
    for item in data_items[:5]:
        print(f"  {item.get('item_no','')}. {item.get('code','')} | {item.get('desc','')[:60]} | "
              f"Qty={item.get('qty','')} | Rate={item.get('rate','')} | "
              f"SOR={item.get('sor_rate','')} | {item.get('flag','')}")
    if len(data_items) > 5:
        print(f"  ... and {len(data_items) - 5} more items")

    # Print full result
    print(f"\\n=== Full JSON ===")
    print(json.dumps(d, indent=2, default=str))
else:
    print(f"Error: {resp2.text[:2000]}")
