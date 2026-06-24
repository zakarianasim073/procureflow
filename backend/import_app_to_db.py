"""
Import crawled APP JSON files into PostgreSQL (procurement_tenders + app_records).
"""

import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("import-app")

DATABASE_URL = "postgresql+psycopg2://procurementflow:procurementflow@localhost:5432/procurementflow"
CRAWL_APP_DIR = Path(__file__).resolve().parent / "crawl_output" / "APP"

PACKAGE_NORMALIZE = re.compile(r"[^A-Za-z0-9/._-]")


def normalize_package_no(raw: Any) -> str:
    s = str(raw or "").strip().upper()
    s = re.sub(r"\s+", " ", s).strip()
    s = PACKAGE_NORMALIZE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:250]


def safe_float(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        return float(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def to_iso_date(val: Any) -> str:
    s = str(val or "").strip()
    if not s:
        return ""
    for fmt in ("%d/%b/%Y", "%d-%b-%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s[:20]


def main():
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Load existing procurement_tenders by package_no
    logger.info("Loading existing procurement_tenders...")
    existing_tenders: Dict[str, Dict] = {}
    rows = session.execute(text("SELECT id, package_no FROM procurement_tenders")).fetchall()
    for r in rows:
        existing_tenders[str(r[1] or "").upper()] = str(r[0])

    # Load existing app_records by procurement_tender_id
    logger.info("Loading existing app_records...")
    existing_app: Dict[str, Dict] = {}
    rows = session.execute(text("SELECT id, procurement_tender_id, source_tender_id FROM app_records")).fetchall()
    for r in rows:
        existing_app[str(r[1])] = {"id": str(r[0]), "source_tender_id": str(r[2] or "")}

    total_records = 0
    total_created_tender = 0
    total_created_app = 0
    total_skipped = 0

    app_files = sorted(f for f in os.listdir(CRAWL_APP_DIR) if f.endswith(".json") and f != "_checkpoint.json")

    for fname in app_files:
        agency = fname[:-5]
        fpath = CRAWL_APP_DIR / fname
        records = json.loads(fpath.read_text(encoding="utf-8"))
        logger.info(f"[{agency}] {len(records)} records...")

        batch_created_tender = 0
        batch_created_app = 0
        batch_skipped = 0

        for rec in records:
            raw_pkg = rec.get("package_no", "")
            pkg = normalize_package_no(raw_pkg)
            if not pkg:
                batch_skipped += 1
                continue

            total_records += 1

            # --- ProcurementTender ---
            tender_id = existing_tenders.get(pkg)
            if tender_id is None:
                tender_id = str(uuid4())
                agency_code = (rec.get("agency") or agency).strip().upper()[:20]
                # procurement_method from Col[5] is not in APP JSON (was stripped)
                # But the crawl script parses it — it's stored in rec.get("procurement_method")
                procurement_method = (rec.get("procurement_method") or "").strip()[:100]
                session.execute(
                    text("""
                        INSERT INTO procurement_tenders (id, package_no, title, agency_code, procurement_method, match_type, created_at, updated_at)
                        VALUES (:id, :package_no, :title, :agency_code, :procurement_method, 'unmatched_app', NOW(), NOW())
                    """),
                    {
                        "id": tender_id,
                        "package_no": pkg,
                        "title": (rec.get("title") or rec.get("work_name") or "")[:500],
                        "agency_code": agency_code,
                        "procurement_method": procurement_method,
                    },
                )
                existing_tenders[pkg] = tender_id
                batch_created_tender += 1
                total_created_tender += 1

            # --- APPRecord ---
            app_rec = existing_app.get(tender_id)
            if app_rec is None:
                source_tender_id = str(rec.get("tender_id", "")).strip()
                title = (rec.get("title") or rec.get("work_name") or "")[:500]
                estimated_cost = safe_float(rec.get("estimated_cost_bdt"))
                status = (rec.get("status") or "APP").strip()[:50]
                published_date = to_iso_date(rec.get("published_date"))
                deadline = to_iso_date(rec.get("deadline"))
                financial_year = (rec.get("financial_year") or "").strip()[:20]
                app_code = (rec.get("app_code") or "").strip()[:200]
                category = (rec.get("category") or "").strip()[:100]

                session.execute(
                    text("""
                        INSERT INTO app_records (id, procurement_tender_id, source_tender_id, title, estimated_cost_bdt, status, published_date, deadline, financial_year, app_code, category, created_at, updated_at)
                        VALUES (:id, :procurement_tender_id, :source_tender_id, :title, :estimated_cost_bdt, :status, :published_date, :deadline, :financial_year, :app_code, :category, NOW(), NOW())
                    """),
                    {
                        "id": str(uuid4()),
                        "procurement_tender_id": tender_id,
                        "source_tender_id": source_tender_id or pkg,
                        "title": title,
                        "estimated_cost_bdt": estimated_cost,
                        "status": status,
                        "published_date": published_date,
                        "deadline": deadline,
                        "financial_year": financial_year,
                        "app_code": app_code,
                        "category": category,
                    },
                )
                existing_app[tender_id] = {"id": str(uuid4()), "source_tender_id": source_tender_id}
                batch_created_app += 1
                total_created_app += 1
            else:
                # Update existing app_record with any new info
                source_tender_id = str(rec.get("tender_id", "")).strip()
                if source_tender_id and not app_rec["source_tender_id"]:
                    session.execute(
                        text("UPDATE app_records SET source_tender_id = :sid WHERE id = :id"),
                        {"sid": source_tender_id, "id": app_rec["id"]},
                    )
                    batch_skipped += 1

            # Flush every 1000 records
            if total_records % 1000 == 0:
                session.commit()
                logger.info(f"  ... {total_records} records processed ({total_created_tender} tenders, {total_created_app} app records)")

        session.commit()
        logger.info(f"  [{agency}] done: +{batch_created_tender} tenders, +{batch_created_app} app records, {batch_skipped} skipped/updated")

    session.commit()
    session.close()
    engine.dispose()

    logger.info("=" * 60)
    logger.info(f"Total records processed: {total_records}")
    logger.info(f"ProcurementTenders created: {total_created_tender}")
    logger.info(f"APPRecords created: {total_created_app}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
