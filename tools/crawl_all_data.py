"""
Crawl 40% of ALL eGP data from two separate tabs:
  eTenders tab → completed works (all agencies, no keyword filter)
  eCMS tab    → ongoing package details (all agencies, no keyword filter)
Keeps them unmerged — separate JSON directories + source-tagged DB import.
"""
from __future__ import annotations

import argparse, json, logging, re, sys, time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("all-data")

BASE = "https://www.eprocure.gov.bd"
BACKEND = Path(__file__).resolve().parent.parent / "backend"
KNOWLEDGE = BACKEND / "runtime" / "knowledge"
ALL_DIR = KNOWLEDGE / "eexperience_all"

_client = httpx.Client(verify=False, timeout=30, follow_redirects=True)
AJAX_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": f"{BASE}/resources/common/SearcheCMS.jsp",
    "Origin": BASE,
    "X-Requested-With": "XMLHttpRequest",
}

NOISE_MARKERS = (
    "home page", "about e-gp", "forgot password", "user login", "annual procurement plans",
    "econtracts", "eexperience", "advance search", "view all notifications", "copyright",
)
CONTRACTOR_SKIP_PATTERNS = (
    re.compile(r"\bjv\b", re.IGNORECASE),
    re.compile(r"\bjoint venture\b", re.IGNORECASE),
    re.compile(r"\bconsortium\b", re.IGNORECASE),
)

# ---- helpers ----
def _parse_amount(raw: str) -> float:
    text = (raw or "").strip()
    if not text:
        return 0.0
    m = re.search(r"([\d,]+(?:\.\d+)?)", text)
    return float(m.group(1).replace(",", "")) if m else 0.0

def _extract_dates(raw: str) -> List[str]:
    return re.findall(
        r"\b\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}\b|\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b",
        raw or "",
    )

def _normalize_ws(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())

def _is_noise(value: str) -> bool:
    return any(m in _normalize_ws(value).lower() for m in NOISE_MARKERS)

def _is_usable_contractor(value: str) -> bool:
    name = _normalize_ws(value)
    if len(name) < 5 or len(re.sub(r"[^A-Za-z]", "", name)) < 4:
        return False
    if any(p.search(name) for p in CONTRACTOR_SKIP_PATTERNS):
        return False
    return not _is_noise(name)

# ---- fetch & parse ----
def fetch_page(status_tab: str, page: int, size: int = 100, work_status: str = "All") -> Optional[str]:
    for attempt in range(3):
        try:
            _client.get(f"{BASE}/resources/common/SearcheCMS.jsp", headers=AJAX_HEADERS, timeout=20)
            resp = _client.post(
                f"{BASE}/AdvSearcheCMSServlet",
                headers=AJAX_HEADERS,
                data={
                    "action": "geteCMSList",
                    "keyword": "",
                    "expCertNo": "", "officeId": "",
                    "contractAwardTo": "", "contractStartDtFrom": "",
                    "contractStartDtTo": "", "contractEndDtFrom": "",
                    "contractEndDtTo": "", "departmentId": "",
                    "tenderId": "", "contractAmount": "",
                    "procurementMethod": "", "procurementNature": "",
                    "contAwrdSearchOpt": "Contains",
                    "exCertSearchOpt": "Contains",
                    "exCertificateNo": "", "tendererId": "",
                    "procType": "",
                    "statusTab": status_tab,
                    "pageNo": str(page),
                    "size": str(size),
                    "workStatus": work_status,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                if "<tr" in resp.text:
                    return resp.text
                if "noRecordFound" in resp.text:
                    return None
            if resp.status_code in (302, 303, 307, 401, 403):
                return None
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                logger.warning(f"  Page fetch failed: {e}")
    return None

def parse_records(rows_html: str, source: str = "EEXPERIENCE_ALL") -> List[Dict[str, Any]]:
    soup = BeautifulSoup(f"<table>{rows_html}</table>", "html.parser")
    rows = soup.find_all("tr")
    records: List[Dict[str, Any]] = []

    expected_cols = 10
    for row in rows:
        cells = row.find_all("td")
        if len(cells) != expected_cols:
            continue
        text = [_normalize_ws(c.get_text(" ", strip=True)) for c in cells]
        if text[0].lower() in {"s. no.", "s.no.", "sl. no."}:
            continue
        if not text[0].isdigit():
            continue

        pe_office = text[1]
        title_block = text[3]
        contractor_name = text[4]
        status = text[9]

        if _is_noise(pe_office) or _is_noise(title_block) or _is_noise(contractor_name):
            continue
        if status not in {"Completed", "Ongoing"}:
            continue
        if not _is_usable_contractor(contractor_name):
            continue

        tender_match = re.search(r"^\s*(\d{6,})\s*,", title_block)
        # Extract ref_no: text between tender_id and title (from <a> tag or next uppercase word)
        title_link = row.find("a")
        # Get the raw cell HTML to split ref_no from title
        cell_html = str(cells[3])
        # Try to find a br tag or text before the anchor
        ref_no = ""
        title_text = _normalize_ws(title_link.get_text(" ", strip=True) if title_link else "")
        if title_link:
            # Extract text before the anchor in the cell
            before_a = cell_html.split("<a", 1)[0] if "<a" in cell_html else ""
            # Get the ref_no from before the anchor
            raw_before = BeautifulSoup(before_a, "html.parser").get_text(" ", strip=True)
            # Remove tender_id prefix
            ref_parts = re.sub(r"^\s*\d{6,}\s*,\s*", "", raw_before).strip()
            # Take only up to a reasonable length, remove trailing commas/dashes
            ref_no = re.sub(r"[,;\-]+$", "", ref_parts).strip()
        # Fallback: use regex
        if not ref_no:
            ref_match = re.search(
                r"^\s*\d{6,}\s*,\s*([^,]+?)\s{2,}", title_block
            )
            if ref_match:
                ref_no = ref_match.group(1).strip()
            else:
                ref_match = re.search(
                    r"^\s*\d{6,}\s*,\s*(.*?)\s+\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}$",
                    title_block, re.IGNORECASE,
                )
                if ref_match:
                    ref_no = ref_match.group(1).strip()
                    # Strip title from ref_no if title is known
                    if title_text and ref_no.endswith(title_text):
                        ref_no = ref_no[:-len(title_text)].strip()
                    # Truncate to 250 chars max
                    ref_no = ref_no[:250]
        title = title_text if title_text else title_block
        dates = _extract_dates(text[8])
        published_dates = _extract_dates(title_block)

        record = {
            "tender_id": tender_match.group(1) if tender_match else "",
            "package_no": ref_no[:250] if ref_no else "",
            "title": title,
            "pe_office": pe_office,
            "agency_code": "",
            "procurement_method": text[2],
            "contractor_name": contractor_name,
            "company_unique_id": text[5],
            "experience_certificate_no": text[6],
            "contract_value_bdt": _parse_amount(text[7]),
            "contract_start_date": dates[0] if len(dates) > 0 else "",
            "contract_end_date": dates[1] if len(dates) > 1 else "",
            "planned_completion_date": dates[1] if len(dates) > 1 else "",
            "actual_completion_date": dates[1] if status == "Completed" and len(dates) > 1 else "",
            "published_date": published_dates[-1] if published_dates else "",
            "completion_status": status.lower(),
            "work_status": status,
            "status": status.lower(),
            "progress_pct": 100.0 if status == "Completed" else 0.0,
            "completed_on_time": None,
            "source": source,
        }
        records.append(record)
    return records

# ---- crawl ----
def fetch_total_pages(status_tab: str) -> int:
    """Get total page count from the server."""
    html = fetch_page(status_tab, 1, size=100)
    if not html:
        return 0
    m = re.search(r'id="totalPages"[^>]*value="(\d+)"', html)
    return int(m.group(1)) if m else 1

def crawl_tab(status_tab: str, source: str, max_pages: int, page_size: int = 100) -> List[Dict]:
    """Crawl ALL data from a given tab (no keyword filter)."""
    total_available = fetch_total_pages(status_tab)
    pages_to_crawl = min(max_pages, total_available) if max_pages > 0 else total_available
    logger.info(f"[{status_tab}] Total pages: {total_available}, crawling {pages_to_crawl} pages ({source})")

    all_records: List[Dict] = []
    seen_keys = set()
    tab_dir = "completed" if status_tab == "eTenders" else ("ongoing" if status_tab == "eCMS" else status_tab.lower())
    checkpoint_path = ALL_DIR / tab_dir / "checkpoint.json"

    # Resume from checkpoint if exists
    start_page = 1
    if checkpoint_path.exists():
        ckpt = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        all_records = ckpt.get("records", [])
        seen_keys = set(ckpt.get("seen_keys", []))
        start_page = ckpt.get("last_page", 0) + 1
        logger.info(f"  [{status_tab}] Resuming from page {start_page} ({len(all_records)} records in checkpoint)")

    for page in range(start_page, pages_to_crawl + 1):
        rows_html = fetch_page(status_tab, page, size=page_size)
        if rows_html is None:
            logger.info(f"  [{status_tab}] No more records at page {page}")
            break
        records = parse_records(rows_html, source=source)
        if not records:
            logger.info(f"  [{status_tab}] Empty page {page}, stopping")
            break
        new_count = 0
        for rec in records:
            key = f"{rec['tender_id']}-{rec['contractor_name']}-{rec['contract_start_date']}"
            if key not in seen_keys:
                seen_keys.add(key)
                all_records.append(rec)
                new_count += 1
        if page % 50 == 0 or page == pages_to_crawl:
            logger.info(f"  [{status_tab}] Page {page}/{pages_to_crawl}: +{new_count} new, {len(all_records)} total")
        # Checkpoint every 100 pages
        if page % 100 == 0:
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            checkpoint_path.write_text(json.dumps({"last_page": page, "seen_keys": list(seen_keys), "records": all_records}, ensure_ascii=False), encoding="utf-8")
            logger.info(f"  [{status_tab}] Checkpoint saved at page {page}")
        if new_count == 0 and len(records) > 0:
            logger.info(f"  [{status_tab}] All records on page {page} are duplicates, stopping")
            break
        time.sleep(0.3)

    # Remove checkpoint on success
    if checkpoint_path.exists():
        checkpoint_path.unlink()

    return all_records

def save_json(data: List[Dict], filepath: Path, label: str = ""):
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"[{label}] Saved {len(data)} records to {filepath}")

def import_to_db(json_path: Path, source: str):
    """Import one JSON file into DB."""
    sys.path.insert(0, str(BACKEND))
    import asyncio
    from app.db.base import get_async_session, init_db, close_db
    from app.services.intelligence_data_service import IntelligenceDataService

    async def _import():
        await init_db()
        async for db in get_async_session():
            svc = IntelligenceDataService(db)
            count = await svc.import_eexperience_from_json(json_path)
            await db.commit()
            logger.info(f"[{source}] Imported {count} records from {json_path}")
            return count
    return asyncio.run(_import())

def main():
    parser = argparse.ArgumentParser(description="Crawl 40% of ALL eGP data from eTenders (completed) + eCMS (ongoing)")
    parser.add_argument("--completed-only", action="store_true", help="Only crawl eTenders completed works")
    parser.add_argument("--ongoing-only", action="store_true", help="Only crawl eCMS ongoing packages")
    parser.add_argument("--import-db", action="store_true", help="Import all saved JSON into DB")
    parser.add_argument("--pct", type=float, default=0.4, help="Percentage to crawl (default 0.4 = 40%%)")
    parser.add_argument("--page-size", type=int, default=100, help="Rows per page (default 100)")
    args = parser.parse_args()

    if args.import_db:
        completed_fp = ALL_DIR / "completed" / "all_completed.json"
        ongoing_fp = ALL_DIR / "ongoing" / "all_ongoing.json"
        if completed_fp.exists():
            import_to_db(completed_fp, "EEXPERIENCE_ALL")
        else:
            logger.warning(f"Completed file not found: {completed_fp}")
        if ongoing_fp.exists():
            import_to_db(ongoing_fp, "ECMS_ONGOING")
        else:
            logger.warning(f"Ongoing file not found: {ongoing_fp}")
        return

    do_completed = not args.ongoing_only
    do_ongoing = not args.completed_only

    # Get total pages to calculate 40%
    completed_total = fetch_total_pages("eTenders") if do_completed else 0
    ongoing_total = fetch_total_pages("eCMS") if do_ongoing else 0

    completed_pages = int(completed_total * args.pct) if completed_total else 0
    ongoing_pages = int(ongoing_total * args.pct) if ongoing_total else 0

    logger.info("=" * 60)
    logger.info(f"eTenders (completed) total pages: {completed_total}")
    logger.info(f"  → Crawling {args.pct*100:.0f}% = {completed_pages} pages")
    logger.info(f"eCMS (ongoing) total pages: {ongoing_total}")
    logger.info(f"  → Crawling {args.pct*100:.0f}% = {ongoing_pages} pages")
    logger.info("=" * 60)

    if do_completed:
        logger.info("--- Crawling eTenders (completed works) ---")
        completed = crawl_tab("eTenders", "EEXPERIENCE_ALL", completed_pages, args.page_size)
        completed_fp = ALL_DIR / "completed" / "all_completed.json"
        save_json(completed, completed_fp, "EEXPERIENCE_ALL")
        # Also save a combined all_experience.json in the usual location for compatibility
        combined_fp = ALL_DIR / "all_completed.json"
        save_json(completed, combined_fp, "EEXPERIENCE_ALL")

    if do_ongoing:
        logger.info("--- Crawling eCMS (ongoing packages) ---")
        ongoing = crawl_tab("eCMS", "ECMS_ONGOING", ongoing_pages, args.page_size)
        ongoing_fp = ALL_DIR / "ongoing" / "all_ongoing.json"
        save_json(ongoing, ongoing_fp, "ECMS_ONGOING")
        combined_fp = ALL_DIR / "all_ongoing.json"
        save_json(ongoing, combined_fp, "ECMS_ONGOING")

if __name__ == "__main__":
    main()
