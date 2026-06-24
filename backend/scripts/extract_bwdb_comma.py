"""Extract BWDB SOR from 'comma' PDF version (139p, Zone order A,B,C,D)"""
import csv
import re
import logging
from pathlib import Path
from typing import List, Dict, Set

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
logger = logging.getLogger("bwdb_comma")

PDF_PATH = Path(r"C:\Users\znasi\Downloads\Documents\BWDB Revised Rate Schedule,2023.pdf")
SOR_DIR = Path(__file__).parent.parent / "app" / "sor" / "bwdb"

UNIT_SET = {"sqm", "m", "cum", "kg", "ton", "each", "job", "set", "day", "lump", "no", "nos", "hour", "month", "year", "sqm.", "cum.", "rft", "cft", "rm"}

def clean_rate(val: str) -> float:
    val = val.strip().replace(",", "").replace(" ", "")
    try:
        return float(val)
    except ValueError:
        return 0.0

def extract_all_text() -> str:
    import PyPDF2
    with open(str(PDF_PATH), "rb") as f:
        reader = PyPDF2.PdfReader(f)
        texts = []
        for i in range(len(reader.pages)):
            t = reader.pages[i].extract_text()
            if t:
                texts.append(t)
    return "\n".join(texts)

def extract_items(text: str) -> List[Dict]:
    """Parse items with code on same line as rates, and items with code on adjacent line."""
    lines = text.split("\n")
    items = []
    seen_codes: Set[str] = set()
    
    # Pattern 1: Code + description + unit + 4 rates on same line
    # e.g. 04-280-10 150mmx25mm m 108.98 108.34 108.37 103.08
    pat1 = re.compile(
        r"(\d{2}-\d{3}-\d{2})\s+"          # code
        r".*?\b(sqm|m|cum|kg|ton|each|job|set|day|lump|no|nos|hour|month|year)\b\s*"  # unit
        r"([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)",  # 4 rates
        re.IGNORECASE
    )
    
    for line in lines:
        m = pat1.search(line)
        if m:
            code = m.group(1)
            if code not in seen_codes:
                seen_codes.add(code)
                unit = m.group(2).lower()
                za = clean_rate(m.group(3))
                zb = clean_rate(m.group(4))
                zc = clean_rate(m.group(5))
                zd = clean_rate(m.group(6))
                items.append({
                    "agency": "BWDB",
                    "code": code,
                    "description": "",
                    "unit": unit,
                    "zone_a": za,
                    "zone_b": zb,
                    "zone_c": zc,
                    "zone_d": zd,
                })
    
    # Pattern 2: Code on one line, rates on next line
    # e.g.:
    # 04-180-00
    # siteand removingdebrisincluding sqm 44.52 43.61 43.54 40.59
    pat2_code = re.compile(r"^(\d{2}-\d{3}-\d{2})\s*$")
    pat2_rates = re.compile(
        r".*?\b(sqm|m|cum|kg|ton|each|job|set|day|lump|no|nos|hour|month|year)\b\s*"
        r"([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)",
        re.IGNORECASE
    )
    
    for i in range(len(lines) - 1):
        code_m = pat2_code.match(lines[i].strip())
        if code_m:
            code = code_m.group(1)
            if code in seen_codes:
                continue
            rate_m = pat2_rates.search(lines[i+1])
            if rate_m:
                seen_codes.add(code)
                unit = rate_m.group(1).lower()
                za = clean_rate(rate_m.group(2))
                zb = clean_rate(rate_m.group(3))
                zc = clean_rate(rate_m.group(4))
                zd = clean_rate(rate_m.group(5))
                items.append({
                    "agency": "BWDB",
                    "code": code,
                    "description": "",
                    "unit": unit,
                    "zone_a": za,
                    "zone_b": zb,
                    "zone_c": zc,
                    "zone_d": zd,
                })
    
    logger.info("Pattern 1 found: %d items", len([it for it in items if it]))
    # Deduplicate
    seen = set()
    unique = []
    for it in items:
        if it["code"] not in seen:
            seen.add(it["code"])
            unique.append(it)
    logger.info("Unique items: %d", len(unique))
    return unique

def load_existing_csv() -> List[Dict]:
    csv_path = SOR_DIR / "rates.csv"
    if not csv_path.exists():
        return []
    rates = []
    with open(str(csv_path), "r", encoding="utf-8-sig", errors="replace") as f:
        for row in csv.DictReader(f):
            try:
                rates.append({
                    "agency": "BWDB",
                    "code": row.get("code", "").strip(),
                    "description": row.get("description", "").strip(),
                    "unit": row.get("unit", "").strip().lower(),
                    "zone_a": float(row.get("zone_a", 0) or 0),
                    "zone_b": float(row.get("zone_b", 0) or 0),
                    "zone_c": float(row.get("zone_c", 0) or 0),
                    "zone_d": float(row.get("zone_d", 0) or 0),
                })
            except (ValueError, KeyError):
                continue
    return rates

def merge_items(pdf_items, csv_items):
    """Merge: keep CSV as base (it has correct zone order from B,C,D,A mapping).
    Add NEW codes from PDF (zone order A,B,C,D) that don't exist in CSV."""
    csv_by_code = {it["code"]: it for it in csv_items}
    pdf_by_code = {it["code"]: it for it in pdf_items}
    
    merged = {it["code"]: dict(it) for it in csv_items}
    
    new_from_pdf = 0
    for code, it in pdf_by_code.items():
        if code not in merged:
            merged[code] = dict(it)
            new_from_pdf += 1
    
    logger.info("Merge: PDF=%d CSV=%d Unique=%d (new from PDF=%d)",
                len(pdf_items), len(csv_items), len(merged), new_from_pdf)
    return list(merged.values())

def save_csv(items):
    path = SOR_DIR / "rates.csv"
    fieldnames = ["agency", "code", "description", "unit", "zone_a", "zone_b", "zone_c", "zone_d"]
    with open(str(path), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for it in items:
            w.writerow(it)
    logger.info("Saved %d items to %s", len(items), path)

def main():
    logger.info("Extracting text from BWDB comma PDF...")
    text = extract_all_text()
    logger.info("Total text length: %d chars", len(text))
    
    pdf_items = extract_items(text)
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
        for r in rows:
            logger.info("  %s: %d", r[0], r[1])

if __name__ == "__main__":
    main()
