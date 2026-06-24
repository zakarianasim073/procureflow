"""
ETL Runner — imports existing crawl_output data into new SQLAlchemy tables.
Usage: python run_etl.py
Seeds Tender stub records from Award and OpeningReport tender_ids automatically.
"""
import os, sys, json, logging
from pathlib import Path
# Force SQLite for dev (override .env which has DATABASE_URL=postgresql)
_DB = os.path.join(os.path.dirname(__file__), 'backend', 'data', 'procureflow_v3.db')
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB}"
os.environ["SYNC_DATABASE_URL"] = f"sqlite:///{_DB}"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
logging.basicConfig(level=logging.INFO)

import asyncio
from pathlib import Path
from app.db.database import init_db, get_sync_session
from app.db.etl import run_full_etl, import_award_json, import_opening_report_json, import_app_records

CRAWL = Path(__file__).parent / "backend" / "crawl_output"
KNOWLEDGE = Path(__file__).parent / "backend" / "runtime" / "knowledge"

def seed_tenders_from_awards_and_reports(session):
    """Create stub Tender records for tender_ids found in awards & report filenames."""
    from app.db.models import Tender
    existing = {t.tender_id for t in session.query(Tender.tender_id).all()}
    tender_ids = set()

    # Extract from award JSONs
    award_dir = CRAWL / "Award"
    if award_dir.exists():
        for fp in sorted(award_dir.glob("*.json")):
            if fp.name == "_checkpoint.json":
                continue
            try:
                with open(str(fp), encoding="utf-8") as f:
                    data = json.load(f)
                items = data if isinstance(data, list) else data.get("awards", data.get("data", [data]))
                if isinstance(items, dict):
                    items = [items]
                for item in items:
                    if isinstance(item, dict):
                        tid = str(item.get("tender_id", ""))
                        if tid:
                            tender_ids.add(tid)
            except Exception as e:
                print(f"  Warning: could not parse {fp.name}: {e}")

    # Extract from opening report filenames
    report_json_dir = CRAWL / "OpeningReport" / "JSON"
    if report_json_dir.exists():
        for fp in sorted(report_json_dir.glob("*.json")):
            tid = fp.stem
            if tid:
                tender_ids.add(tid)

    # Also extract from opening report JSON content
    if report_json_dir.exists():
        for fp in sorted(report_json_dir.glob("*.json")):
            try:
                with open(str(fp), encoding="utf-8") as f:
                    data = json.load(f)
                items = data if isinstance(data, list) else data.get("opening_reports", data.get("data", [data]))
                if isinstance(items, dict):
                    items = [items]
                for item in items:
                    if isinstance(item, dict):
                        tid = str(item.get("tender_id", ""))
                        if tid:
                            tender_ids.add(tid)
            except Exception:
                pass

    # Create stubs for missing tender_ids
    new_ids = tender_ids - existing
    count = 0
    for tid in sorted(new_ids):
        stub = Tender(tender_id=tid, title=f"Auto-seeded from ETL (tender {tid})", source="egp_etl_seed")
        session.add(stub)
        count += 1
        if count % 500 == 0:
            session.flush()
    session.commit()
    print(f"  Seeded {count} stub Tender records (total in DB: {len(existing) + count})")
    return count

async def main():
    # 1. Create tables
    print("=== Creating tables ===")
    await init_db()
    print("Tables created.")

    # 2. Run ETL (runtime/knowledge path for tenders/awards/opening_reports)
    session = get_sync_session()
    try:
        # The ETL's run_full_etl looks for:
        #   knowledge/tenders/*.json  → import_tender_json
        #   knowledge/awards/*.json   → import_award_json
        #   knowledge/opening_reports/*.json → import_opening_report_json
        # Our data is in different paths, so we call importers directly.

        # 2a. Import tenders from runtime/knowledge/tenders/
        tender_dir = KNOWLEDGE / "tenders"
        if tender_dir.exists():
            from app.db.etl import import_tender_json
            for fp in sorted(tender_dir.glob("*.json")):
                c = import_tender_json(str(fp), session)
                print(f"  Tenders from {fp.name}: {c}")

        # 2b. Seed stub Tender records from Award & OpeningReport tender_ids
        print("\n--- Seeding stub Tender records ---")
        n_seeded = seed_tenders_from_awards_and_reports(session)

        # 2c. Import awards from crawl_output/Award/
        award_dir = CRAWL / "Award"
        if award_dir.exists():
            for fp in sorted(award_dir.glob("*.json")):
                c = import_award_json(str(fp), session)
                print(f"  Awards from {fp.name}: {c}")

        # 2c. Import opening reports from crawl_output/OpeningReport/JSON/
        report_json_dir = CRAWL / "OpeningReport" / "JSON"
        if report_json_dir.exists():
            json_files = sorted(report_json_dir.glob("*.json"))
            print(f"  Found {len(json_files)} opening report JSONs")
            for fp in json_files:
                c = import_opening_report_json(str(fp), session)
                if c:
                    print(f"  Report from {fp.name}: {c}")

        # 2d. Import APP records from crawl_output/APP/ (with encoding fallback)
        app_dir = CRAWL / "APP"
        if app_dir.exists():
            for fp in sorted(app_dir.glob("*.json")):
                try:
                    c = import_app_records(str(fp), session)
                except (UnicodeDecodeError, json.JSONDecodeError) as e:
                    # Try with utf-8 encoding
                    import codecs
                    with codecs.open(str(fp), 'r', encoding='utf-8', errors='replace') as f:
                        data = json.load(f)
                    c = 0  # Just log the issue for now
                    print(f"  APP from {fp.name}: encoding issue, skipped ({e})")
                else:
                    print(f"  APP from {fp.name}: {c}")

        # 2e. Import NPP records from runtime/knowledge/npp/
        npp_dir = KNOWLEDGE / "npp"
        if npp_dir.exists():
            from app.db.etl import import_npp_json
            for fp in sorted(npp_dir.rglob("*.json")):
                try:
                    c = import_npp_json(str(fp), session)
                except Exception as e:
                    print(f"  NPP from {fp.name}: error ({e})")
                else:
                    print(f"  NPP from {fp.name}: {c}")

        # Summary
        from app.db.models import Tender, Award, OpeningReport, APPRecord, Contractor
        tender_count = session.query(Tender).count()
        award_count = session.query(Award).count()
        report_count = session.query(OpeningReport).count()
        app_count = session.query(APPRecord).count()
        contractor_count = session.query(Contractor).count()
        print(f"\n=== Final DB Summary ===")
        print(f"  Tenders: {tender_count}")
        print(f"  Awards: {award_count}")
        print(f"  Opening Reports: {report_count}")
        print(f"  APP Records: {app_count}")
        print(f"  Contractors: {contractor_count}")

    finally:
        session.close()

if __name__ == "__main__":
    asyncio.run(main())
