"""
ETL Pipeline: JSON files → PostgreSQL-compatible Database.
Imports all agency JSON data, award data, NPP evaluations, and PPR records.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session as SyncSession

from app.agents.core.regime import get_regime
from app.db.models import Tender, Award, APPRecord, Contractor, OpeningReport, KnowledgeEntry, AgentResult, NPPRecord, PPREvaluation, RateAnalysis

logger = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────

def _safe_decimal(val, default=None):
    if val is None:
        return default
    try:
        return Decimal(str(val))
    except (ValueError, TypeError):
        return default


def _safe_str(val, default=""):
    if val is None:
        return default
    return str(val)


def _parse_date(val):
    if not val:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(val)[:19], fmt).date()
        except (ValueError, TypeError):
            continue
    return None


# ── ETL: Tenders from Agency JSON Files ─────────────────────────────────

def import_tender_json(file_path: str, session: SyncSession, agency: str = None) -> int:
    """Import tender data from an agency JSON file."""
    with open(file_path) as f:
        data = json.load(f)
    
    if isinstance(data, dict):
        items = data.get("tenders", data.get("data", [data]))
    elif isinstance(data, list):
        items = data
    else:
        logger.warning(f"Unknown JSON structure in {file_path}")
        return 0
    
    count = 0
    domain = Path(file_path).stem
    
    for item in items:
        if not isinstance(item, dict):
            continue
        
        tender_id = str(item.get("tender_id", ""))
        if not tender_id:
            continue
        
        # Check if exists
        existing = session.query(Tender).filter_by(tender_id=tender_id).first()
        if existing:
            continue
        
        tender = Tender(
            tender_id=tender_id,
            package_no=_safe_str(item.get("package_no")),
            title=_safe_str(item.get("title")),
            work_name=_safe_str(item.get("work_name")),
            agency=agency or _safe_str(item.get("agency_target")),
            procuring_entity=_safe_str(item.get("procuring_entity") or item.get("procurement_entity")),
            estimated_amount_bdt=_safe_decimal(item.get("estimated_amount_bdt")),
            procurement_type=_safe_str(item.get("procurement_type")),
            department_id=_safe_str(item.get("department_id")),
            agency_target=_safe_str(item.get("agency_target")),
            app_id=_safe_str(item.get("app_id")),
            source=_safe_str(item.get("source", "egp")),
            status="archived" if item.get("is_archived") else "live",
            is_archived=bool(item.get("is_archived", False)),
            raw_data=item,
            source_file=str(file_path),
            _stored_at=_safe_str(item.get("_stored_at")),
            _domain=agency or domain,
        )
        
        # Parse dates
        for fld in ["publication_date", "closing_date", "opening_date", "last_selling_date"]:
            val = item.get(fld)
            if val:
                d = _parse_date(val)
                if d:
                    setattr(tender, fld, d)
        
        session.add(tender)
        count += 1
        
        # Bulk commit every 500
        if count % 500 == 0:
            session.flush()
    
    session.commit()
    logger.info(f"Imported {count} tenders from {file_path}")
    return count


def import_award_json(file_path: str, session: SyncSession) -> int:
    """Import award data from JSON file."""
    with open(file_path) as f:
        data = json.load(f)
    
    items = data if isinstance(data, list) else data.get("awards", data.get("data", [data]))
    if isinstance(items, dict):
        items = [items]
    
    count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        
        tender_id = str(item.get("tender_id", ""))
        if not tender_id:
            continue

        # PostgreSQL enforces award -> tender integrity.
        if not session.query(Tender).filter_by(tender_id=tender_id).first():
            continue
        
        # Check if award exists for this tender
        existing = session.query(Award).filter_by(tender_id=tender_id).first()
        if existing:
            continue
        
        award = Award(
            tender_id=tender_id,
            contractor_name=_safe_str(item.get("winner") or item.get("contractor_name")),
            contractor_id=_safe_str(item.get("company_id") or item.get("contractor_id")),
            winner=_safe_str(item.get("winner")),
            company_id=_safe_str(item.get("company_id")),
            award_amount=_safe_decimal(item.get("award_amount")),
            amount_bdt=_safe_decimal(item.get("amount_bdt")),
            experience_cert_no=_safe_str(item.get("experience_cert_no")),
            procurement_nature=_safe_str(item.get("procurement_nature")),
            procurement_type=_safe_str(item.get("procurement_type")),
            agency=_safe_str(item.get("agency")),
            work_status=_safe_str(item.get("work_status")),
            raw_data=item,
            source_file=str(file_path),
        )
        
        for fld in ["award_date", "contract_start_date", "contract_end_date"]:
            val = item.get(fld)
            if val:
                d = _parse_date(val)
                if d:
                    setattr(award, fld, d)
        
        session.add(award)
        count += 1
    
    session.commit()
    logger.info(f"Imported {count} awards from {file_path}")
    return count


def import_opening_report_json(file_path: str, session: SyncSession) -> int:
    """Import opening report data from JSON file."""
    with open(file_path) as f:
        data = json.load(f)

    file_tender_id = Path(file_path).stem

    items = data if isinstance(data, list) else data.get("opening_reports", data.get("data", [data]))
    if isinstance(items, dict):
        items = [items]
    
    count = 0
    for item in items:
        if not isinstance(item, dict):
            continue

        raw_tender_id = item.get("tender_id") or file_tender_id
        tender_id = str(raw_tender_id).strip() if raw_tender_id is not None else ""
        if not tender_id:
            continue

        # Skip orphaned reports instead of poisoning the whole session.
        if not session.query(Tender).filter_by(tender_id=tender_id).first():
            continue
        
        existing = session.query(OpeningReport).filter_by(tender_id=tender_id).first()
        if existing:
            continue
        
        report = OpeningReport(
            tender_id=tender_id,
            estimated_amount_bdt=_safe_decimal(item.get("estimated_amount_bdt") or item.get("estimate_amount")),
            pe_office=_safe_str(item.get("pe_office") or item.get("procuring_entity")),
            zone=_safe_str(item.get("zone")),
            package_work_name=_safe_str(item.get("package_work_name") or item.get("work_name")),
            bidders=item.get("bidders", []),
            winner_name=_safe_str(item.get("winner_name") or item.get("winner")),
            winner_amount=_safe_decimal(item.get("winner_amount") or item.get("award_amount")),
            is_archived=True,
            raw_data=item,
            source_json=str(file_path),
        )
        
        if item.get("opening_date"):
            d = _parse_date(item.get("opening_date"))
            if d:
                report.opening_date = d
        
        # Check for SLT
        if item.get("bidders"):
            for b in item["bidders"]:
                if isinstance(b, dict) and b.get("status") in ("slt", "alt", "non_responsive"):
                    report.has_slt = True
                    if b.get("status") == "alt":
                        report.has_alt = True
        
        session.add(report)
        count += 1
    
    session.commit()
    logger.info(f"Imported {count} opening reports from {file_path}")
    return count


# ── Full ETL Pipeline ────────────────────────────────────────────────────



def import_npp_json(file_path: str, session: SyncSession) -> int:
    """Import NPP (Negotiated Percentage Below Estimate) evaluation data."""
    with open(file_path) as f:
        data = json.load(f)
    
    # Handle different JSON structures:
    # 1. Array of records: [ {...}, {...} ]
    # 2. Single record object: { "tender_id": "...", ... }
    # 3. Object with "npp" or "data" keys containing array
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # Check if it has array keys
        if "npp" in data and isinstance(data["npp"], list):
            items = data["npp"]
        elif "data" in data and isinstance(data["data"], list):
            items = data["data"]
        else:
            # Single record
            items = [data]
    else:
        # Bare primitive (float, int, str) - cannot extract tender_id, log and skip
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Skipping {file_path}: JSON is primitive type ({type(data).__name__}), not a record")
        return 0
    
    if isinstance(items, dict):
        items = [items]
    
    count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        
        tender_id = str(item.get("tender_id", ""))
        if not tender_id:
            continue
        
        # Check if NPP record exists
        existing = session.query(NPPRecord).filter_by(tender_id=tender_id).first()
        if existing:
            continue
        
        # Map actual NPP data fields
        # The actual NPP format has: tender_id, package_no (which is work_name), app_estimate, award_amount, npp, agency, etc.
        package_no = item.get("package_no", "")
        work_name = item.get("package_no", "")  # package_no contains the work name in this format
        estimated_amount = item.get("app_estimate", item.get("estimated_amount_bdt", 0))
        award_amount = item.get("award_amount", 0)
        npp_pct = item.get("npp", item.get("lowest_percent_below_oe", 0))
        
        # Calculate lowest_bid from npp percentage
        lowest_bid = 0
        if estimated_amount and npp_pct:
            lowest_bid = estimated_amount * (1 - npp_pct)
        
        npp = NPPRecord(
            tender_id=tender_id,
            package_no=str(package_no) if package_no else "",
            work_name=str(work_name) if work_name else "",
            pe_office=item.get("procuring_entity", ""),
            zone=item.get("zone", ""),
            estimated_amount_bdt=_safe_decimal(estimated_amount),
            lowest_bid=_safe_decimal(lowest_bid),
            bid_average=_safe_decimal(lowest_bid),  # Use lowest_bid as average for now
            lowest_percent_below_oe=_safe_decimal(npp_pct),
            average_percent_below_oe=_safe_decimal(npp_pct),
            bid_spread_percent=_safe_decimal(0),
            bidder_count=1,  # We have at least the winner
            cluster_detected=False,
            discount_strategy_detected=False,
            slt_risk="low" if npp_pct and float(npp_pct) < 0.15 else "medium",
            likely_market_discount=_safe_decimal(npp_pct),
            agency=item.get("agency", ""),
            source_file=file_path,
            raw_data=item,
        )
        
        session.add(npp)
        count += 1
    
    session.commit()
    logger.info(f"Imported {count} NPP records from {file_path}")
    return count

def import_ppr_evaluations(file_path: str, session: SyncSession) -> int:
    """Import PPR (Schedule 4/5/6) evaluation results."""
    with open(file_path) as f:
        data = json.load(f)
    
    items = data if isinstance(data, list) else data.get("ppr_evaluations", data.get("data", [data]))
    if isinstance(items, dict):
        items = [items]
    
    count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        
        tender_id = str(item.get("tender_id", ""))
        if not tender_id:
            continue
        
        # Check if PPR evaluation exists
        existing = session.query(PPREvaluation).filter_by(tender_id=tender_id).first()
        if existing:
            continue
        
        # Create PPR schedules for each schedule type
        schedules_data = item.get("schedules", [])
        for schedule_item in schedules_data:
            ppr_schedule = PPREvaluation(
                tender_id=tender_id,
                schedule_type="" if not isinstance(schedule_item.get("schedule_type"), dict) else schedule_item.get("schedule_type").get("value", ""),
                schedule_label="" if not isinstance(schedule_item.get("schedule_label"), dict) else schedule_item.get("schedule_label").get("value", ""),
                criteria="" if not isinstance(schedule_item.get("criteria"), dict) else schedule_item.get("criteria").get("value", ""),
                total_marks=0.0 if not isinstance(schedule_item.get("total_marks"), (int, float)) else schedule_item.get("total_marks"),
                max_marks=0.0 if not isinstance(schedule_item.get("max_marks"), (int, float)) else schedule_item.get("max_marks"),
                percentage=0.0 if not isinstance(schedule_item.get("percentage"), (int, float)) else schedule_item.get("percentage"),
                passed=False if not isinstance(schedule_item.get("passed"), bool) else schedule_item.get("passed"),
                raw_data=item,
            )
            session.add(ppr_schedule)
            count += 1
    
    session.commit()
    logger.info(f"Imported {count} PPR evaluation records from {file_path}")
    return count

def import_app_records(file_path: str, session: SyncSession) -> int:
    """Import APP (Annual Procurement Plan) records."""
    with open(file_path) as f:
        data = json.load(f)
    
    items = data if isinstance(data, list) else data.get("app_records", data.get("data", [data]))
    if isinstance(items, dict):
        items = [items]
    
    count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        
        tender_id = str(item.get("tender_id", ""))
        if not tender_id:
            continue
        
        # Check if APP record exists
        existing = session.query(APPRecord).filter_by(tender_id=tender_id).first()
        if existing:
            continue
        
        app_record = APPRecord(
            tender_id=tender_id,
            package_no="" if not isinstance(item.get("package_no"), dict) else item.get("package_no").get("value", ""),
            work_name="" if not isinstance(item.get("work_name"), dict) else item.get("work_name").get("value", ""),
            estimated_amount_bdt=0.0 if not isinstance(item.get("estimated_amount_bdt"), (int, float)) else item.get("estimated_amount_bdt"),
            procurement_type="" if not isinstance(item.get("procurement_type"), dict) else item.get("procurement_type").get("value", ""),
            department_id="" if not isinstance(item.get("department_id"), dict) else item.get("department_id").get("value", ""),
            agency_target="" if not isinstance(item.get("agency_target"), dict) else item.get("agency_target").get("value", ""),
            app_id="" if not isinstance(item.get("app_id"), dict) else item.get("app_id").get("value", ""),
            source="" if not isinstance(item.get("source"), dict) else item.get("source").get("value", ""),
            status="" if not isinstance(item.get("status"), dict) else item.get("status").get("value", ""),
            is_archived=False if not isinstance(item.get("is_archived"), bool) else item.get("is_archived"),
            raw_data=item,
            source_file=file_path,
        )
        
        session.add(app_record)
        count += 1
    
    session.commit()
    logger.info(f"Imported {count} APP records from {file_path}")
    return count

def import_rates(file_path: str, session: SyncSession) -> int:
    """Import market rate analysis data."""
    with open(file_path) as f:
        data = json.load(f)
    
    items = data if isinstance(data, list) else data.get("rates", data.get("data", [data]))
    if isinstance(items, dict):
        items = [items]
    
    count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        
        rate_id = str(item.get("rate_id", ""))
        if not rate_id:
            continue
        
        # Check if rate record exists
        existing = session.query(RateAnalysis).filter_by(rate_id=rate_id).first()
        if existing:
            continue
        
        rate_record = RateAnalysis(
            rate_id=rate_id,
            agency="" if not isinstance(item.get("agency"), dict) else item.get("agency").get("value", ""),
            zone="" if not isinstance(item.get("zone"), dict) else item.get("zone").get("value", ""),
            procurement_type="" if not isinstance(item.get("procurement_type"), dict) else item.get("procurement_type").get("value", ""),
            item_code="" if not isinstance(item.get("item_code"), dict) else item.get("item_code").get("value", ""),
            item_description="" if not isinstance(item.get("item_description"), dict) else item.get("item_description").get("value", ""),
            sor_rate=0.0 if not isinstance(item.get("sor_rate"), (int, float)) else item.get("sor_rate"),
            quoted_rate=0.0 if not isinstance(item.get("quoted_rate"), (int, float)) else item.get("quoted_rate"),
            rate_diff_pct=0.0 if not isinstance(item.get("rate_diff_pct"), (int, float)) else item.get("rate_diff_pct"),
            market_trend="" if not isinstance(item.get("market_trend"), dict) else item.get("market_trend").get("value", ""),
            raw_data=item,
            source_file=file_path,
        )
        
        session.add(rate_record)
        count += 1
    
    session.commit()
    logger.info(f"Imported {count} rate analysis records from {file_path}")
    return count

def run_full_etl(
    knowledge_base_path: str,
    session: SyncSession,
    agency_files: Dict[str, str] = None,
) -> Dict[str, int]:
    """Run full ETL pipeline: import all JSON data into database.
    
    Args:
        knowledge_base_path: Path to runtime/knowledge or backend/runtime/knowledge
        session: SQLAlchemy session
        agency_files: Optional dict of agency_name → file_path overrides
    
    Returns:
        Dict with counts per category
    """
    results = {"tenders": 0, "awards": 0, "opening_reports": 0}
    kb = Path(knowledge_base_path)
    
    if not kb.exists():
        logger.warning(f"Knowledge base path does not exist: {kb}")
        return results
    
    # ── Import agency tender files ──
    if agency_files:
        for agency, fp in agency_files.items():
            if os.path.exists(fp):
                c = import_tender_json(fp, session, agency=agency)
                results["tenders"] += c
    
    # ── Import from standard paths ──
    # Tenders
    tender_dir = kb / "tenders"
    if tender_dir.exists():
        for fp in sorted(tender_dir.glob("*.json")):
            c = import_tender_json(str(fp), session)
            results["tenders"] += c
    
    # Awards
    award_dir = kb / "awards"
    if award_dir.exists():
        for fp in sorted(award_dir.glob("*.json")):
            c = import_award_json(str(fp), session)
            results["awards"] += c
    
    # Awards summary
    award_summary_dir = kb / "awards_summary"
    if award_summary_dir.exists():
        for fp in sorted(award_summary_dir.glob("*.json")):
            c = import_award_json(str(fp), session)
            results["awards"] += c
    
    # Opening reports (custom path)
    reports_dir = kb / "opening_reports"
    if reports_dir.exists():
        for fp in sorted(reports_dir.glob("*.json")):
            c = import_opening_report_json(str(fp), session)
            results["opening_reports"] += c
    
    logger.info(f"ETL complete: {results}")
    return results


def ingest_uploaded_json_files(session: SyncSession, upload_dir: str = "/tmp/codex-web-uploads") -> Dict[str, int]:
    """Ingest JSON files from the codex-web-uploads directory."""
    results = {"tenders": 0, "awards": 0, "opening_reports": 0}
    upload_path = Path(upload_dir)
    
    if not upload_path.exists():
        logger.warning(f"Upload directory not found: {upload_dir}")
        return results
    
    # Map of known agency files
    agency_map = {}
    for d in upload_path.iterdir():
        if not d.is_dir():
            continue
        for f in d.iterdir():
            fname = f.name
            if fname in ("BWDB.json", "BBA.json", "RHD.json", "PWD.json", "LGED.json"):
                agency = fname.replace(".json", "")
                agency_map[agency] = str(f)
                logger.info(f"Found agency file: {agency} -> {f}")
    
    # Import agency tender files
    for agency, fp in agency_map.items():
        c = import_tender_json(fp, session, agency=agency)
        results["tenders"] += c
        logger.info(f"  {agency}: {c} tenders")
    
    # Import award files
    for d in upload_path.iterdir():
        if not d.is_dir():
            continue
        for f in d.iterdir():
            fname = f.name
            if "BWDB_batch" in fname and fname.endswith(".json"):
                c = import_award_json(str(f), session)
                results["awards"] += c
                logger.info(f"  Awards from {fname}: {c}")
    
    # Import works_api files as opening reports / NPP evaluations
    for d in upload_path.iterdir():
        if not d.is_dir():
            continue
        for f in d.iterdir():
            fname = f.name
            if fname.startswith("works_api_") and fname.endswith(".json"):
                c = import_opening_report_json(str(f), session)
                results["opening_reports"] += c
    
    logger.info(f"Ingestion complete: {results}")
    return results
