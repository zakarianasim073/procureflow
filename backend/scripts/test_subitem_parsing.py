"""Test BOQ parsing with subitem fix"""
import httpx, json

resp = httpx.post(
    "http://localhost:8000/api/boq/compare",
    data={
        "boq_file_id": "57c20c63",
        "sor_agency": "BWDB",
        "zone": "B",
        "tender_info": json.dumps({
            "tender_id": "1290886",
            "title": "Ban-61/2025-26, Construction of Regulator",
            "entity": "Cox's Bazar WD Division 2",
            "location": "Pekua, Coxsbazar",
        }),
    },
    timeout=60,
)
d = resp.json()
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    items = d.get("data", [])
    summary = d.get("summary", {})
    print(f"Items: {len(items)}")
    print(f"Total SOR: {summary.get('total_sor', 0):,.2f}")
    print(f"Total Quoted: {summary.get('total_quoted', 0):,.2f}")
    print(f"APP Estimate: 151,000,000.00")
    dev = summary.get('total_sor', 0) - 151000000
    dev_pct = (dev / 151000000) * 100
    print(f"Deviation: {dev:,.2f} ({dev_pct:.1f}%)")
    
    # Show items with highest SOR amount
    print("\nTop 10 items by SOR amount:")
    sorted_items = sorted(items, key=lambda x: (x.get("qty", 0) or 0) * (x.get("sor_rate", 0) or 0), reverse=True)
    for item in sorted_items[:10]:
        qty = item.get("qty", 0) or 0
        sr = item.get("sor_rate", 0) or 0
        amt = qty * sr
        print(f"  #{item['item_no']} code={item['code']} desc={item['desc'][:50]} qty={qty} rate={sr} amt={amt:,.0f}")
    
    # Show subitem codes detected
    subitems = [i for i in items if i.get("code", "").endswith(("10", "20", "30", "40", "45", "50", "90")) and "-" in i.get("code", "")]
    print(f"\nSub-item codes detected: {len(subitems)}")
    for si in subitems[:5]:
        print(f"  {si['code']}: {si['desc'][:60]}")
    
    # Items with quantity=0 (misparsed)
    zero_qty = [i for i in items if (i.get("qty") or 0) == 0]
    print(f"\nItems with qty=0: {len(zero_qty)}")
else:
    print(resp.text[:1000])
