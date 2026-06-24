"""Full crawl test — APP only, 3 agencies."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx
from crawl_egp_all import APPCrawler, write_output, AGENCIES

client = httpx.Client(verify=False, timeout=30, follow_redirects=True)
crawler = APPCrawler(client, delay=0.3)

test_agencies = ["PWD", "BWDB", "LGED"]
app_data = {}

for i, agency in enumerate(test_agencies):
    print(f"[{i+1}/{len(test_agencies)}] {agency}...")
    records = crawler.crawl_agency(agency)
    app_data[agency] = records
    print(f"  {len(records)} records")
    if records:
        r = records[0]
        print(f"  Sample: tender_id={r.get('tender_id')}, pkg={r.get('package_no')}, amt={r.get('estimated_cost_bdt')}, method={r.get('procurement_method')}")

client.close()

# Write output
output_dir = Path(__file__).resolve().parent / "crawl_output"
manifest = write_output(output_dir, app_data, {}, [], [])

print(f"\nTotal: {manifest['totals']['app']} records")
print(f"Output: {output_dir}")

# Validate: check every record has tender_id
all_recs = []
for recs in app_data.values():
    all_recs.extend(recs)
has_tid = sum(1 for r in all_recs if r.get("tender_id"))
has_pkg = sum(1 for r in all_recs if r.get("package_no"))
has_wn = sum(1 for r in all_recs if r.get("work_name"))
has_amt = sum(1 for r in all_recs if r.get("estimated_cost_bdt", 0) > 0)
print(f"Validation: {len(all_recs)} total")
print(f"  tender_id: {has_tid}")
print(f"  package_no: {has_pkg}")
print(f"  work_name: {has_wn}")
print(f"  estimated_cost_bdt > 0: {has_amt}")
