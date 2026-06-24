"""Extract BWDB SOR from split PDFs (1-50 and 51-104) using word positions"""
import csv
import re
import logging
from pathlib import Path
from typing import List, Dict, Set, Tuple

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
logger = logging.getLogger("bwdb_split")

PDFS = [
    Path(r"C:\Users\znasi\Downloads\sor_BWDB(1-50).pdf"),
    Path(r"C:\Users\znasi\Downloads\sor_BWDB(51-104).pdf"),
]
SOR_DIR = Path(__file__).parent.parent / "app" / "sor" / "bwdb"

RATE_RE = re.compile(r"([\d,]+\.\d{2})")
UNIT_SET = {"sqm", "m", "cum", "kg", "ton", "each", "job", "set", "day", "lump", "no", "nos", "hour", "month", "year"}

def clean_rate(val: str) -> float:
    return float(val.strip().replace(",", ""))

def extract_from_pdf(pdf_path: Path) -> List[Dict]:
    import pdfplumber
    items = []
    seen_codes: Set[str] = set()
    
    with pdfplumber.open(str(pdf_path)) as pdf:
        logger.info("%s: %d pages", pdf_path.name, len(pdf.pages))
        for page_num, page in enumerate(pdf.pages):
            words = page.extract_words(x_tolerance=3, y_tolerance=3)
            if not words:
                continue
            
            # Group words into rows by y-position
            rows = {}
            for w in words:
                y_key = round(w["top"])
                if y_key not in rows:
                    rows[y_key] = []
                rows[y_key].append((w["x0"], w["text"]))
            
            # Process each row
            row_texts = {}
            for y_key in sorted(rows.keys()):
                line = " ".join(t[1] for t in sorted(rows[y_key], key=lambda x: x[0]))
                row_texts[y_key] = line
            
            # Find items: look for code fragments and reconstruct
            sorted_ys = sorted(row_texts.keys())
            
            for i, y in enumerate(sorted_ys):
                line = row_texts[y]
                
                # Look for 4 rates in a line
                rates = RATE_RE.findall(line)
                if len(rates) >= 4:
                    # Look for unit in this line or nearby lines
                    unit = ""
                    for look_y in sorted_ys[max(0,i-2):min(len(sorted_ys),i+3)]:
                        for u in UNIT_SET:
                            if u in row_texts[look_y].lower():
                                unit = u
                                break
                        if unit:
                            break
                    
                    # Look for code in this line or surrounding lines (codes might be split)
                    code_parts = []
                    for look_y in sorted_ys[max(0,i-3):min(len(sorted_ys),i+3)]:
                        lt = row_texts[look_y]
                        # Match code pattern like "04 180 00" or "04-180-00"
                        m = re.search(r"(\d{2})\s*-?\s*(\d{3})\s*-?\s*(\d{2})", lt)
                        if m:
                            code = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                            if code not in seen_codes:
                                seen_codes.add(code)
                                za = clean_rate(rates[0])  # pos1 = Zone A (wait, header says B,C,D,A)
                                zb = clean_rate(rates[1])
                                zc = clean_rate(rates[2])
                                zd = clean_rate(rates[3])
                                
                                # Header says ZoneB, ZoneC, ZoneD, ZoneA
                                # So pos1=B, pos2=C, pos3=D, pos4=A
                                # Need to remap to zone_a, zone_b, zone_c, zone_d
                                # zb = pos1, zc = pos2, zd = pos3, za = pos4
                                items.append({
                                    "agency": "BWDB",
                                    "code": code,
                                    "description": "",
                                    "unit": unit,
                                    "zone_a": zd,  # pos4 = Zone A
                                    "zone_b": za,  # pos1 = Zone B
                                    "zone_c": zb,  # pos2 = Zone C
                                    "zone_d": zc,  # pos3 = Zone D
                                })
                                break
    
    logger.info("Extracted %d items from %s", len(items), pdf_path.name)
    return items

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

def merge_items(new_items, csv_items):
    """Merge: keep CSV as base, add new codes from PDF."""
    merged = {it["code"]: dict(it) for it in csv_items}
    new_count = 0
    for it in new_items:
        if it["code"] not in merged:
            merged[it["code"]] = dict(it)
            new_count += 1
    logger.info("Merge: new items=%d CSV=%d Unique=%d", new_count, len(csv_items), len(merged))
    return list(merged.values())

def save_csv(items):
    path = SOR_DIR / "rates.csv"
    fieldnames = ["agency", "code", "description", "unit", "zone_a", "zone_b", "zone_c", "zone_d"]
    with open(str(path), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for it in items:
            w.writerow(it)
    logger.info("Saved %d items", len(items))

def main():
    all_new = []
    for pdf_path in PDFS:
        items = extract_from_pdf(pdf_path)
        all_new.extend(items)
    
    # Deduplicate
    seen = set()
    unique_new = []
    for it in all_new:
        if it["code"] not in seen:
            seen.add(it["code"])
            unique_new.append(it)
    
    logger.info("Total new items from PDFs: %d", len(unique_new))
    
    csv_items = load_existing_csv()
    merged = merge_items(unique_new, csv_items)
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
