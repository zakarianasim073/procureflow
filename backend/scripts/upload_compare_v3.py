"""Upload BOQ, compare with per-agency zone support"""
import httpx, json, sys, os

api = "http://localhost:8000/api"
boq_path = "uploads/1290886/docs/Section6_Bill of Quantities/Section6_Bill of Quantities.pdf"

# Upload
print("=== Upload ===")
with open(boq_path, "rb") as f:
    resp = httpx.post(f"{api}/boq/upload", files={"file": ("boq.pdf", f, "application/pdf")}, timeout=60)
upload_data = resp.json()
file_id = upload_data.get("file_id", "")
print(f"File ID: {file_id}")

# Compare with per-agency zone
# Cox's Bazar = Chattogram = Zone B for all agencies
# But if district were Rajshahi: BWDB=B, PWD=D, LGED=C
zone_config = json.dumps({"BWDB": "B", "PWD": "B", "LGED": "B"})
print(f"\n=== Compare (zone={zone_config}) ===")
resp2 = httpx.post(
    f"{api}/boq/compare",
    data={
        "boq_file_id": file_id,
        "sor_agency": "BWDB",
        "zone": zone_config,
        "tender_info": json.dumps({
            "tender_id": "1290886",
            "title": "Construction of Regulator (3-Vent: 1.50m x 1.80m)",
            "entity": "BWDB",
            "location": "Cox's Bazar",
        }),
    },
    timeout=300,
)
d = resp2.json()
print(f"Status: {resp2.status_code}")

if resp2.status_code == 200:
    items = d.get("data", [])
    matched = [x for x in items if x.get('sor_rate') is not None]
    missing = [x for x in items if x.get('sor_rate') is None]
    
    print(f"\nItems: {len(items)} total, {len(matched)} matched, {len(missing)} missing")
    print(f"  Matches: {d.get('matches')}, Variances: {d.get('variances')}")
    print(f"  Below SOR: {d.get('below_sor')}, SOR Missing: {len([x for x in items if x.get('flag')=='SOR MISSING'])}")
    
    print(f"\nItems by agency:")
    by_agency = {}
    for item in items:
        a = item.get('agency', '?')
        by_agency[a] = by_agency.get(a, 0) + 1
    for a, c in sorted(by_agency.items()):
        print(f"  {a}: {c}")
    
    print(f"\nFirst 10 items:")
    for item in items[:10]:
        print(f"  #{item['item_no']:>3} {item.get('code',''):15} {item.get('agency',''):5} "
              f"qty={item.get('qty',''):>8} rate={item.get('rate','?'):>8} "
              f"sor={item.get('sor_rate','?'):>8} {item.get('flag','')}")
    
    # Check report files
    excel = d.get('excel_path', '')
    docx = d.get('docx_path', '')
    if excel and os.path.exists(excel):
        print(f"\nExcel report: {excel} ({os.path.getsize(excel):,} bytes)")
    if docx and os.path.exists(docx):
        print(f"DOCX report: {docx} ({os.path.getsize(docx):,} bytes)")
else:
    print(f"Error: {json.dumps(d, indent=2)[:2000]}")
