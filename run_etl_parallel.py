"""
Parallel ETL — imports using thread pools for speed.
Usage: python run_etl_parallel.py
"""
import os, sys, json, logging
from pathlib import Path
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///D:/A1/procurementflow_final_v3/procurementflow/backend/data/procureflow_v3.db"
os.environ["SYNC_DATABASE_URL"] = "sqlite:///D:/A1/procurementflow_final_v3/procurementflow/backend/data/procureflow_v3.db"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
logging.basicConfig(level=logging.WARNING)

import asyncio, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.orm import Session as SyncSession
from app.db.database import get_sync_engine, init_db
from app.db.models import Base, Tender, Award, OpeningReport, APPRecord, NPPRecord

CRAWL = Path(__file__).parent / "backend" / "crawl_output"
KNOWLEDGE = Path(__file__).parent / "backend" / "runtime" / "knowledge"
engine = get_sync_engine()

def _safe_decimal(v, d=None):
    if v is None: return d
    try: return float(str(v))
    except: return d

def _safe_str(v, d=""):
    return str(v) if v is not None else d

def _parse_date(v):
    if not v: return None
    from datetime import datetime
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try: return datetime.strptime(str(v)[:19], fmt).date()
        except: continue
    return None

def seed_tenders():
    """Create stub Tender records from award & report tender_ids."""
    from sqlalchemy.orm import Session
    session = Session(engine)
    existing = {t[0] for t in session.query(Tender.tender_id).all()}
    tender_ids = set()

    # From award JSONs
    for fp in sorted(CRAWL.glob("Award/*.json")):
        if fp.name == "_checkpoint.json": continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else data.get("awards", data.get("data", [data]))
            if isinstance(items, dict): items = [items]
            for it in items:
                tid = str(it.get("tender_id", ""))
                if tid: tender_ids.add(tid)
        except Exception: pass

    # From opening report filenames
    for fp in sorted((CRAWL / "OpeningReport" / "JSON").glob("*.json")):
        tender_ids.add(fp.stem)

    # From opening report content
    for fp in sorted((CRAWL / "OpeningReport" / "JSON").glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else data.get("opening_reports", data.get("data", [data]))
            if isinstance(items, dict): items = [items]
            for it in items:
                tid = str(it.get("tender_id", ""))
                if tid: tender_ids.add(tid)
        except Exception: pass

    new_ids = tender_ids - existing
    count = 0
    for tid in sorted(new_ids):
        session.add(Tender(tender_id=tid, title=f"Auto-seeded (tender {tid})", source="etl_seed"))
        count += 1
        if count % 1000 == 0:
            session.flush()
            print(f"  Seeded {count}...")
    session.commit()
    print(f"Seeded {count} stub Tenders (total: {len(existing) + count})")
    session.close()
    return count

def import_awards_batch(files):
    """Import awards from JSON files."""
    from sqlalchemy.orm import Session
    session = Session(engine)
    existing = {a[0] for a in session.query(Award.tender_id).all()}
    total = 0
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else data.get("awards", data.get("data", [data]))
            if isinstance(items, dict): items = [items]
            for item in items:
                tid = str(item.get("tender_id", ""))
                if not tid or tid in existing: continue
                if not session.query(Tender).filter_by(tender_id=tid).first(): continue
                session.add(Award(
                    tender_id=tid,
                    contractor_name=_safe_str(item.get("winner") or item.get("contractor_name")),
                    winner=_safe_str(item.get("winner")),
                    company_id=_safe_str(item.get("company_id") or item.get("contractor_id")),
                    award_amount=_safe_decimal(item.get("award_amount")),
                    amount_bdt=_safe_decimal(item.get("amount_bdt")),
                    agency=_safe_str(item.get("agency")),
                    procurement_type=_safe_str(item.get("procurement_type")),
                    raw_data=item,
                    source_file=str(fp),
                ))
                existing.add(tid)
                total += 1
                if total % 2000 == 0:
                    session.flush()
            session.commit()
        except Exception as e:
            print(f"  Error in {fp.name}: {e}")
    session.close()
    return total

def import_opening_reports_batch(files):
    """Import opening reports in parallel."""
    from sqlalchemy.orm import Session
    session = Session(engine)
    existing = {r[0] for r in session.query(OpeningReport.tender_id).all()}
    total = 0
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else data.get("opening_reports", data.get("data", [data]))
            if isinstance(items, dict): items = [items]
            for item in items:
                raw_tender_id = item.get("tender_id") or fp.stem
                tid = str(raw_tender_id).strip() if raw_tender_id else ""
                if not tid or tid in existing: continue
                if not session.query(Tender).filter_by(tender_id=tid).first(): continue
                session.add(OpeningReport(
                    tender_id=tid,
                    estimated_amount_bdt=_safe_decimal(item.get("estimated_amount_bdt") or item.get("estimate_amount")),
                    pe_office=_safe_str(item.get("pe_office") or item.get("procuring_entity")),
                    zone=_safe_str(item.get("zone")),
                    package_work_name=_safe_str(item.get("package_work_name") or item.get("work_name")),
                    bidders=item.get("bidders", []),
                    winner_name=_safe_str(item.get("winner_name") or item.get("winner")),
                    winner_amount=_safe_decimal(item.get("winner_amount") or item.get("award_amount")),
                    is_archived=True,
                    raw_data=item,
                    source_json=str(fp),
                ))
                existing.add(tid)
                total += 1
                if total % 200 == 0:
                    session.flush()
            session.commit()
        except Exception as e:
            print(f"  Error in {fp.name}: {e}")
    session.close()
    return total

def import_app_batch(files):
    """Import APP records from JSON files."""
    from sqlalchemy.orm import Session
    session = Session(engine)
    existing = {a[0] for a in session.query(APPRecord.package_no).all()}
    total = 0
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else data.get("app", data.get("data", [data]))
            if isinstance(items, dict): items = [items]
            for item in items:
                if not isinstance(item, dict): continue
                pkg = str(item.get("package_no", ""))
                if not pkg or pkg in existing: continue
                session.add(APPRecord(
                    package_no=pkg,
                    tender_id=pkg,
                    work_name=_safe_str(item.get("work_name")),
                    estimated_amount_bdt=_safe_decimal(item.get("estimated_cost_bdt")),
                    procurement_type=_safe_str(item.get("category")),
                    status=_safe_str(item.get("status")),
                    raw_data=item,
                    source_file=str(fp),
                ))
                existing.add(pkg)
                total += 1
                if total % 1000 == 0:
                    session.flush()
            session.commit()
        except Exception as e:
            print(f"  Error in {fp.name}: {e}")
    session.close()
    return total

def import_npp_batch(files):
    """Import NPP records - handles float/list/dict JSON variations."""
    from sqlalchemy.orm import Session
    session = Session(engine)
    existing = {n[0] for n in session.query(NPPRecord.tender_id).all()}
    total = 0
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            
            # Handle various JSON structures:
            # - list of records: [ {...}, {...} ]
            # - single record object: { "tender_id": "...", ... }
            # - object with "npp" or "data" keys containing array: { "npp": [...] }
            # - bare float/int value (edge case): 5.0
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                if "npp" in data and isinstance(data["npp"], list):
                    items = data["npp"]
                elif "data" in data and isinstance(data["data"], list):
                    items = data["data"]
                else:
                    items = [data]
            else:
                # Bare primitive (float, int, str) - cannot extract tender_id, skip
                print(f"  Skipping {fp.name}: JSON is primitive type ({type(data).__name__}), not a record")
                continue
            
            if isinstance(items, dict):
                items = [items]
            
            for item in items:
                if not isinstance(item, dict):
                    continue
                tid = str(item.get("tender_id", ""))
                if not tid or tid in existing: continue
                est = _safe_decimal(item.get("app_estimate", item.get("estimated_amount_bdt", 0)))
                award_amt = _safe_decimal(item.get("award_amount", 0))
                npp_pct = _safe_decimal(item.get("npp", item.get("lowest_percent_below_oe", 0)))
                session.add(NPPRecord(
                    tender_id=tid,
                    estimated_amount_bdt=est,
                    lowest_bid=_safe_decimal(est * (1 - npp_pct) if est and npp_pct else 0),
                    lowest_percent_below_oe=npp_pct,
                    agency=_safe_str(item.get("agency")),
                    source_file=str(fp),
                    raw_data=item,
                ))
                existing.add(tid)
                total += 1
                if total % 500 == 0:
                    session.flush()
            session.commit()
        except Exception as e:
            print(f"  Error in {fp.name}: {e}")
    session.close()
    return total

async def main():
    print("=== Parallel ETL ===\n")

    # Create tables
    await init_db()
    print("Tables created.\n")

    # Seed tenders first (sequential, quick)
    print("--- Seeding Tenders ---")
    t0 = time.time()
    n_seeded = seed_tenders()
    print(f"Done in {time.time()-t0:.1f}s\n")

    # Collect files
    award_files = sorted((CRAWL / "Award").glob("*.json"))
    award_files = [f for f in award_files if f.name != "_checkpoint.json"]
    report_files = sorted((CRAWL / "OpeningReport" / "JSON").glob("*.json"))
    npp_files = sorted(KNOWLEDGE.rglob("npp/**/*.json"))

    # Split into batches for parallel processing
    BATCH_SIZE = 50
    award_batches = [award_files[i:i+BATCH_SIZE] for i in range(0, len(award_files), BATCH_SIZE)]
    report_batches = [report_files[i:i+BATCH_SIZE] for i in range(0, len(report_files), BATCH_SIZE)]
    npp_batches = [npp_files[i:i+BATCH_SIZE] for i in range(0, len(npp_files), BATCH_SIZE)]

    print(f"Files to process:")
    print(f"  Awards: {len(award_files)} ({len(award_batches)} batches)")
    print(f"  Opening Reports: {len(report_files)} ({len(report_batches)} batches)")
    print(f"  NPP: {len(npp_files)} ({len(npp_batches)} batches)\n")

    # Parallel import using thread pool
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = []

        print("--- Importing Awards ---")
        t0 = time.time()
        for batch in award_batches:
            futures.append(pool.submit(import_awards_batch, batch))
        award_total = sum(f.result() for f in futures)
        print(f"  Awards imported: {award_total} ({time.time()-t0:.1f}s)")
        futures.clear()

        print("--- Importing Opening Reports (parallel) ---")
        t0 = time.time()
        for batch in report_batches:
            futures.append(pool.submit(import_opening_reports_batch, batch))
        report_total = sum(f.result() for f in futures)
        print(f"  Reports imported: {report_total} ({time.time()-t0:.1f}s)")
        futures.clear()

        print("--- Importing NPP Records (parallel) ---")
        t0 = time.time()
        for batch in npp_batches:
            futures.append(pool.submit(import_npp_batch, batch))
        npp_total = sum(f.result() for f in futures)
        print(f"  NPP imported: {npp_total} ({time.time()-t0:.1f}s)")

        print("--- Importing APP Records (parallel) ---")
        t0 = time.time()
        app_files = sorted((CRAWL / "APP").glob("*.json"))
        app_files = [f for f in app_files if f.name != "_checkpoint.json"]
        app_batches = [app_files[i:i+BATCH_SIZE] for i in range(0, len(app_files), BATCH_SIZE)]
        futures.clear()
        for batch in app_batches:
            futures.append(pool.submit(import_app_batch, batch))
        app_total = sum(f.result() for f in futures)
        print(f"  APP imported: {app_total} ({time.time()-t0:.1f}s)")

    # Summary
    from sqlalchemy.orm import Session
    session = Session(engine)
    print(f"\n=== Final Summary ===")
    print(f"  Tenders: {session.query(Tender).count()}")
    print(f"  Awards: {session.query(Award).count()}")
    print(f"  Opening Reports: {session.query(OpeningReport).count()}")
    print(f"  APP Records: {session.query(APPRecord).count()}")
    print(f"  NPP Records: {session.query(NPPRecord).count()}")
    session.close()

if __name__ == "__main__":
    asyncio.run(main())
