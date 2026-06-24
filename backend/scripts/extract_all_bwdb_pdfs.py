"""Extract BWDB SOR from ALL split PDFs with zone understanding"""
import csv
import re
import logging
from pathlib import Path
from typing import List, Dict, Set

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
logger = logging.getLogger("bwdb_all")

SOR_DIR = Path(__file__).parent.parent / "app" / "sor" / "bwdb"

# Zone order for the split PDFs:
# - Item format: ZoneB, ZoneC, ZoneD, ZoneA → so rates appear in order: B, C, D, A
# - Element format: ZoneA, ZoneB, ZoneC, ZoneD → standard order
# We'll detect which format by checking the header text

def extract_items_from_pdf(path: Path) -> List[Dict]:
    import PyPDF2
    pdfplumber_available = True
    try:
        import pdfplumber
    except ImportError:
        pdfplumber_available = False
    
    # Get all text first to understand format
    with open(str(path), "rb") as f:
        reader = PyPDF2.PdfReader(f)
        all_text = "\n".join(pg.extract_text() or "" for pg in reader.pages)
    
    # Detect format: "Element" vs "Item"
    is_element_format = "Element" in all_text[:2000] and "Element Code" in all_text[:2000]
    is_item_format = "Item Code" in all_text[:2000] or "SL.No ItemCode" in all_text[:2000]
    
    # Default zone detection from header
    zone_order = "standard"  # A, B, C, D
    if "Zone B" in all_text[:1000] and "Zone A" in all_text[:1000]:
        # Check which comes first
        zb_pos = all_text[:1000].find("Zone B")
        za_pos = all_text[:1000].find("Zone A")
        if zb_pos < za_pos:
            zone_order = "bcda"  # B, C, D, A order
    
    logger.info("  Format: %s, Zone order: %s", "Element" if is_element_format else "Item", zone_order)
    
    # Try pdfplumber word-level extraction
    items = []
    seen_codes: Set[str] = set()
    
    if pdfplumber_available:
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
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
                
                sorted_ys = sorted(rows.keys())
                row_texts = {}
                for y_key in sorted_ys:
                    line = " ".join(t[1] for t in sorted(rows[y_key], key=lambda x: x[0]))
                    row_texts[y_key] = line
                
                CODE_PAT = re.compile(r"(\d{2})\s*-?\s*(\d{3})\s*-?\s*(\d{2})")
                RATE_RE = re.compile(r"([\d,]+\.\d{2})")
                UNIT_SET = {"sqm", "m", "cum", "kg", "ton", "each", "job", "set", "day", "lump", "no", "nos", "hour", "month", "year"}
                
                for i, y in enumerate(sorted_ys):
                    line = row_texts[y]
                    rates = RATE_RE.findall(line)
                    if len(rates) < 4:
                        continue
                    
                    unit = ""
                    for look_y in sorted_ys[max(0,i-2):min(len(sorted_ys),i+3)]:
                        for u in UNIT_SET:
                            if u in row_texts[look_y].lower():
                                unit = u
                                break
                        if unit:
                            break
                    
                    for look_y in sorted_ys[max(0,i-3):min(len(sorted_ys),i+3)]:
                        m = CODE_PAT.search(row_texts[look_y])
                        if m:
                            code = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                            if code not in seen_codes:
                                seen_codes.add(code)
                                r0, r1, r2, r3 = [float(v.replace(",", "")) for v in rates[:4]]
                                if zone_order == "bcda":
                                    # rates order: B, C, D, A
                                    za, zb, zc, zd = r3, r0, r1, r2
                                else:
                                    # standard A, B, C, D
                                    za, zb, zc, zd = r0, r1, r2, r3
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
                            break
    
    logger.info("  Extracted %d items", len(items))
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

def merge_items(all_new, csv_items):
    existing_codes = {it["code"] for it in csv_items}
    merged = {it["code"]: dict(it) for it in csv_items}
    new_count = 0
    for it in all_new:
        if it["code"] not in merged:
            merged[it["code"]] = dict(it)
            new_count += 1
    logger.info("New from PDFs: %d, Existing: %d, Total: %d", new_count, len(csv_items), len(merged))
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
    # Process all split PDFs (skip the ones already processed: 1-50, 51-104)
    pdfs_to_process = [
        Path(r"C:\Users\znasi\Downloads\sor_BWDB(1-25).pdf"),
        Path(r"C:\Users\znasi\Downloads\sor_BWDB(1-30).pdf"),
        Path(r"C:\Users\znasi\Downloads\sor_BWDB(25-50).pdf"),
        Path(r"C:\Users\znasi\Downloads\sor_BWDB(51-75).pdf"),
        Path(r"C:\Users\znasi\Downloads\sor_BWDB(76-100).pdf"),
        Path(r"C:\Users\znasi\Downloads\sor_BWDB(101-125).pdf"),
        Path(r"C:\Users\znasi\Downloads\sor_BWDB(126-139).pdf"),
    ]
    
    all_new = []
    for pdf_path in pdfs_to_process:
        logger.info("Processing %s...", pdf_path.name)
        items = extract_items_from_pdf(pdf_path)
        all_new.extend(items)
    
    # Deduplicate
    seen = set()
    unique_new = []
    for it in all_new:
        if it["code"] not in seen:
            seen.add(it["code"])
            unique_new.append(it)
    logger.info("Total unique items from all PDFs: %d", len(unique_new))
    
    csv_items = load_existing_csv()
    merged = merge_items(unique_new, csv_items)
    
    # Check zone mapping for existing items
    logger.info("--- Zone mapping verification (sample) ---")
    for it in merged[:5]:
        logger.info("  %s: A=%.2f B=%.2f C=%.2f D=%.2f unit=%s desc=%s",
                    it["code"], it["zone_a"], it["zone_b"], it["zone_c"], it["zone_d"],
                    it["unit"], it["description"][:40] if it["description"] else "(empty)")
    
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
