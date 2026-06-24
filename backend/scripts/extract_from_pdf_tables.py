"""Extract SOR items with zone-wise rates from PDFs using pdfplumber table extraction"""
import csv
import re
import logging
from pathlib import Path
from typing import List, Dict, Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
logger = logging.getLogger("pdf_tables")

SOR_DIR = Path(__file__).parent.parent / "app" / "sor"

LGED_PDF = Path(r"D:\enterprise-tender-suite\enterprise-tender-suite\sample pdf,excel&docx\SOR\LGED Revised Rate Schedule,2023.pdf")
PWD_PDF = Path(r"D:\enterprise-tender-suite\enterprise-tender-suite\sample pdf,excel&docx\SOR\PWDSoR2022-Revised-2.3.23-Website.pdf")
BWDB_PDF = Path(r"C:\Users\znasi\Downloads\1247388\BWDB Revised Rate Scedule.pdf")

ITEM_CODE_RE = re.compile(r'^\d+[\d.]*\d$')  # e.g. 1.01, 1.01.1, 2.02.3.01
SECTION_RE = re.compile(r'^(Chapter|Section)', re.IGNORECASE)

UNIT_SET = {
    'job', 'sqm', 'cum', 'day', 'each', 'set', 'kg', 'ton', 'm', 'mm', 'cm',
    'lump', 'rprm', 'sqm.', 'cum.', 'no', 'nos', 'ltr', 'litre', 'litres',
    'hour', 'month', 'week', 'year', 'rm', 'm.', 'sqm', 'rft', 'cft',
    'sqm.', 'cum.', 'kg.', 'ton.', 'km', 'm2', 'm3',
}

def clean_rate(val: Optional[str]) -> Optional[float]:
    if not val:
        return None
    val = str(val).strip().replace(',', '').replace(' ', '')
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None

def is_valid_item_code(code: Optional[str]) -> bool:
    if not code:
        return False
    code = str(code).strip()
    if not code:
        return False
    if SECTION_RE.match(code):
        return False
    if code.lower() in ('item no.', 'item code', 'description of item', 'unit', 'rate'):
        return False
    if ITEM_CODE_RE.match(code):
        return True
    return bool(re.match(r'^\d+[\.\d]*$', code))

def extract_lged_tables() -> List[Dict]:
    import pdfplumber
    items = []
    seen_codes = set()
    with pdfplumber.open(str(LGED_PDF)) as pdf:
        logger.info("LGED PDF: %d pages", len(pdf.pages))
        for page_num, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or not row[0]:
                        continue
                    code = str(row[0]).strip() if row[0] else ''
                    if not is_valid_item_code(code):
                        continue
                    if code in seen_codes:
                        continue
                    desc = str(row[1]).strip() if len(row) > 1 and row[1] else ''
                    unit = str(row[2]).strip().lower() if len(row) > 2 and row[2] else ''
                    if not unit or unit == 'none':
                        unit = ''
                    za = clean_rate(row[3]) if len(row) > 3 else None
                    zb = clean_rate(row[4]) if len(row) > 4 else None
                    zc = clean_rate(row[5]) if len(row) > 5 else None
                    zd = clean_rate(row[6]) if len(row) > 6 else None
                    rates = [r for r in [za, zb, zc, zd] if r is not None]
                    if len(rates) == 0:
                        continue
                    seen_codes.add(code)
                    items.append({
                        'agency': 'LGED',
                        'code': code,
                        'description': desc.replace('\n', ' ').replace('\r', ' ').strip(),
                        'unit': unit,
                        'zone_a': za or 0,
                        'zone_b': zb or 0,
                        'zone_c': zc or 0,
                        'zone_d': zd or 0,
                    })
    logger.info("Extracted %d LGED items", len(items))
    return items

def extract_pwd_tables() -> List[Dict]:
    import pdfplumber
    items = []
    seen_codes = set()
    with pdfplumber.open(str(PWD_PDF)) as pdf:
        logger.info("PWD PDF: %d pages", len(pdf.pages))
        for page_num, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or not row[0]:
                        continue
                    code = str(row[0]).strip() if row[0] else ''
                    if not is_valid_item_code(code):
                        continue
                    if code in seen_codes:
                        continue
                    desc = str(row[1]).strip() if len(row) > 1 and row[1] else ''
                    unit = ''
                    if len(row) > 2 and row[2]:
                        unit = str(row[2]).strip().lower()
                    if (not unit or unit == 'none') and len(row) > 3 and row[3]:
                        unit = str(row[3]).strip().lower()
                    if unit == 'none':
                        unit = ''
                    za = clean_rate(row[5]) if len(row) > 5 else None
                    zb = clean_rate(row[6]) if len(row) > 6 else None
                    zc = clean_rate(row[7]) if len(row) > 7 else None
                    zd = clean_rate(row[8]) if len(row) > 8 else None
                    rates = [r for r in [za, zb, zc, zd] if r is not None]
                    if len(rates) == 0:
                        continue
                    seen_codes.add(code)
                    items.append({
                        'agency': 'PWD',
                        'code': code,
                        'description': desc.replace('\n', ' ').replace('\r', ' ').strip(),
                        'unit': unit,
                        'zone_a': za or 0,
                        'zone_b': zb or 0,
                        'zone_c': zc or 0,
                        'zone_d': zd or 0,
                    })
    logger.info("Extracted %d PWD items", len(items))
    return items

def load_existing_csv(agency: str) -> List[Dict]:
    csv_path = SOR_DIR / agency.lower() / "rates.csv"
    if not csv_path.exists():
        return []
    rates = []
    with open(str(csv_path), 'r', encoding='utf-8-sig', errors='replace') as f:
        for row in csv.DictReader(f):
            try:
                rates.append({
                    'agency': agency.upper(),
                    'code': row.get('code', '').strip(),
                    'description': row.get('description', '').strip(),
                    'unit': row.get('unit', '').strip().lower(),
                    'zone_a': float(row.get('zone_a', 0) or 0),
                    'zone_b': float(row.get('zone_b', 0) or 0),
                    'zone_c': float(row.get('zone_c', 0) or 0),
                    'zone_d': float(row.get('zone_d', 0) or 0),
                })
            except (ValueError, KeyError):
                continue
    return rates

def merge_items(pdf_items: List[Dict], csv_items: List[Dict]) -> List[Dict]:
    pdf_by_code = {it['code']: it for it in pdf_items}
    csv_by_code = {it['code']: it for it in csv_items}
    merged = {}
    for it in pdf_items:
        merged[it['code']] = it
    for it in csv_items:
        if it['code'] not in merged:
            merged[it['code']] = it
    result = list(merged.values())
    logger.info("Merge: PDF=%d CSV=%d Unique=%d", len(pdf_items), len(csv_items), len(result))
    return result

def save_csv(agency: str, items: List[Dict]):
    path = SOR_DIR / agency.lower() / "rates.csv"
    fieldnames = ['agency', 'code', 'description', 'unit', 'zone_a', 'zone_b', 'zone_c', 'zone_d']
    with open(str(path), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for it in items:
            w.writerow(it)
    logger.info("Saved %d items to %s", len(items), path)

def import_to_db():
    """Import CSVs to PostgreSQL via the ETL module"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    sys.path.insert(0, str(Path(__file__).parent.parent / "app"))
    try:
        from app.services.sor_etl import import_sor_to_db, get_sor_count
        from app.db.database import get_sync_engine
        from sqlalchemy import text
        engine = get_sync_engine()
        cnt = get_sor_count()
        logger.info("Current DB sor_rates count: %d", cnt)
        import_sor_to_db(force=True)
        cnt2 = get_sor_count()
        logger.info("DB sor_rates count after import: %d", cnt2)
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT agency, COUNT(*) as cnt
                FROM sor_rates GROUP BY agency ORDER BY agency
            """)).fetchall()
            for row in rows:
                logger.info("  %s: %d", row[0], row[1])
    except Exception as e:
        logger.error("DB import error: %s", e)
        import traceback
        traceback.print_exc()

def main():
    logger.info("=" * 50)
    logger.info("Extracting LGED from PDF tables...")
    lged_pdf = extract_lged_tables()
    lged_csv = load_existing_csv("LGED")
    lged_merged = merge_items(lged_pdf, lged_csv)
    save_csv("LGED", lged_merged)

    logger.info("=" * 50)
    logger.info("Extracting PWD from PDF tables...")
    pwd_pdf = extract_pwd_tables()
    pwd_csv = load_existing_csv("PWD")
    pwd_merged = merge_items(pwd_pdf, pwd_csv)
    save_csv("PWD", pwd_merged)

    logger.info("=" * 50)
    logger.info("BWDB (scanned PDF - keeping existing Excel data)")
    bwdb_csv = load_existing_csv("BWDB")
    logger.info("BWDB: %d items (unchanged)", len(bwdb_csv))
    bwdb_merged = merge_items([], bwdb_csv)
    save_csv("BWDB", bwdb_merged)

    logger.info("=" * 50)
    total = len(lged_merged) + len(pwd_merged) + len(bwdb_merged)
    logger.info("Total items: LGED=%d + PWD=%d + BWDB=%d = %d",
                len(lged_merged), len(pwd_merged), len(bwdb_merged), total)

    logger.info("=" * 50)
    logger.info("Importing to PostgreSQL...")
    import_to_db()

    logger.info("=" * 50)
    logger.info("Done!")

if __name__ == "__main__":
    main()
