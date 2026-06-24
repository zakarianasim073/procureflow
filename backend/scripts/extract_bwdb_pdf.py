"""Extract BWDB items from PDF text (scan-based extraction)"""
import csv
import re
import logging
from pathlib import Path
from typing import List, Dict

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
logger = logging.getLogger("bwdb_pdf")

BWDB_PDF = Path(r"C:\Users\znasi\Downloads\Documents\BWDB Revised Rate Schedule2023.pdf")
SOR_DIR = Path(__file__).parent.parent / "app" / "sor" / "bwdb"

UNIT_PAT = re.compile(r'\b(sqm|m|cum|kg|ton|each|job|set|day|lump|no|nos|hour|month|year|sqm\.|cum\.)\b', re.IGNORECASE)
ITEM_RE = re.compile(r'(\d{2}-\d{3}-\d{2})\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)')

def extract_bwdb_from_pdf() -> List[Dict]:
    import PyPDF2
    with open(str(BWDB_PDF), 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        all_text = []
        for i in range(len(reader.pages)):
            text = reader.pages[i].extract_text()
            if text:
                all_text.append(text)
    full = '\n'.join(all_text)
    lines = full.split('\n')
    items = []
    seen_codes = set()
    for line in lines:
        line = line.strip()
        m = ITEM_RE.search(line)
        if not m:
            continue
        code = m.group(1)
        if code in seen_codes:
            continue
        zb = float(m.group(2).replace(',', ''))
        zc = float(m.group(3).replace(',', ''))
        zd = float(m.group(4).replace(',', ''))
        za = float(m.group(5).replace(',', ''))
        rest = line[m.end():].strip()
        unit_m = UNIT_PAT.search(rest)
        unit = unit_m.group(1).lower() if unit_m else ''
        seen_codes.add(code)
        items.append({
            'agency': 'BWDB',
            'code': code,
            'description': '',
            'unit': unit,
            'zone_a': za,
            'zone_b': zb,
            'zone_c': zc,
            'zone_d': zd,
        })
    logger.info("Extracted %d BWDB items from PDF", len(items))
    return items

def load_existing_csv() -> List[Dict]:
    csv_path = SOR_DIR / "rates.csv"
    if not csv_path.exists():
        return []
    rates = []
    with open(str(csv_path), 'r', encoding='utf-8-sig', errors='replace') as f:
        for row in csv.DictReader(f):
            try:
                rates.append({
                    'agency': 'BWDB',
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

def merge_items(pdf_items, csv_items):
    pdf_by_code = {it['code']: it for it in pdf_items}
    csv_by_code = {it['code']: it for it in csv_items}
    merged = {}
    for it in pdf_items:
        merged[it['code']] = it
    for it in csv_items:
        if it['code'] in merged:
            merged[it['code']]['description'] = it['description'] or merged[it['code']]['description']
            merged[it['code']]['unit'] = it['unit'] or merged[it['code']]['unit']
        else:
            merged[it['code']] = it
    result = list(merged.values())
    logger.info("Merge: PDF=%d CSV=%d Unique=%d", len(pdf_items), len(csv_items), len(result))
    return result

def save_csv(items):
    path = SOR_DIR / "rates.csv"
    fieldnames = ['agency', 'code', 'description', 'unit', 'zone_a', 'zone_b', 'zone_c', 'zone_d']
    with open(str(path), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for it in items:
            w.writerow(it)
    logger.info("Saved %d items to %s", len(items), path)

def main():
    pdf_items = extract_bwdb_from_pdf()
    csv_items = load_existing_csv()
    merged = merge_items(pdf_items, csv_items)
    save_csv(merged)
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    sys.path.insert(0, str(Path(__file__).parent.parent / "app"))
    from app.services.sor_etl import import_sor_to_db, get_sor_count
    from app.db.database import get_sync_engine
    from sqlalchemy import text
    engine = get_sync_engine()
    import_sor_to_db(force=True)
    cnt = get_sor_count()
    logger.info("DB sor_rates count: %d", cnt)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT agency, COUNT(*) as cnt FROM sor_rates GROUP BY agency ORDER BY agency")).fetchall()
        for row in rows:
            logger.info("  %s: %d", row[0], row[1])

if __name__ == "__main__":
    main()
