"""
eExperience crawler — scrapes contract execution data from eGP public SearcheCMS.jsp.
eExperience includes contract start/end dates, completion status, and payment info.
Stored separately from eContracts in EContractExecution model.

Usage:
    python tools/crawl_eexperience.py --agency HED
    python tools/crawl_eexperience.py --all
    python tools/crawl_eexperience.py --import-db
    python tools/crawl_eexperience.py --import-db --path runtime/knowledge/eexperience/all_experience.json
"""
from __future__ import annotations

import argparse, json, logging, re, sys, time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("eexperience")

BASE = "https://www.eprocure.gov.bd"
BACKEND = Path(__file__).resolve().parent.parent / "backend"
KNOWLEDGE = BACKEND / "runtime" / "knowledge"
EEXP_DIR = KNOWLEDGE / "eexperience"

_client = httpx.Client(verify=False, timeout=30, follow_redirects=True)
AJAX_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": f"{BASE}/resources/common/SearcheCMS.jsp",
    "Origin": BASE,
    "X-Requested-With": "XMLHttpRequest",
}

DEFAULT_AGENCIES = [
    "BWDB", "LGED", "PWD", "RHD", "BBA", "EDUCATION", "BIWTA", "BADC",
    "HED", "RAILWAY", "BPDB", "WASA", "REB", "RAJUK", "DPHE", "BREB",
]

EXPECTED_HEADERS = [
    "s. no.",
    "ministry, division, organization, pe",
    "procurement nature, type & method",
    "tender/proposal id, ref no., title & publishing date",
    "contract awarded to",
    "company unique id",
    "experience certificate no",
    "contract amount (in bdt/equivalent in bdt)",
    "contract start & end date",
    "work status",
]

NOISE_MARKERS = (
    "home page", "about e-gp", "forgot password", "user login", "annual procurement plans",
    "econtracts", "eexperience", "advance search", "view all notifications", "copyright",
)
CONTRACTOR_SKIP_PATTERNS = (
    re.compile(r"\bjv\b", re.IGNORECASE),
    re.compile(r"\bjoint venture\b", re.IGNORECASE),
    re.compile(r"\bconsortium\b", re.IGNORECASE),
)


def fetch_experience_rows(keyword: str = "", page: int = 1, size: int = 100, work_status: str = "All") -> Optional[str]:
    """Fetch actual eExperience result rows from AdvSearcheCMSServlet."""
    for attempt in range(3):
        try:
            _client.get(f"{BASE}/resources/common/SearcheCMS.jsp", headers=AJAX_HEADERS, timeout=20)
            resp = _client.post(
                f"{BASE}/AdvSearcheCMSServlet",
                headers=AJAX_HEADERS,
                data={
                    "action": "geteCMSList",
                    "keyword": keyword,
                    "expCertNo": "",
                    "officeId": "",
                    "contractAwardTo": "",
                    "contractStartDtFrom": "",
                    "contractStartDtTo": "",
                    "contractEndDtFrom": "",
                    "contractEndDtTo": "",
                    "departmentId": "",
                    "tenderId": "",
                    "contractAmount": "",
                    "procurementMethod": "",
                    "procurementNature": "",
                    "contAwrdSearchOpt": "Contains",
                    "exCertSearchOpt": "Contains",
                    "exCertificateNo": "",
                    "tendererId": "",
                    "procType": "",
                    "statusTab": "All",
                    "pageNo": str(page),
                    "size": str(size),
                    "workStatus": work_status,
                },
                timeout=20,
            )
            if resp.status_code == 200 and "<tr" in resp.text:
                return resp.text
            if "noRecordFound" in resp.text or "No Records Found" in resp.text:
                return None
            if resp.status_code in (302, 303, 307, 401, 403):
                logger.warning(f"  eExperience rows returned {resp.status_code}")
                return None
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                logger.warning(f"  Row fetch failed: {e}")
    return None


def _parse_amount(raw: str) -> float:
    text = (raw or "").strip()
    if not text:
        return 0.0
    match = re.search(r"([\d,]+(?:\.\d+)?)", text)
    return float(match.group(1).replace(",", "")) if match else 0.0


def _extract_dates(raw: str) -> List[str]:
    return re.findall(r"\b\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}\b|\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b", raw or "")


def _normalize_ws(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _is_noise_text(value: str) -> bool:
    lowered = _normalize_ws(value).lower()
    return any(marker in lowered for marker in NOISE_MARKERS)


def _is_usable_contractor_name(value: str) -> bool:
    name = _normalize_ws(value)
    if len(name) < 5:
        return False
    if len(re.sub(r"[^A-Za-z]", "", name)) < 4:
        return False
    if "JV" in re.sub(r"[^A-Z]", "", name.upper()):
        return False
    if any(pattern.search(name) for pattern in CONTRACTOR_SKIP_PATTERNS):
        return False
    return not _is_noise_text(name)


def parse_experience_records(rows_html: str, agency_code: str = "") -> List[Dict[str, Any]]:
    """Parse only the actual eExperience result rows returned by AdvSearcheCMSServlet."""
    soup = BeautifulSoup(f"<table>{rows_html}</table>", "html.parser")
    rows = soup.find_all("tr")
    records: List[Dict[str, Any]] = []
    for row in rows:
        cells = row.find_all("td")
        if len(cells) != len(EXPECTED_HEADERS):
            continue
        row_text = [_normalize_ws(c.get_text(" ", strip=True)) for c in cells]
        if row_text[0].lower() in {"s. no.", "s.no.", "sl. no."}:
            continue
        if not row_text[0].isdigit():
            continue

        pe_office = row_text[1]
        title_block = row_text[3]
        contractor_name = row_text[4]
        status = row_text[9]
        if _is_noise_text(pe_office) or _is_noise_text(title_block) or _is_noise_text(contractor_name):
            continue
        if status not in {"Completed", "Ongoing"}:
            continue

        tender_match = re.search(r"^\s*(\d{6,})\s*,", title_block)
        ref_match = re.search(r"^\s*\d{6,}\s*,\s*(.*?)\s*,?\s*Date\s*[:.-]", title_block, re.IGNORECASE)
        if not ref_match:
            ref_match = re.search(r"^\s*\d{6,}\s*,\s*(.*?)\s+\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}$", title_block, re.IGNORECASE)
        title_link = row.find("a")
        title = _normalize_ws(title_link.get_text(" ", strip=True) if title_link else title_block)
        dates = _extract_dates(row_text[8])
        published_dates = _extract_dates(title_block)
        work_status = status
        progress_pct = 100.0 if status == "Completed" else 0.0
        if not _is_usable_contractor_name(contractor_name):
            continue
        record = {
            "tender_id": tender_match.group(1) if tender_match else "",
            "package_no": _normalize_ws(ref_match.group(1)) if ref_match else "",
            "title": title,
            "pe_office": pe_office,
            "agency_code": agency_code,
            "procurement_method": row_text[2],
            "contractor_name": contractor_name,
            "company_unique_id": row_text[5],
            "experience_certificate_no": row_text[6],
            "contract_value_bdt": _parse_amount(row_text[7]),
            "contract_start_date": dates[0] if len(dates) > 0 else "",
            "contract_end_date": dates[1] if len(dates) > 1 else "",
            "planned_completion_date": dates[1] if len(dates) > 1 else "",
            "actual_completion_date": dates[1] if status == "Completed" and len(dates) > 1 else "",
            "published_date": published_dates[-1] if published_dates else "",
            "completion_status": status.lower(),
            "work_status": work_status,
            "status": status.lower(),
            "progress_pct": progress_pct,
            "completed_on_time": None,
            "source": "EEXPERIENCE",
            "raw_row": row_text,
        }
        records.append(record)

    logger.debug("  Parsed %s qualified experience rows", len(records))
    return records

def clean_record(rec: Dict) -> Dict:
    """Normalize eExperience record fields."""
    cleaned = {
        "tender_id": str(rec.get("tender_id", "")).strip(),
        "package_no": str(rec.get("package_no", "")).strip()[:300],
        "title": str(rec.get("title", "")).strip()[:500],
        "agency_code": rec.get("agency_code", ""),
        "pe_office": str(rec.get("pe_office", "")).strip(),
        "contractor_name": str(rec.get("contractor_name", "")).strip(),
        "contract_value_bdt": float(rec.get("contract_value_bdt", 0)),
        "contract_start_date": normalize_date(rec.get("contract_start_date", "")),
        "contract_end_date": normalize_date(rec.get("contract_end_date", "")),
        "planned_completion_date": normalize_date(rec.get("planned_completion_date", "")),
        "actual_completion_date": normalize_date(rec.get("actual_completion_date", "")),
        "completion_status": str(rec.get("completion_status", rec.get("status", ""))).strip()[:50],
        "work_status": str(rec.get("work_status", "")).strip()[:100],
        "status": str(rec.get("status", "completed")).strip()[:50],
        "progress_pct": float(rec.get("progress_pct", 0) or 0),
        "completed_on_time": rec.get("completed_on_time"),
        "completion_certificate_no": str(rec.get("experience_certificate_no", "")).strip()[:200],
        "company_unique_id": str(rec.get("company_unique_id", "")).strip()[:100],
        "procurement_method": str(rec.get("procurement_method", "")).strip()[:120],
        "published_date": normalize_date(rec.get("published_date", "")),
        "district": "",
        "source_url": "",
        "award_date": "",
        "raw_payload": rec,
    }
    return cleaned


def is_valid_completed_work_record(rec: Dict[str, Any]) -> bool:
    title = _normalize_ws(str(rec.get("title", "")))
    pe_office = _normalize_ws(str(rec.get("pe_office", "")))
    contractor = _normalize_ws(str(rec.get("contractor_name", "")))
    status = _normalize_ws(str(rec.get("work_status") or rec.get("completion_status") or rec.get("status", "")))
    amount = float(rec.get("contract_value_bdt", 0) or 0)
    has_dates = bool(rec.get("contract_start_date") and rec.get("contract_end_date"))
    if not title or not pe_office or not contractor:
        return False
    if _is_noise_text(title) or _is_noise_text(pe_office) or _is_noise_text(contractor):
        return False
    if status not in {"Completed", "Ongoing", "completed", "ongoing"}:
        return False
    if amount <= 0:
        return False
    if not has_dates:
        return False
    return True

DATE_FORMATS = [
    "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%b-%Y",
    "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%d-%b-%y",
]

def normalize_date(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    raw = raw.replace("Sept", "Sep")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw[:20].strip(), fmt).date().isoformat()
        except (ValueError, IndexError):
            continue
    return raw[:10]

def crawl_agency(agency_code: str, keyword: str = "", max_pages: int = 200) -> List[Dict]:
    """Crawl eExperience for a single agency."""
    kw = keyword or agency_code
    logger.info(f"[{agency_code}] Crawling eExperience (keyword='{kw}')")

    all_records = []
    seen_keys = set()

    for page in range(1, max_pages + 1):
        rows_html = fetch_experience_rows(kw, page, size=100, work_status="All")
        if rows_html is None:
            break
        records = parse_experience_records(rows_html, agency_code)
        if not records:
            break
        for rec in records:
            cleaned = clean_record(rec)
            if not is_valid_completed_work_record(cleaned):
                continue
            key = f"{cleaned['tender_id']}-{cleaned['contractor_name']}-{cleaned['contract_start_date']}"
            if key not in seen_keys:
                seen_keys.add(key)
                all_records.append(cleaned)
        logger.info(f"  [{agency_code}] Page {page}: {len(records)} rows, {len(all_records)} total")
        if len(records) < 100:
            break
        time.sleep(0.5)

    # Save per-agency JSON
    agency_dir = EEXP_DIR / agency_code
    agency_dir.mkdir(parents=True, exist_ok=True)
    fp = agency_dir / "experience.json"
    fp.write_text(json.dumps(all_records, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"  [{agency_code}] Saved {len(all_records)} records to {fp}")

    return all_records

def import_to_db(json_path: Optional[str] = None):
    """Import eExperience JSON into EContractExecution model."""
    sys.path.insert(0, str(BACKEND))
    import asyncio
    from app.db.base import get_async_session, init_db, close_db
    from app.services.intelligence_data_service import IntelligenceDataService

    fp = Path(json_path) if json_path else (EEXP_DIR / "all_experience.json")

    async def _import():
        await init_db()
        async for db in get_async_session():
            svc = IntelligenceDataService(db)
            count = await svc.import_eexperience_from_json(fp)
            await db.commit()
            logger.info(f"Imported {count} eExperience records from {fp}")
            return count

    return asyncio.run(_import())

def main():
    parser = argparse.ArgumentParser(description="Crawl eExperience data from eGP")
    parser.add_argument("--agency", help="Comma-separated agency codes")
    parser.add_argument("--all", action="store_true", help="Crawl all default agencies")
    parser.add_argument("--import-db", action="store_true", help="Import JSON -> DB")
    parser.add_argument("--path", help="JSON path for import-db")
    parser.add_argument("--max-pages", type=int, default=500)
    args = parser.parse_args()

    if args.import_db:
        import_to_db(args.path)
        return

    agencies: List[str] = []
    if args.all:
        agencies = DEFAULT_AGENCIES
    elif args.agency:
        agencies = [a.strip() for a in args.agency.split(",")]
    else:
        parser.print_help()
        sys.exit(1)

    all_records = []
    for code in agencies:
        records = crawl_agency(code, max_pages=args.max_pages)
        all_records.extend(records)

    # Save combined file
    EEXP_DIR.mkdir(parents=True, exist_ok=True)
    combined_fp = EEXP_DIR / "all_experience.json"
    combined_fp.write_text(json.dumps(all_records, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"\nSaved {len(all_records)} total records to {combined_fp}")

if __name__ == "__main__":
    main()
