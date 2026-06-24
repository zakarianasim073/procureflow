"""
Multi-agency eContracts crawler for newly discovered agencies.
Crawls SearchNoaServlet per agency, fetches detail pages,
outputs per-agency flat.json for DB import.

Usage:
    python tools/crawl_econtracts_new.py --agency HED,RAILWAY,BPDB
    python tools/crawl_econtracts_new.py --all-new
    python tools/crawl_econtracts_new.py --import-db
"""
from __future__ import annotations

import argparse, json, logging, re, sys, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("econtracts_new")

BASE = "https://www.eprocure.gov.bd"
BACKEND = Path(__file__).resolve().parent.parent / "backend"
KNOWLEDGE = BACKEND / "runtime" / "knowledge"
RUNTIME = BACKEND / "runtime"

EXCLUDED = {"BWDB", "LGED", "PWD", "RHD", "BBA", "EDUCATION", "BIWTA", "BADC", "DISASTER", "POWER"}

_client = httpx.Client(verify=False, timeout=30, follow_redirects=True)

BANGLADESH_DISTRICTS = [
    "bagerhat", "bandarban", "barguna", "barisal", "bhola", "bogra",
    "brahmanbaria", "chandpur", "chapainawabganj", "chittagong",
    "chuadanga", "comilla", "cox's bazar", "dhaka", "dinajpur", "faridpur",
    "feni", "gaibandha", "gazipur", "gopalganj", "habiganj", "jamalpur",
    "jessore", "jhalokati", "jhenaidah", "joypurhat", "khagrachhari",
    "khulna", "kishoreganj", "kurigram", "kushtia", "lakshmipur",
    "lalmonirhat", "madaripur", "magura", "manikganj", "maulvibazar",
    "meherpur", "munshiganj", "mymensingh", "naogaon", "narail",
    "narayanganj", "narsingdi", "natore", "netrokona", "nilphamari",
    "noakhali", "pabna", "panchagarh", "patuakhali", "pirojpur",
    "rajbari", "rajshahi", "rangamati", "rangpur", "sathkhira",
    "shariatpur", "sherpur", "sirajganj", "sunamganj", "sylhet",
    "tangail", "thakurgaon",
]

def detect_district(text: str) -> str:
    t = re.sub(r'[^a-zA-Z\s]', ' ', text).lower()
    for d in BANGLADESH_DISTRICTS:
        if d in t:
            return d.title()
    return ""

def fetch_noa_page(agency_keyword: str, page: int, size: int = 50) -> Optional[str]:
    for attempt in range(3):
        try:
            resp = _client.post(
                f"{BASE}/SearchNoaServlet",
                data={"keyword": agency_keyword, "pageNo": str(page), "size": str(size)},
                timeout=15,
            )
            if resp.status_code == 200 and len(resp.text) > 100:
                return resp.text
            if "No Records Found" in resp.text:
                return None
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                logger.warning(f"  Page {page} failed: {e}")
    return None

def parse_noa_rows(html: str, agency_code: str, page: int) -> List[Dict]:
    records = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)
    for row_html in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)
        if len(cells) < 8:
            continue
        clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        if re.match(r"^(sl|no|serial|s\.?\s*no)", clean[0], re.I):
            continue

        col2 = clean[2] if len(clean) > 2 else ""
        title_match = re.search(r"(\d{6,})[, ]*(.*)", col2)
        tender_id = title_match.group(1) if title_match else ""
        title = title_match.group(2).strip()[:300] if title_match else col2[:200]

        detail_url = ""
        url_m = re.search(r'href="([^"]*ViewAwardedContracts[^"]*)"', cells[2])
        if url_m:
            detail_url = url_m.group(1)

        col3 = clean[3] if len(clean) > 3 else ""
        pe_parts = col3.split("\n") if "\n" in col3 else [col3, ""]
        procuring_entity = pe_parts[0].strip()
        procurement_method = pe_parts[-1].strip() if len(pe_parts) > 1 else ""

        district_raw = clean[4] if len(clean) > 4 else ""
        award_date_raw = clean[5] if len(clean) > 5 else ""
        winner = clean[6] if len(clean) > 6 else ""
        amount_raw = clean[7] if len(clean) > 7 else "0"

        amount_bdt = 0.0
        try:
            val = re.sub(r"[^\d.]", "", amount_raw)
            if val:
                amount_bdt = float(val) * 10_000_000
        except ValueError:
            pass

        if not tender_id:
            continue

        pe_parts2 = [p.strip() for p in procuring_entity.split(",")]
        pe_office = pe_parts2[0] if pe_parts2 else ""
        district = detect_district(procuring_entity) or district_raw.strip()

        records.append({
            "tender_id": tender_id,
            "title": title,
            "procuring_entity": procuring_entity,
            "procurement_method": procurement_method,
            "district": district,
            "pe_office": pe_office,
            "award_date": award_date_raw.strip(),
            "winner": winner.strip(),
            "amount_bdt": amount_bdt,
            "detail_url": detail_url,
            "agency_code": agency_code,
            "source": "ECONTRACT_NEW",
            "noa_page": page,
        })
    return records

def fetch_detail(tender_id: str, pkg_lot_id: str = "") -> Optional[Dict]:
    url = f"{BASE}/resources/common/ViewAwardedContracts.jsp?tenderid={tender_id}"
    if pkg_lot_id:
        url += f"&pkgLotId={pkg_lot_id}"
    for attempt in range(3):
        try:
            resp = _client.get(url, timeout=15)
            if resp.status_code == 200 and len(resp.text) > 200:
                return parse_detail_html(resp.text)
        except Exception as e:
            if attempt < 2:
                time.sleep(1)
    return None

def parse_detail_html(html: str) -> Dict:
    result = {}
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.DOTALL)
    for table in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.DOTALL)
        for row in rows:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            if len(cells) < 2:
                continue
            key = cells[0].strip().lower()
            val = cells[1].strip()
            if "package" in key and "no" in key:
                result["package_no"] = val
            elif "contract value" in key or "award" in key or "amount" in key:
                result["amount"] = val
            elif "economic operator" in key or "awarded" in key or "winner" in key:
                result["winner"] = val
            elif "procurement method" in key:
                result["procurement_method"] = val
            elif "procuring entity" in key:
                result["procuring_entity"] = val
            elif "date of notification" in key:
                result["award_date"] = val
    return result

def get_cache_dir(agency_code: str) -> Path:
    d = KNOWLEDGE / "econtracts" / agency_code
    d.mkdir(parents=True, exist_ok=True)
    return d

def save_flat(agency_code: str, records: List[Dict]):
    cache_dir = get_cache_dir(agency_code)
    fp = cache_dir / "flat.json"
    fp.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"  Saved {len(records)} records to {fp}")

def crawl_agency(agency_code: str, keyword: str = "", max_pages: int = 500) -> int:
    kw = keyword or agency_code
    logger.info(f"[{agency_code}] Crawling eContracts (keyword='{kw}', max_pages={max_pages})")
    cache_dir = get_cache_dir(agency_code)
    all_records: List[Dict] = []
    seen_keys: Set[str] = set()

    for page in range(1, max_pages + 1):
        html = fetch_noa_page(kw, page)
        if html is None:
            logger.info(f"  [{agency_code}] No more data at page {page}")
            break
        records = parse_noa_rows(html, agency_code, page)
        if not records:
            logger.info(f"  [{agency_code}] Empty page {page}, stopping")
            break
        new_records = []
        for r in records:
            key = f"{r['tender_id']}-{r['winner']}-{r['award_date']}"
            if key not in seen_keys:
                seen_keys.add(key)
                new_records.append(r)
        logger.info(f"  [{agency_code}] Page {page}: {len(records)} rows, {len(new_records)} new")
        if new_records:
            all_records.extend(new_records)
        if len(records) < 50:
            logger.info(f"  [{agency_code}] Partial page ({len(records)}), assuming end")
            break
        time.sleep(0.3)

    # Enrich with detail page data
    logger.info(f"  [{agency_code}] Fetching detail pages for {len(all_records)} records...")
    enriched = []
    for i, rec in enumerate(all_records):
        if i > 0 and i % 100 == 0:
            logger.info(f"  [{agency_code}] Detail progress: {i}/{len(all_records)}")
        detail = fetch_detail(rec["tender_id"])
        if detail:
            if detail.get("package_no") and not rec["title"]:
                rec["title"] = detail["package_no"]
            rec["package_no"] = detail.get("package_no", "")
            rec["procurement_method"] = detail.get("procurement_method", rec["procurement_method"])
        time.sleep(0.1)
        enriched.append(rec)

    if enriched:
        save_flat(agency_code, enriched)
    else:
        logger.info(f"  [{agency_code}] No records found")
    return len(enriched)

def import_to_db(agency_codes: List[str]):
    """Import per-agency flat.json files into the database."""
    sys.path.insert(0, str(BACKEND))
    import asyncio
    from app.db.base import get_async_session, init_db, close_db
    from app.services.intelligence_data_service import IntelligenceDataService

    async def _import():
        await init_db()
        async for db in get_async_session():
            svc = IntelligenceDataService(db)
            total = 0
            for code in agency_codes:
                fp = get_cache_dir(code) / "flat.json"
                if not fp.exists():
                    logger.warning(f"  No flat.json for {code}, skipping")
                    continue
                count = await svc.import_awards_from_json(fp)
                logger.info(f"  Imported {count} awards for {code}")
                total += count
            await db.commit()
            logger.info(f"Total imported: {total}")
            return total

    return asyncio.run(_import())

def main():
    parser = argparse.ArgumentParser(description="Crawl eContracts for new agencies")
    parser.add_argument("--agency", help="Comma-separated agency codes (e.g. HED,RAILWAY)")
    parser.add_argument("--all-new", action="store_true", help="Crawl all non-excluded agencies found in discovered_agencies.json")
    parser.add_argument("--import-db", action="store_true", help="Import flat.json -> DB instead of crawling")
    parser.add_argument("--max-pages", type=int, default=500, help="Max pages per agency")
    args = parser.parse_args()

    if args.import_db:
        discovered_fp = KNOWLEDGE / "discovered_agencies" / "discovered_agencies.json"
        if discovered_fp.exists():
            agencies = [r["agency_code"] for r in json.loads(discovered_fp.read_text(encoding="utf-8"))]
        elif args.agency:
            agencies = [a.strip() for a in args.agency.split(",")]
        else:
            agencies = []
        if agencies:
            import_to_db(agencies)
        return

    agency_codes: List[str] = []
    if args.all_new:
        discovered_fp = KNOWLEDGE / "discovered_agencies" / "discovered_agencies.json"
        if discovered_fp.exists():
            discovered = json.loads(discovered_fp.read_text(encoding="utf-8"))
            agency_codes = [r["agency_code"] for r in discovered if r["agency_code"] not in EXCLUDED]
        else:
            logger.error("discovered_agencies.json not found. Run crawl_discover_agencies.py first.")
            sys.exit(1)
    elif args.agency:
        agency_codes = [a.strip() for a in args.agency.split(",")]
    else:
        parser.print_help()
        sys.exit(1)

    for code in agency_codes:
        if code in EXCLUDED:
            logger.info(f"Skipping excluded agency {code}")
            continue
        total = crawl_agency(code, max_pages=args.max_pages)
        logger.info(f"[{code}] Done: {total} records")

if __name__ == "__main__":
    main()
