import json
import sys
sys.path.insert(0, "backend")
from app.services.contractor_dna_service import get_contractor_stats, load_contractors

stats = get_contractor_stats()
print(f"Total contractors: {stats['total_contractors']}")
print(f"Total awards covered: {stats['total_awards_covered']}")
print(f"Total amount: BDT {stats['total_amount_bdt']:,.2f}")
print(f"Avg discount: {stats['avg_discount_percent']}%")
print()

print("Top by wins:")
for c in stats["top_by_wins"]:
    print(f"  {c['name'][:50]:50s} {c['wins']:>3} wins  BDT {c['amount']:>10,.2f}  ({c['top_agency']})")

print()
print("Top by amount:")
for c in stats["top_by_amount"]:
    print(f"  {c['name'][:50]:50s} BDT {c['amount']:>12,.2f}  ({c['wins']} wins, {c['top_agency']})")

# Search BWDB contractors
print()
bwdb_contractors = [c for c in load_contractors() if "BWDB" in c.get("agencies", {})]
print(f"BWDB contractors: {len(bwdb_contractors)}")
bwdb_sorted = sorted(bwdb_contractors, key=lambda x: x.get("total_wins", 0), reverse=True)
for c in bwdb_sorted[:10]:
    bwdb_info = c.get("agencies", {}).get("BWDB", {})
    print(f"  {c['contractor_name'][:50]:50s} {c['total_wins']:>3} total wins  BDT {c['total_amount_bdt']:>10,.2f}  BWDB wins={bwdb_info.get('wins',0)}")
