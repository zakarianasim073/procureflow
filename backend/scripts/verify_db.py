"""Verify DB vs CSV counts"""
import sys, csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
from app.services.sor_etl import get_sor_count
from app.db.database import get_sync_engine
from sqlalchemy import text

engine = get_sync_engine()
cnt = get_sor_count()
print(f"Total sor_rates: {cnt}")

with engine.connect() as conn:
    rows = conn.execute(text("SELECT agency, COUNT(*) as cnt FROM sor_rates GROUP BY agency ORDER BY agency")).fetchall()
    for r in rows:
        print(f"  {r[0]}: {r[1]}")
    
    for agency in ("BWDB", "PWD", "LGED"):
        db_cnt = conn.execute(text(f"SELECT COUNT(*) FROM sor_rates WHERE agency='{agency}'")).scalar()
        csv_path = ROOT / "backend" / "app" / "sor" / agency.lower() / "rates.csv"
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            csv_cnt = sum(1 for _ in csv.DictReader(f))
        match = "OK" if db_cnt == csv_cnt else "MISMATCH"
        print(f"  {agency}: DB={db_cnt} CSV={csv_cnt} {match}")
