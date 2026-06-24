"""
Enterprise-grade eContracts crawler: per-agency, incremental, structured output.
Crawls SearchNoaServlet for each target agency, caches pages, fetches details,
produces clean structured hierarchy:

  Ministry → Agency → PE Office → District → Location → Contractor → contracts[]
"""
from __future__ import annotations

import json, logging, re, sys, time
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("econtracts_crawler")

BASE = "https://www.eprocure.gov.bd"
KNOWLEDGE = Path(__file__).resolve().parent.parent / "backend" / "runtime" / "knowledge"

# ── Agency Configuration ──────────────────────────────────────────────
AGENCY_CONFIG = {
    "BWDB": {
        "keyword": "BWDB",
        "ministry": "Ministry of Water Resources",
        "name": "Bangladesh Water Development Board",
    },
    "LGED": {
        "keyword": "LGED",
        "ministry": "Ministry of Local Government, Rural Development and Co-operatives",
        "name": "Local Government Engineering Department",
    },
    "PWD": {
        "keyword": "PWD",
        "ministry": "Ministry of Housing and Public Works",
        "name": "Public Works Department",
    },
    "RHD": {
        "keyword": "RHD",
        "ministry": "Ministry of Road Transport and Bridges",
        "name": "Roads and Highways Department",
    },
    "BBA": {
        "keyword": "BBA",
        "ministry": "Ministry of Road Transport and Bridges",
        "name": "Bangladesh Bridge Authority",
    },
    "EDUCATION": {
        "keyword": "Education Engineering",
        "ministry": "Ministry of Education",
        "name": "Education Engineering Directorate",
    },
    "BIWTA": {
        "keyword": "BIWTA",
        "ministry": "Ministry of Shipping",
        "name": "Bangladesh Inland Water Transport Authority",
    },
    "BADC": {
        "keyword": "BADC",
        "ministry": "Ministry of Agriculture",
        "name": "Bangladesh Agricultural Development Corporation",
    },
    "DISASTER": {
        "keyword": "Disaster",
        "ministry": "Ministry of Disaster Management and Relief",
        "name": "Disaster Management Department",
    },
    "POWER": {
        "keyword": "PGCB",
        "ministry": "Ministry of Power, Energy and Mineral Resources",
        "name": "Power Grid Company of Bangladesh",
    },
}

TARGET_AGENCIES = set(AGENCY_CONFIG.keys())

# ── District List ─────────────────────────────────────────────────────
BANGLADESH_DISTRICTS = [
    "bagerhat", "bandarban", "barguna", "barisal", "bhola", "bogra",
    "brahmanbaria", "chandpur", "chapainawabganj", "chittagong", "chittagong",
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

def parse_procuring_entity(pe: str) -> Dict[str, str]:
    if not pe:
        return {"pe_office": "", "district": "", "location": ""}
    parts = [p.strip() for p in pe.split(",")]
    pe_office = parts[0] if parts else ""
    district = detect_district(pe)
    location = ", ".join(p for p in parts[1:] if p) if len(parts) > 1 else ""
    return {"pe_office": pe_office, "district": district, "location": location}

# ── HTTP Client ───────────────────────────────────────────────────────
_client = httpx.Client(verify=False, timeout=30, follow_redirects=True)

def fetch_noa_page(agency_code: str, page: int, size: int = 50) -> Optional[str]:
    kw = AGENCY_CONFIG[agency_code]["keyword"]
    for attempt in range(3):
        try:
            resp = _client.post(
                f"{BASE}/SearchNoaServlet",
                data={"keyword": kw, "pageNo": str(page), "size": str(size)},
            )
            if resp.status_code == 200 and len(resp.text) > 100:
                return resp.text
            if "No Records Found" in resp.text:
                return None
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                logger.warning(f"  [{agency_code}] Page {page} failed after 3 retries: {e}")
    return None

def fetch_detail(tender_id: str, pkg_lot_id: str = "") -> Optional[Dict]:
    """Fetch ViewAwardedContracts.jsp detail page and extract package_no, winner, amount."""
    url = f"{BASE}/resources/common/ViewAwardedContracts.jsp?tenderid={tender_id}"
    if pkg_lot_id:
        url += f"&pkgLotId={pkg_lot_id}"
    for attempt in range(3):
        try:
            resp = _client.get(url)
            if resp.status_code == 200 and len(resp.text) > 200:
                return parse_detail_html(resp.text)
        except Exception as e:
            if attempt < 2:
                time.sleep(1)
    return None

def parse_detail_html(html: str) -> Dict:
    """Extract fields from ViewAwardedContracts.jsp detail page."""
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
            elif "agency" in key and ":" in key:
                result["agency_detail"] = val
    return result

def parse_amount(val: str) -> float:
    """Parse amount from various formats: Crore, Lac, BDT."""
    val = val.replace(",", "").strip()
    if "crore" in val.lower():
        return float(re.sub(r"[^\d.]", "", val)) * 10_000_000
    if "lac" in val.lower() or "lakh" in val.lower():
        return float(re.sub(r"[^\d.]", "", val)) * 100_000
    try:
        return float(re.sub(r"[^\d.]", "", val))
    except ValueError:
        return 0.0

def parse_noa_rows(html: str, agency_code: str, page: int) -> List[Dict]:
    """Parse NOA table HTML rows into structured records."""
    records = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)
    for row_html in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)
        if len(cells) < 8:
            continue
        clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        # Skip header row
        if re.match(r"^(sl|no|serial|s\.?\s*no)", clean[0], re.I):
            continue

        # Column 2: Tender info — contains link + tender_id + title
        col2 = clean[2] if len(clean) > 2 else ""
        title_match = re.search(r"(\d{6,})[, ]*(.*)", col2)
        tender_id = title_match.group(1) if title_match else ""
        title = title_match.group(2).strip() if title_match else col2[:200]

        # Extract detail URL from HTML
        detail_url = ""
        url_m = re.search(r'href="([^"]*ViewAwardedContracts[^"]*)"', cells[2])
        if url_m:
            detail_url = url_m.group(1)

        # Column 3: Procuring Entity + Procurement Method
        col3 = clean[3] if len(clean) > 3 else ""
        pe_parts = col3.split("\n") if "\n" in col3 else [col3, ""]
        procuring_entity = pe_parts[0].strip()
        procurement_method = pe_parts[-1].strip() if len(pe_parts) > 1 else ""

        # Column 4: District
        district_raw = clean[4] if len(clean) > 4 else ""

        # Column 5: Date of Notification
        award_date_raw = clean[5] if len(clean) > 5 else ""

        # Column 6: Contractor (Winner)
        winner = clean[6] if len(clean) > 6 else ""

        # Column 7: Value in Crore
        amount_raw = clean[7] if len(clean) > 7 else "0"

        # Parse amount: table shows value in Crore BDT
        amount_bdt = 0.0
        try:
            val = re.sub(r"[^\d.]", "", amount_raw)
            if val:
                amount_bdt = float(val) * 10_000_000  # Convert Crore to BDT
        except ValueError:
            pass

        if not tender_id:
            continue

        pe_info = parse_procuring_entity(procuring_entity)

        records.append({
            "tender_id": tender_id,
            "title": title[:300],
            "procuring_entity": procuring_entity,
            "procurement_method": procurement_method,
            "district": pe_info["district"] or district_raw.strip(),
            "pe_office": pe_info["pe_office"],
            "location": pe_info["location"],
            "award_date": award_date_raw.strip(),
            "winner": winner.strip(),
            "amount_bdt": amount_bdt,
            "amount_crore": amount_raw.strip(),
            "detail_url": detail_url,
            "agency_code": agency_code,
            "agency_name": AGENCY_CONFIG[agency_code]["name"],
            "ministry": AGENCY_CONFIG[agency_code]["ministry"],
            "source": "ECONTRACT",
            "noa_page": page,
        })
    return records

# ── Cache Management ──────────────────────────────────────────────────
def get_cache_dir(agency_code: str) -> Path:
    d = KNOWLEDGE / "econtracts" / agency_code
    d.mkdir(parents=True, exist_ok=True)
    return d

def load_page_cache(agency_code: str, page: int) -> Optional[List[Dict]]:
    fp = get_cache_dir(agency_code) / f"page_{page:04d}.json"
    if fp.exists():
        return json.loads(fp.read_text(encoding="utf-8"))
    return None

def save_page_cache(agency_code: str, page: int, records: List[Dict]):
    fp = get_cache_dir(agency_code) / f"page_{page:04d}.json"
    fp.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

def load_global_seen() -> Set[str]:
    fp = KNOWLEDGE / "econtracts" / "seen_keys.json"
    if fp.exists():
        return set(json.loads(fp.read_text(encoding="utf-8")))
    return set()

def save_global_seen(seen: Set[str]):
    fp = KNOWLEDGE / "econtracts" / "seen_keys.json"
    fp.write_text(json.dumps(sorted(seen), indent=2), encoding="utf-8")

# ── Crawler ───────────────────────────────────────────────────────────
def crawl_agency(agency_code: str, max_pages: int = 5000) -> int:
    """Crawl all eContracts for a single agency. Returns new record count."""
    cache_dir = get_cache_dir(agency_code)
    seen = load_global_seen()
    total_new = 0
    page = 1

    # Resume from last cached page
    cached_pages = sorted(cache_dir.glob("page_*.json"))
    if cached_pages:
        last_page = int(cached_pages[-1].stem.split("_")[1])
        page = last_page + 1
        logger.info(f"  [{agency_code}] Resuming from page {page} ({len(cached_pages)} cached)")

    while page <= max_pages:
        # Check cache first
        cached = load_page_cache(agency_code, page)
        if cached is not None:
            for r in cached:
                key = f"{r['tender_id']}|{r['winner']}"
                if key not in seen:
                    seen.add(key)
                    total_new += 1
            page += 1
            continue

        html = fetch_noa_page(agency_code, page)
        if not html:
            logger.info(f"  [{agency_code}] No more data at page {page}")
            break

        records = parse_noa_rows(html, agency_code, page)
        if not records:
            logger.info(f"  [{agency_code}] Empty page {page}, stopping")
            break

        # Dedup and count
        new_records = []
        for r in records:
            key = f"{r['tender_id']}|{r['winner']}"
            if key not in seen:
                seen.add(key)
                new_records.append(r)

        if new_records:
            save_page_cache(agency_code, page, new_records)
            total_new += len(new_records)

        logger.info(f"  [{agency_code}] Page {page}: {len(new_records)} new (total {total_new})")

        # Save seen keys periodically
        if page % 50 == 0:
            save_global_seen(seen)

        page += 1

    save_global_seen(seen)
    logger.info(f"[{agency_code}] Complete: {total_new} new records across {page - 1} pages")
    return total_new

# ── Detail Fetching ───────────────────────────────────────────────────
def enrich_with_details(agency_code: str, max_workers: int = 10) -> int:
    """Fetch detail pages for records missing package_no."""
    cache_dir = get_cache_dir(agency_code)
    enriched = 0
    no_detail = 0

    for fp in sorted(cache_dir.glob("page_*.json")):
        records = json.loads(fp.read_text(encoding="utf-8"))
        to_fetch = [r for r in records if not r.get("package_no") and r.get("detail_url")]
        if not to_fetch:
            continue

        logger.debug(f"  [{agency_code}] Fetching {len(to_fetch)} details from {fp.name}")

        def process_detail(rec: Dict) -> Dict:
            url = rec.get("detail_url", "")
            m = re.search(r"tenderid=(\d+)", url)
            pkg_m = re.search(r"pkgLotId=(\d+)", url)
            if not m:
                return rec
            detail = fetch_detail(m.group(1), pkg_m.group(1) if pkg_m else "")
            if detail:
                if detail.get("package_no"):
                    rec["package_no"] = detail["package_no"]
                if detail.get("amount") and not rec.get("amount_bdt"):
                    rec["amount_bdt"] = parse_amount(detail["amount"])
                if detail.get("winner"):
                    rec["winner"] = detail["winner"]
            return rec

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(process_detail, r) for r in to_fetch]
            updated = []
            for f in as_completed(futures):
                try:
                    updated.append(f.result())
                except Exception as e:
                    logger.warning(f"  Detail fetch failed: {e}")

        # Merge updated records back
        updated_idx = 0
        for i, r in enumerate(records):
            if r.get("detail_url") and not r.get("package_no"):
                if updated_idx < len(updated):
                    records[i] = updated[updated_idx]
                    if updated[updated_idx].get("package_no"):
                        enriched += 1
                    else:
                        no_detail += 1
                    updated_idx += 1

        save_page_cache(agency_code, int(fp.stem.split("_")[1]), records)

    logger.info(f"[{agency_code}] Details enriched: {enriched} have package_no, {no_detail} still missing")
    return enriched

# ── Structured Output ─────────────────────────────────────────────────
def build_structured_output(agencies: Optional[List[str]] = None) -> Dict:
    """Build hierarchical output: ministry→agency→pe_office→district→location→contractor→contracts."""
    targets = agencies or sorted(TARGET_AGENCIES)
    hierarchy: Dict = {}
    seen = load_global_seen()
    total_records = 0
    total_amount = 0.0

    for agency_code in targets:
        cache_dir = get_cache_dir(agency_code)
        if not cache_dir.exists():
            continue

        for fp in sorted(cache_dir.glob("page_*.json")):
            records = json.loads(fp.read_text(encoding="utf-8"))
            for r in records:
                key = f"{r['tender_id']}|{r['winner']}"
                if key not in seen:
                    continue  # Skip if already removed from global set

                total_records += 1
                amt = float(r.get("amount_bdt", 0) or 0)
                total_amount += amt

                ministry = r.get("ministry", "Unknown")
                agency_name = r.get("agency_name", agency_code)
                pe = r.get("pe_office") or r.get("procuring_entity", "Unknown")
                district = r.get("district") or ""
                location = r.get("location") or ""
                contractor = r.get("winner", "Unknown")
                pkg_no = r.get("package_no", "")

                # Build hierarchy
                hierarchy.setdefault(ministry, {})
                hierarchy[ministry].setdefault(agency_code, {
                    "agency_name": agency_name,
                    "pe_offices": {},
                })
                hierarchy[ministry][agency_code]["pe_offices"].setdefault(pe, {})
                hierarchy[ministry][agency_code]["pe_offices"][pe].setdefault(district, {})
                hierarchy[ministry][agency_code]["pe_offices"][pe][district].setdefault(location, {})
                hierarchy[ministry][agency_code]["pe_offices"][pe][district][location].setdefault(contractor, {
                    "contractor_name": contractor,
                    "contracts": [],
                    "total_amount_bdt": 0.0,
                    "contract_count": 0,
                })
                ctr = hierarchy[ministry][agency_code]["pe_offices"][pe][district][location][contractor]
                ctr["contracts"].append({
                    "tender_id": r["tender_id"],
                    "package_no": pkg_no,
                    "work_name": (r.get("title", "") or "")[:200],
                    "quoted_amount_bdt": round(amt, 2),
                    "contract_signing_date": r.get("award_date", ""),
                    "procurement_method": r.get("procurement_method", ""),
                })
                ctr["total_amount_bdt"] += amt
                ctr["contract_count"] += 1

    # Convert nested dicts to lists
    output_ministries = []
    for ministry_name in sorted(hierarchy.keys()):
        agencies_list = []
        for ac in sorted(hierarchy[ministry_name].keys()):
            info = hierarchy[ministry_name][ac]
            pe_list = []
            for pe_name in sorted(info["pe_offices"].keys()):
                districts_list = []
                for dist_name in sorted(info["pe_offices"][pe_name].keys()):
                    locations_list = []
                    for loc_name in sorted(info["pe_offices"][pe_name][dist_name].keys()):
                        contractors_list = []
                        for ctr_name in sorted(info["pe_offices"][pe_name][dist_name][loc_name].keys()):
                            ctr_info = info["pe_offices"][pe_name][dist_name][loc_name][ctr_name]
                            contractors_list.append({
                                "contractor_name": ctr_info["contractor_name"],
                                "total_amount_bdt": round(ctr_info["total_amount_bdt"], 2),
                                "contract_count": ctr_info["contract_count"],
                                "contracts": ctr_info["contracts"],
                            })
                        locations_list.append({
                            "location": loc_name,
                            "contractors": contractors_list,
                        })
                    districts_list.append({
                        "district": dist_name or "Unknown",
                        "locations": locations_list,
                    })
                pe_list.append({
                    "pe_office": pe_name,
                    "districts": districts_list,
                })
            agencies_list.append({
                "agency_code": ac,
                "agency_name": info["agency_name"],
                "pe_offices": pe_list,
            })
        output_ministries.append({
            "ministry": ministry_name,
            "agencies": agencies_list,
        })

    return {
        "generated_at": datetime.now().isoformat(),
        "total_records": total_records,
        "total_amount_bdt": round(total_amount, 2),
        "agencies_crawled": targets,
        "ministries": output_ministries,
    }

# ── Main ──────────────────────────────────────────────────────────────
def main(
    agencies: Optional[List[str]] = None,
    skip_crawl: bool = False,
    skip_details: bool = False,
    max_pages: int = 5000,
    max_workers: int = 10,
):
    targets = agencies or sorted(TARGET_AGENCIES)

    # Phase 1: Crawl
    if not skip_crawl:
        logger.info(f"=== Phase 1: Crawling {len(targets)} target agencies ===")
        total = 0
        for ac in targets:
            t0 = time.time()
            n = crawl_agency(ac, max_pages=max_pages)
            elapsed = time.time() - t0
            total += n
            logger.info(f"  [{ac}] {n} new records in {elapsed:.1f}s")
        logger.info(f"Crawl complete: {total} total new records across {len(targets)} agencies")

    # Phase 2: Detail enrichment
    if not skip_details:
        logger.info("=== Phase 2: Enriching with detail page data ===")
        total_enriched = 0
        for ac in targets:
            n = enrich_with_details(ac, max_workers=max_workers)
            total_enriched += n
        logger.info(f"Detail enrichment complete: {total_enriched} records enriched")

    # Phase 3: Build structured output
    logger.info("=== Phase 3: Building structured output ===")
    structured = build_structured_output(targets)
    out = KNOWLEDGE / "econtracts" / "structured.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(structured, indent=2, ensure_ascii=False), encoding="utf-8")

    # Also save a flat list for matching
    flat = []
    for m in structured["ministries"]:
        for a in m["agencies"]:
            for pe in a["pe_offices"]:
                for d in pe["districts"]:
                    for loc in d["locations"]:
                        for ctr in loc["contractors"]:
                            for c in ctr["contracts"]:
                                flat.append({
                                    "tender_id": c["tender_id"],
                                    "package_no": c["package_no"],
                                    "title": c["work_name"],
                                    "winner": ctr["contractor_name"],
                                    "amount_bdt": c["quoted_amount_bdt"],
                                    "agency_code": a["agency_code"],
                                    "agency_name": a["agency_name"],
                                    "ministry": m["ministry"],
                                    "pe_office": pe["pe_office"],
                                    "district": d["district"],
                                    "location": loc["location"],
                                    "award_date": c["contract_signing_date"],
                                    "procurement_method": c["procurement_method"],
                                    "source": "ECONTRACT",
                                })
    flat_out = KNOWLEDGE / "econtracts" / "flat.json"
    flat_out.write_text(json.dumps(flat, indent=2, ensure_ascii=False), encoding="utf-8")

    logger.info(f"Output: {len(flat)} records in structured.json + flat.json")
    logger.info(f"Stats: {structured['total_records']} contracts, BDT {structured['total_amount_bdt']:,.2f}")
    for m in structured["ministries"]:
        for a in m["agencies"]:
            cnt = sum(c["contract_count"] for pe in a["pe_offices"] for d in pe["districts"] for loc in d["locations"] for c in loc["contractors"])
            print(f"  {a['agency_code']}: {cnt} contracts")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Enterprise eContracts Crawler")
    parser.add_argument("--agencies", nargs="+", help="Agencies to crawl (default: all)")
    parser.add_argument("--skip-crawl", action="store_true", help="Skip crawl, rebuild output only")
    parser.add_argument("--skip-details", action="store_true", help="Skip detail page enrichment")
    parser.add_argument("--max-pages", type=int, default=5000, help="Max pages per agency")
    parser.add_argument("--workers", type=int, default=10, help="Thread pool workers for details")
    args = parser.parse_args()
    main(
        agencies=args.agencies,
        skip_crawl=args.skip_crawl,
        skip_details=args.skip_details,
        max_pages=args.max_pages,
        max_workers=args.workers,
    )
