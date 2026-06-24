"""Investigate BOQ vs APP deviation"""
import httpx, json, sys, os

# 1. Get BOQ comparison details
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

# 2. Show all BOQ items with their rates and amounts
items = d.get("data", [])
print(f"\n=== ALL {len(items)} BOQ ITEMS ===")
total_qty = 0
total_sor_amt = 0
total_rate = 0
for item in items:
    qty = item.get("qty", 0) or 0
    rate = item.get("rate", 0) or 0
    sor_rate = item.get("sor_rate", 0) or 0
    sor_amt = qty * sor_rate
    quoted_amt = qty * rate
    total_qty += qty
    total_sor_amt += sor_amt
    total_rate += rate
    flag = item.get("flag", "")
    if sor_amt > 10000000 or rate > 10000000:
        print(f"  HIGH: #{item['item_no']} {item['code']} {item['desc'][:50]} | qty={qty} | rate={rate} | sor_rate={sor_rate} | sor_amt={sor_amt:,.0f} | flag={flag}")

print(f"\nSummary: total_qty={total_qty}, total_sor_amt={total_sor_amt:,.0f}, total_rate_sum={total_rate:,.0f}")

# 3. Check summary
print(f"\nSummary from API:")
print(json.dumps(d.get("summary", {}), indent=2, default=str))

# 4. Check all APP records for Ban-61
sys.path.insert(0, r"D:\A1\procurementflow_final_v3\procurementflow\backend")
os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:procurementflow@localhost:5432/procurementflow"

from sqlalchemy import create_engine, text
engine = create_engine("postgresql://postgres:procurementflow@localhost:5432/procurementflow")
with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT id, source_tender_id, procurement_tender_id, estimated_cost_bdt, title, app_code, financial_year
        FROM app_records
        WHERE title LIKE '%Ban-61%' OR title LIKE '%Kumuria%' OR title LIKE '%1290886%'
        OR source_tender_id = '1290886'
        ORDER BY created_at DESC
    """)).fetchall()
    print(f"\n=== APP Records for Ban-61/1290886 ({len(rows)} found) ===")
    for r in rows:
        print(f"  id={r[0][:8]}... source_tender_id={r[1]} procurement_tender_id={r[2][:8]}... cost={r[3]:,.0f} title={r[4][:60]} app_code={r[5]} fy={r[6]}")

engine.dispose()
