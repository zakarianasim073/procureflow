"""
Clean APP JSON files: remove corrupted keyword-crawl records.
Only keep office-crawl records (which have _office_search=True and proper app_code/package_no).
"""
import json, logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("clean_app")

KNOWLEDGE = Path(__file__).resolve().parent.parent / "backend" / "runtime" / "knowledge"
APP_DIR = KNOWLEDGE / "app"

total_removed = 0
total_kept = 0

for fp in sorted(APP_DIR.glob("*.json")):
    if fp.name.startswith("offices_") or fp.name == "dept_tree.json":
        continue
    
    recs = json.loads(fp.read_text(encoding="utf-8"))
    if not isinstance(recs, list):
        logger.warning(f"Skipping {fp.name} (not a list)")
        continue
    
    before = len(recs)
    kept = []
    removed_keyword = 0
    removed_no_data = 0
    
    for r in recs:
        if not isinstance(r, dict):
            removed_no_data += 1
            continue
        
        # Office-crawl records have _office_search=True
        if r.get("_office_search"):
            kept.append(r)
            continue
        
        # Also keep records with non-empty app_code and valid tender_id
        ac = (r.get("app_code") or "").strip()
        tid = (r.get("tender_id") or "").strip()
        pkg = (r.get("package_no") or "").strip()
        est = r.get("estimated_amount_bdt", 0) or 0
        
        # Keyword-crawl records have bad data: synthetic TID, scrambled fields
        # Detect by: _source_keyword flag, or synthetic TID format "APP-XXXX-"
        is_keyword = bool(r.get("_source_keyword"))
        is_synthetic_tid = bool(tid and tid.startswith("APP-"))
        has_code = bool(ac)
        
        if is_keyword or is_synthetic_tid:
            removed_keyword += 1
            continue
        
        # Keep records that look valid even without _office_search
        if has_code and tid and pkg and est > 0:
            kept.append(r)
        else:
            removed_no_data += 1
    
    after = len(kept)
    total_removed += (before - after)
    total_kept += after
    
    # Write cleaned file
    fp.write_text(json.dumps(kept, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"{fp.name}: {before} -> {after} records (-{before-after}: {removed_keyword} keyword, {removed_no_data} invalid)")

logger.info(f"Total: {total_kept} kept, {total_removed} removed")
