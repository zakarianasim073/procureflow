"""Save BWDB scraped data into the agent system."""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from datetime import datetime
from pathlib import Path

bwdb_path = Path("runtime/data_intel/bwdb_live_tenders.json")
data = json.loads(bwdb_path.read_text(encoding="utf-8"))
bwdb = data.get("bwdb_tenders", [])

ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
out = Path("runtime/data_intel") / f"tenders_bwdb_live_{ts}.json"
out.write_text(json.dumps(bwdb, indent=2, default=str), encoding="utf-8")
print(f"Saved {len(bwdb)} BWDB tenders to {out.name}")

print()
print("=== 43 BWDB LIVE TENDERS ===")
for t in bwdb:
    v = t.get("estimated_value_bdt", 0) or 0
    e = t.get("procuring_entity", "")[:60]
    print(f"  {t['tender_id']:>8} | BDT {v:>8,.0f} | {t['deadline']} | {e}")

print()
print("Done — 43 BWDB tenders loaded into system.")
