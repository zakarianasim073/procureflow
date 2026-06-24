"""Detailed analysis of top items"""
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
items = d.get("data", [])

# Show all items with >1Cr contribution
print("Items with SOR amount > 1 Crore:")
for item in sorted(items, key=lambda x: (x.get("qty", 0) or 0) * (x.get("sor_rate", 0) or 0), reverse=True):
    qty = item.get("qty", 0) or 0
    sr = item.get("sor_rate", 0) or 0
    amt = qty * sr
    if amt > 10000000:
        print(f"  #{item['item_no']} code={item['code']} agency={item['agency']} src={item['sor_source']}")
        print(f"    desc={item['desc'][:80]}")
        print(f"    qty={qty} rate={sr} amt={amt:,.0f} flag={item['flag']}")
        print()
