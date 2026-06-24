"""Extract all SOR items zone-wise from PDF/Excel and save to PostgreSQL"""
import csv
import json
import logging
import uuid
from pathlib import Path
from typing import Dict, List

from sqlalchemy import select, func, inspect
from sqlalchemy.orm import Session

from app.db.database import get_sync_engine
from app.models.sor_rate import SorRate, SorAgency

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
logger = logging.getLogger("sor_import")

SOR_DIR = Path(__file__).parent.parent / "app" / "sor"
EXCEL_PATH = Path(r"D:\enterprise-tender-suite\enterprise-tender-suite\sample pdf,excel&docx\SOR\BWDB Rates_2023 Revised.xlsx")

def _norm(code: str) -> str:
    return code.replace(' ', '').replace('-', '').replace('.', '').replace('&', '').lower()

def load_existing_csv(agency: str) -> List[Dict]:
    csv_path = SOR_DIR / agency.lower() / "rates.csv"
    if not csv_path.exists():
        return []
    rates = []
    with open(str(csv_path), 'r', encoding='utf-8-sig', errors='replace') as f:
        for row in csv.DictReader(f):
            try:
                rates.append({
                    "agency": agency,
                    "code": row.get('code', '').strip(),
                    "description": row.get('description', '').strip(),
                    "unit": row.get('unit', '').strip().lower(),
                    "zone_a": float(row.get('zone_a', 0) or 0),
                    "zone_b": float(row.get('zone_b', 0) or 0),
                    "zone_c": float(row.get('zone_c', 0) or 0),
                    "zone_d": float(row.get('zone_d', 0) or 0),
                })
            except (ValueError, KeyError):
                continue
    return rates

def extract_lged_from_pdf() -> List[Dict]:
    from app.sor.sor_extractor import SORExtractor
    ext = SORExtractor()
    rates = ext.extract("LGED")
    logger.info("PDF extracted LGED: %d items", len(rates))
    return rates

def extract_pwd_from_pdf() -> List[Dict]:
    from app.sor.sor_extractor import SORExtractor
    ext = SORExtractor()
    rates = ext.extract("PWD")
    logger.info("PDF extracted PWD: %d items", len(rates))
    return rates

def extract_bwdb_from_excel() -> List[Dict]:
    import openpyxl
    wb = openpyxl.load_workbook(str(EXCEL_PATH), data_only=True)
    ws = wb['rates']
    rates = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        try:
            agency, code, desc, unit, za, zb, zc, zd = row[:8]
            if not code:
                continue
            code = str(code).strip()
            rates.append({
                "agency": "BWDB",
                "code": code,
                "description": str(desc or '').strip()[:300],
                "unit": str(unit or '').strip().lower(),
                "zone_a": float(za) if za else 0.0,
                "zone_b": float(zb) if zb else 0.0,
                "zone_c": float(zc) if zc else 0.0,
                "zone_d": float(zd) if zd else 0.0,
            })
        except (ValueError, TypeError):
            continue
    logger.info("Excel extracted BWDB: %d items", len(rates))
    return rates

def merge_rates(existing: List[Dict], extracted: List[Dict]) -> List[Dict]:
    """Merge extracted rates into existing, keyed by normalized code.
    Extracted rates take priority; existing-only items are preserved."""
    merged = {}
    for r in existing:
        key = _norm(r["code"])
        if key not in merged or not merged[key]["unit"]:
            merged[key] = r
    for r in extracted:
        key = _norm(r["code"])
        if key in merged:
            merged[key] = r
        else:
            merged[key] = r
    result = list(merged.values())
    result.sort(key=lambda x: x["code"])
    logger.info("Merged: %d items (existing %d + extracted %d)", len(result), len(existing), len(extracted))
    return result

def save_csv(agency: str, rates: List[Dict]):
    csv_path = SOR_DIR / agency.lower() / "rates.csv"
    fieldnames = ["agency", "code", "description", "unit", "zone_a", "zone_b", "zone_c", "zone_d"]
    with open(str(csv_path), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rates:
            w.writerow({k: r.get(k, "") for k in fieldnames})
    logger.info("Saved %d rates to %s", len(rates), csv_path)

def save_json(agency: str, rates: List[Dict]):
    json_path = SOR_DIR / agency.lower() / "rates.json"
    with open(str(json_path), "w", encoding="utf-8") as f:
        json.dump(rates, f, indent=2, ensure_ascii=False)

def import_to_pg():
    """Import all merged CSVs into PostgreSQL."""
    engine = get_sync_engine()
    inspector = inspect(engine)
    if "sor_rates" not in inspector.get_table_names():
        logger.error("sor_rates table does not exist")
        return

    from sqlalchemy.orm import Session
    # Clear existing
    with Session(engine) as session:
        session.execute(SorRate.__table__.delete())
        session.commit()
    logger.info("Cleared existing sor_rates table")

    agencies = ["BWDB", "PWD", "LGED"]
    total = 0
    with Session(engine) as session:
        for agency_name in agencies:
            csv_path = SOR_DIR / agency_name.lower() / "rates.csv"
            if not csv_path.exists():
                continue
            count = 0
            with open(str(csv_path), 'r', encoding='utf-8-sig', errors='replace') as f:
                for row in csv.DictReader(f):
                    try:
                        code = row.get('code', '').strip()
                        if not code:
                            continue
                        rate = SorRate(
                            id=str(uuid.uuid4()),
                            agency=SorAgency(agency_name),
                            code=code,
                            normalized_code=_norm(code),
                            description=row.get('description', '').strip()[:500],
                            unit=row.get('unit', '').strip().lower()[:50],
                            zone_a=float(row.get('zone_a', 0) or 0),
                            zone_b=float(row.get('zone_b', 0) or 0),
                            zone_c=float(row.get('zone_c', 0) or 0),
                            zone_d=float(row.get('zone_d', 0) or 0),
                            is_active=True,
                            source_file=str(csv_path),
                        )
                        session.add(rate)
                        count += 1
                    except (ValueError, KeyError):
                        continue
            session.commit()
            logger.info("DB: %d %s rates imported", count, agency_name)
            total += count
    logger.info("Total in DB: %d rates", total)


if __name__ == "__main__":
    # LGED: extract from PDF, merge with existing CSV
    lged_existing = load_existing_csv("LGED")
    lged_pdf = extract_lged_from_pdf()
    lged_merged = merge_rates(lged_existing, lged_pdf)
    save_csv("LGED", lged_merged)
    save_json("LGED", lged_merged)

    # PWD: extract from PDF, merge with existing CSV
    pwd_existing = load_existing_csv("PWD")
    pwd_pdf = extract_pwd_from_pdf()
    pwd_merged = merge_rates(pwd_existing, pwd_pdf)
    save_csv("PWD", pwd_merged)
    save_json("PWD", pwd_merged)

    # BWDB: extract from Excel, merge with existing CSV
    bwdb_existing = load_existing_csv("BWDB")
    bwdb_xl = extract_bwdb_from_excel()
    bwdb_merged = merge_rates(bwdb_existing, bwdb_xl)
    save_csv("BWDB", bwdb_merged)
    save_json("BWDB", bwdb_merged)

    # Import all to PostgreSQL
    import_to_pg()

    print("\n=== Done ===")
    print(f"BWDB: {len(bwdb_merged)} items")
    print(f"PWD:  {len(pwd_merged)} items")
    print(f"LGED: {len(lged_merged)} items")
    print(f"Total: {len(bwdb_merged) + len(pwd_merged) + len(lged_merged)}")
