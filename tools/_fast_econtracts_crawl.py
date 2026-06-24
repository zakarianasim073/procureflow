"""
Full-speed eContracts crawler: scrapes ALL NOA pages back to Aug 2025.
Saves incrementally — resume-safe, never refetches same tender+winner.
"""
import json, logging, re, sys, time
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("econtracts_crawl")

EGP_BASE = "https://www.eprocure.gov.bd"
KNOWLEDGE = Path(__file__).resolve().parent.parent / "backend" / "runtime" / "knowledge"

try:
    import httpx
    _HTTPX = httpx.Client(verify=False, timeout=30, follow_redirects=True)
except ImportError:
    _HTTPX = None

# ── Persistent state ─────────────────────────────────────────────
STATE_DIR = KNOWLEDGE / "econtracts_raw"
STATE_DIR.mkdir(parents=True, exist_ok=True)

SEEN_FILE = STATE_DIR / "seen_keys.json"
OUTPUT_DIR = STATE_DIR / "detail_pages"

def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    return set()

def save_seen(seen: set):
    SEEN_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")

def load_page_results(page: int) -> list:
    fp = STATE_DIR / f"page_{page:04d}.json"
    if fp.exists():
        return json.loads(fp.read_text(encoding="utf-8"))
    return None

def save_page_results(page: int, records: list):
    fp = STATE_DIR / f"page_{page:04d}.json"
    fp.write_text(json.dumps(records, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

# ── Fetch helpers ─────────────────────────────────────────────────
def fetch_url(url: str, data: dict = None, retries: int = 3) -> str | None:
    for attempt in range(retries):
        try:
            if _HTTPX is None:
                from urllib.request import Request, urlopen
                from urllib.parse import urlencode
                req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
                if data:
                    req.data = urlencode(data).encode()
                with urlopen(req, timeout=30) as resp:
                    return resp.read().decode("utf-8")
            else:
                if data:
                    resp = _HTTPX.post(url, data=data)
                else:
                    resp = _HTTPX.get(url)
                if resp.status_code == 200 and len(resp.text) > 100:
                    return resp.text
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
            else:
                logger.warning(f"  Failed: {url[:80]} -> {e}")
    return None

def parse_detail(html: str) -> dict:
    result = {"package_no": "", "amount_bdt": 0.0, "winner": "",
              "procurement_method": "", "procuring_entity": "", "award_date": ""}
    tables = re.findall(r'<table[^>]*>(.*?)</table>', html, re.DOTALL | re.IGNORECASE)
    for table in tables:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.DOTALL)
        for row in rows:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL | re.IGNORECASE)
            texts = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            if len(texts) < 2: continue
            key, val = texts[0].strip(), texts[1].strip()
            if "Package No." in key: result["package_no"] = val
            elif "Contract Value" in key:
                try: result["amount_bdt"] = float(val.replace(",", ""))
                except ValueError: pass
            elif "Name of the Economic Operator" in key: result["winner"] = val
            elif "Procurement Method" in key: result["procurement_method"] = val
            elif "Procuring Entity Name" in key: result["procuring_entity"] = val
            elif "Date of Notification of Award" in key: result["award_date"] = val
            elif "Agency:" in key:
                if not result.get("procuring_entity"):
                    result["procuring_entity"] = val
    return result

# ── Main crawler ─────────────────────────────────────────────────
seen_keys = load_seen()
logger.info(f"Loaded {len(seen_keys)} already-seen tender+winner keys")

total_new = 0
page = 1
stop_aug2025 = False

while not stop_aug2025:
    # Check if page already cached
    cached = load_page_results(page)
    if cached is not None:
        # Still count to find Aug 2025 cutoff
        for r in cached:
            award_date = r.get("award_date", "")
            if award_date and award_date < "01-Aug-2025":
                stop_aug2025 = True
                break
        if stop_aug2025:
            logger.info(f"Reached pre-Aug 2025 data at page {page}, stopping")
            break
        # Mark keys as seen
        for r in cached:
            key = f"{r.get('tender_id','')}|{r.get('winner','')}"
            seen_keys.add(key)
        total_new += len(cached)
        logger.info(f"Page {page}: {len(cached)} cached records (total {total_new})")
        page += 1
        continue

    # Fetch NOA page
    logger.info(f"Fetching NOA page {page}...")
    html = fetch_url(f"{EGP_BASE}/SearchNoaServlet", {"keyword": "", "pageNo": str(page), "size": "50"})
    if not html or "No Records Found" in html:
        logger.info(f"No more records at page {page}")
        break

    # Parse rows
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
    row_infos = []
    for row_html in rows:
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row_html, re.DOTALL | re.IGNORECASE)
        if len(cells) < 8: continue
        cell2_html = cells[2]
        link_match = re.search(r'href=(["\'])(/resources/common/ViewAwardedContracts\.jsp[^"\']+)\1', cell2_html, re.DOTALL)
        if not link_match: continue
        detail_url = link_match.group(2)
        cell_text = re.sub(r'<[^>]+>', '', cell2_html).strip()
        tender_id = ""
        m = re.search(r'(\d{6,})', cell_text)
        if m: tender_id = m.group(1)
        winner_approx = re.sub(r'<[^>]+>', '', cells[6]).strip() if len(cells) > 6 else ""
        key = f"{tender_id}|{winner_approx}"
        if key in seen_keys: continue
        seen_keys.add(key)
        row_infos.append((detail_url, cell_text, tender_id, winner_approx, key, cells[1] if len(cells) > 1 else "", cells[7] if len(cells) > 7 else ""))

    if not row_infos:
        logger.info(f"  Page {page}: all {len(rows)} rows already seen, saving empty")
        save_page_results(page, [])
        page += 1
        continue

    # Fetch detail pages in parallel
    def fetch_detail(info):
        detail_url, cell_text, tender_id, winner_approx, key, pe_cell, amount_cell = info
        try:
            detail_html = fetch_url(f"{EGP_BASE}{detail_url}")
            detail = parse_detail(detail_html) if detail_html else {}
            package_no = detail.get("package_no", "")
            if not package_no:
                return None

            title = cell_text
            if ", " in cell_text:
                parts = cell_text.split(", ", 1)
                if len(parts) > 1:
                    title = parts[1]

            amount_bdt = 0.0
            try:
                amount_bdt = float(re.sub(r'<[^>]+>', '', amount_cell).replace(",", "")) * 100_000
            except ValueError:
                pass
            if detail.get("amount_bdt", 0) > 0:
                amount_bdt = detail["amount_bdt"]

            return {
                "tender_id": tender_id,
                "package_no": package_no,
                "title": title[:300] if title else "",
                "winner": detail.get("winner", winner_approx),
                "amount_bdt": amount_bdt,
                "procuring_entity": detail.get("procuring_entity", re.sub(r'<[^>]+>', '', pe_cell).strip()),
                "award_date": detail.get("award_date", ""),
                "procurement_method": detail.get("procurement_method", ""),
                "procurement_nature": "Works",
                "source": "ECONTRACT",
                "noa_page": page,
            }
        except Exception:
            return None

    page_results = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(fetch_detail, info): info for info in row_infos}
        for f in as_completed(futures):
            res = f.result()
            if res:
                page_results.append(res)

    # Save page results
    save_page_results(page, page_results)
    total_new += len(page_results)

    # Check for Aug 2025 cutoff
    for r in page_results:
        award_date = r.get("award_date", "")
        if award_date and award_date < "01-Aug-2025":
            stop_aug2025 = True
            break

    logger.info(f"Page {page}: {len(page_results)} new with package_no (total {total_new}){' [STOP - pre-Aug 2025]' if stop_aug2025 else ''}")
    
    # Save seen keys every 10 pages
    if page % 10 == 0:
        save_seen(seen_keys)

    page += 1
    if stop_aug2025:
        break

# Final save
save_seen(seen_keys)
logger.info(f"\n=== Complete: {total_new} total records with package_no across {page-1} pages ===")
logger.info(f"Data saved to {STATE_DIR}")
