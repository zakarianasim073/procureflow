"""Upload BOQ and compare - v2 with multi-agency matching"""
import httpx, json, sys

api = "http://localhost:8000/api"

# Step 1: Upload
print("=== Step 1: Upload BOQ PDF ===")
boq_path = "uploads/1290886/docs/Section6_Bill of Quantities/Section6_Bill of Quantities.pdf"
with open(boq_path, "rb") as f:
    resp = httpx.post(f"{api}/boq/upload", files={"file": ("boq.pdf", f, "application/pdf")}, timeout=60)
print(f"Upload status: {resp.status_code}")
upload_data = resp.json()
file_id = upload_data.get("file_id", "")
print(f"File ID: {file_id}")

if not file_id:
    sys.exit(1)

# Step 2: Compare (multi-agency - will try BWDB, PWD, LGED for each item)
print("\n=== Step 2: Run BOQ Comparison (multi-agency) ===")
resp2 = httpx.post(
    f"{api}/boq/compare",
    data={
        "boq_file_id": file_id,
        "sor_agency": "BWDB",  # primary agency, but backend now tries all 3
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
print(f"Compare status: {resp2.status_code}")

d = resp2.json()
if resp2.status_code == 200:
    print(f"\n=== Results ===")
    print(f"Total items: {d.get('total_items', 0)}")
    print(f"Matches: {d.get('matches', 0)}")
    print(f"Variances: {d.get('variances', 0)}")
    print(f"Mismatches: {d.get('mismatches', 0)}")
    print(f"Below SOR: {d.get('below_sor', 0)}")
    print(f"SOR Missing: {sum(1 for x in d.get('data',[]) if x.get('flag')=='SOR MISSING')}")
    print(f"Rate Missing: {sum(1 for x in d.get('data',[]) if x.get('flag')=='RATE MISSING')}")
    
    summary = d.get("summary", {})
    print(f"\nSummary:")
    print(f"  Total SOR value: {summary.get('total_sor', 0):,.2f}")
    print(f"  Total Quoted: {summary.get('total_quoted', 0):,.2f}")
    print(f"  Savings: {summary.get('total_sor', 0) - summary.get('total_quoted', 0):,.2f}")
    print(f"  Discount: {summary.get('discount_pct', 0)*100:.2f}%")
    
    # Show items with SOR matches
    data_items = d.get("data", [])
    matched = [x for x in data_items if x.get('sor_rate') is not None]
    print(f"\n=== Items With SOR Match ({len(matched)}/{len(data_items)}) ===")
    for item in matched:
        print(f"  #{item['item_no']:>3} {item.get('code',''):15} {item.get('agency',''):5} {item.get('flag',''):12} Rate={item.get('rate','?'):>8} SOR={item.get('sor_rate','?'):>8} Qty={item.get('qty',''):>8}")
    
    missing = [x for x in data_items if x.get('sor_rate') is None]
    if missing:
        print(f"\n=== Items Without SOR Match ({len(missing)}) ===")
        for item in missing:
            print(f"  #{item['item_no']:>3} {item.get('code',''):15} {item.get('agency',''):5} {item.get('flag',''):12} {item.get('desc','')[:60]}")
    
    print(f"\nExcel report: {d.get('excel_path','')}")
else:
    print(f"Error: {json.dumps(d, indent=2)[:2000]}")
