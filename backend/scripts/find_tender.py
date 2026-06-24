"""Find tender 1290886 in the database"""
import sys
sys.path.insert(0, ".")
sys.path.insert(0, "app")

from app.db.database import get_sync_engine
from sqlalchemy import text

engine = get_sync_engine()
tender_id = "1290886"

with engine.connect() as conn:
    tables = conn.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
    ).fetchall()
    
    print(f"Database has {len(tables)} tables")
    
    for tbl_row in tables:
        tbl = tbl_row[0]
        cols = conn.execute(
            text(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name='{tbl}'")
        ).fetchall()
        
        for col, dtype in cols:
            c = col
            try:
                if dtype in ("bigint", "integer", "numeric"):
                    q = f"SELECT COUNT(*) FROM \"{tbl}\" WHERE CAST(\"{c}\" AS TEXT) LIKE '%{tender_id}%'"
                elif dtype in ("character varying", "text"):
                    q = f"SELECT COUNT(*) FROM \"{tbl}\" WHERE \"{c}\" LIKE '%{tender_id}%'"
                else:
                    continue
                cnt = conn.execute(text(q)).scalar()
                if cnt and cnt > 0:
                    print(f"  {tbl}.{c}: {cnt} matches")
                    # Fetch one sample
                    sample = conn.execute(
                        text(f"SELECT * FROM \"{tbl}\" WHERE \"{c}\" LIKE '%{tender_id}%' LIMIT 1")
                    ).fetchone()
                    if sample:
                        print(f"    Sample: {dict(sample)}")
            except Exception as e:
                pass

