"""Get details for tender 1290886"""
import sys, glob, os
sys.path.insert(0, ".")
sys.path.insert(0, "app")

from app.db.database import get_sync_engine
from sqlalchemy import text, inspect

engine = get_sync_engine()
tid = "1290886"

with engine.connect() as conn:
    # Check procurement_tenders
    rows = conn.execute(
        text("SELECT * FROM procurement_tenders WHERE package_no LIKE '%' || :tid || '%' LIMIT 3"),
        {"tid": tid}
    ).fetchall()
    print(f"=== procurement_tenders ({len(rows)} rows) ===")
    for row in rows:
        d = dict(row._mapping)
        for k, v in d.items():
            val = str(v)[:200] if v else "NULL"
            print(f"  {k}: {val}")
        print()

    # Check procurement_lifecycle
    rows = conn.execute(
        text("SELECT * FROM procurement_lifecycle WHERE package_no LIKE '%' || :tid || '%' LIMIT 3"),
        {"tid": tid}
    ).fetchall()
    print(f"=== procurement_lifecycle ({len(rows)} rows) ===")
    for row in rows:
        d = dict(row._mapping)
        for k, v in d.items():
            val = str(v)[:200] if v else "NULL"
            print(f"  {k}: {val}")
        print()

    # Check app_records - get columns first
    insp = inspect(engine)
    app_cols = [c["name"] for c in insp.get_columns("app_records")]
    print(f"=== app_records columns ({len(app_cols)}) ===")
    
    rows = conn.execute(
        text("SELECT * FROM app_records WHERE source_tender_id LIKE '%' || :tid || '%' LIMIT 3"),
        {"tid": tid}
    ).fetchall()
    print(f"=== app_records ({len(rows)} rows) ===")
    for row in rows:
        d = dict(row._mapping)
        for k, v in d.items():
            val = str(v)[:200] if v else "NULL"
            print(f"  {k}: {val}")
        print()
    
    # List available pipeline services 
    svc_dir = r"D:\A1\procurementflow_final_v3\procurementflow\backend\app\services"
    print(f"=== Available services ===")
    for f in sorted(glob.glob(os.path.join(svc_dir, "*.py"))):
        print(f"  {os.path.basename(f)}")
    
    print(f"\n=== Available API endpoints ===")
    api_dir = r"D:\A1\procurementflow_final_v3\procurementflow\backend\app\api"
    for f in sorted(glob.glob(os.path.join(api_dir, "**", "*.py"), recursive=True)):
        rel = os.path.relpath(f, api_dir)
        if rel.endswith(".py"):
            print(f"  api/{rel}")
