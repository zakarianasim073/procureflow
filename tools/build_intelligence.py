"""
Complete Intelligence Pipeline Builder

Pulls ALL data from eGP (public endpoints):
  1. APP records from SearchAPPServlet (public)
  2. NOA award records from SearchNoaServlet (public)
  3. Matches APP ↔ awards by: tender_id → package_no → fuzzy title
  4. For unmatched awards, synthesizes APP estimate (award × 1.08)
  5. Calculates NPP, discount per award
  6. Builds contractor DNA with discount patterns
  7. Outputs everything agents need

Usage:
    python tools/build_intelligence.py --rebuild
    python tools/build_intelligence.py --agency BWDB --rebuild
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.request import Request, urlopen
from urllib.error import URLError

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("intel_builder")

BACKEND = Path(__file__).resolve().parent.parent / "backend"
RUNTIME = BACKEND / "runtime"
KNOWLEDGE = RUNTIME / "knowledge"

EGP_BASE = "https://www.eprocure.gov.bd"

# Shared httpx client for eContracts scraping
try:
    import httpx
    _HTTPX = httpx.Client(verify=False, timeout=30, follow_redirects=True)
except ImportError:
    _HTTPX = None

# eGP credentials for authenticated endpoints (ComboServlet, etc.)
EGP_EMAIL = "hbsrjv@gmail.com"
EGP_PASSWORD = "hbsrjv2017"

# Department ID → name mapping for office-based APP crawl
AGENCY_DEPT_MAP = {
    "BWDB": {"id": 7, "name": "BWDB"},
    "LGED": {"id": 5, "name": "LGED"},
    "RHD": {"id": 10, "name": "RHD"},
    "PWD": {"id": 21, "name": "PWD"},
    "BADC": {"id": 39, "name": "BADC"},
    "HED": {"id": 141, "name": "Health_Engineering"},
    "RAILWAY": {"id": 163, "name": "Bangladesh_Railway"},
    "BPDB": {"id": 18, "name": "BPDB"},
    "WASA": {"id": 28, "name": "Dhaka_WASA"},
    "BRIDGES": {"id": 22, "name": "Bridges_Division"},
    "BIWTA": {"id": 171, "name": "BIWTA"},
    "EDUCATION_ENG": {"id": 138, "name": "Education_Engineering"},
    "REB": {"id": 13, "name": "REB"},
    "RAJUK": {"id": 29, "name": "RAJUK"},
}

# Offices cache directory
OFFICES_CACHE_DIR = KNOWLEDGE / "app"

def _login_egp() -> Optional[httpx.Client]:
    """Login to the eGP portal and return an authenticated httpx client."""
    if _HTTPX is None:
        return None
    try:
        _HTTPX.get(EGP_BASE)
        resp = _HTTPX.post(
            f"{EGP_BASE}/LoginSrBean?action=checkLogin",
            data={"emailId": EGP_EMAIL, "password": EGP_PASSWORD},
        )
        _HTTPX.get(f"{EGP_BASE}/Index.jsp")
        return _HTTPX
    except Exception as exc:
        logger.warning(f"eGP login failed: {exc}")
        return None


def fetch_offices(department_id: int, dept_name: str = "", force_refresh: bool = False) -> List[Dict]:
    """Fetch PE offices for a department from the authenticated ComboServlet.
    Caches result to KNOWLEDGE/app/offices_{name}.json.
    """
    cache_name = dept_name.lower().replace(" ", "_") if dept_name else f"dept_{department_id}"
    cache_path = OFFICES_CACHE_DIR / f"offices_{cache_name}.json"

    if not force_refresh and cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    client = _login_egp()
    if client is None:
        logger.warning(f"Cannot fetch offices for dept {department_id} — no eGP session")
        return []
    try:
        resp = client.post(
            f"{EGP_BASE}/ComboServlet",
            data={"departmentId": str(department_id), "funName": "officeCombo"},
        )
        opts = re.findall(r'<option[^>]*value=(["\'])([^"\']+)\1[^>]*>(.*?)</option>', resp.text, re.DOTALL)
        offices = []
        for _, val, txt in opts:
            t = re.sub(r'<[^>]+>', '', txt).strip()
            v = val.strip()
            if v and v != " " and t and t != "-- Select Procuring Entity --":
                offices.append({"id": int(v), "name": t})
        offices.sort(key=lambda x: x["id"])
        OFFICES_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(offices, indent=2), encoding="utf-8")
        label = dept_name or f"dept_{department_id}"
        logger.info(f"Fetched {len(offices)} offices for {label}")
        return offices
    except Exception as exc:
        logger.warning(f"Failed to fetch offices for dept {department_id}: {exc}")
        return []


def ensure_session():
    """Ensure shared httpx session is seeded with a JSESSIONID."""
    if _HTTPX is not None:
        try:
            _HTTPX.get(EGP_BASE)
        except Exception:
            pass


def extract_pkg_from_title(title: str) -> str:
    """Extract a meaningful package_no from a title prefix."""
    t = title.strip()
    if not t:
        return ""
    for sep in ["\r", "\n", "  "]:
        parts = t.split(sep, 1)
        if len(parts) > 1 and len(parts[0]) < 80:
            candidate = parts[0].strip()
            if _is_valid_pkg(candidate):
                return candidate
            break
    m = re.match(
        r'^([A-Za-z0-9_/\-.]{3,60}?)\s+(?:at |of |for |work |Supply |Procurement |Construction |Repair |Development |Improvement |Re-excavation |Providing |Installation |Maintenance )',
        t, re.IGNORECASE
    )
    if m:
        candidate = m.group(1).strip()
        if _is_valid_pkg(candidate):
            return candidate
    return ""


_PKG_BLACKLIST = {"supply", "works", "construction", "repair", "development",
                   "improvement", "procurement", "maintenance", "providing",
                   "installation", "reexcavation", "remaining", "re-excavation",
                   "supplying", "service", "goods", "n/a", "na", ""}


def _is_valid_pkg(pkg: str) -> bool:
    """Check if a string looks like a real package identifier (not a word or number)."""
    p = pkg.strip().lower()
    if not p or len(p) < 4:
        return False
    if p in _PKG_BLACKLIST:
        return False
    # Pure digits (just a tender ID, not a package no)
    if re.match(r'^\d{4,}$', p):
        return False
    # Must contain separator characters typical of package codes
    has_sep = "/" in pkg or "-" in pkg
    if not has_sep:
        return False
    return True


# ── helpers ────────────────────────────────────────────────────────────

def slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "_", s)
    return s.strip("_") or "unknown"


def normalize_title(raw: str) -> str:
    s = raw.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_agency_id(text: str) -> str:
    t = text.lower()
    if "bwdb" in t or "water development" in t or "water resources" in t:
        return "BWDB"
    if "lged" in t or "local government engineering" in t:
        return "LGED"
    if "pwd" in t or "public works" in t:
        return "PWD"
    if "railway" in t:
        return "RAILWAY"
    if "rhd" in t or "road transport" in t or "roads and highways" in t:
        return "RHD"
    if "bba" in t or "bridge authority" in t:
        return "BBA"
    if "power" in t or "electricity" in t or "reb" in t or "pgcb" in t:
        return "POWER"
    if "education" in t or "hed" in t:
        return "EDUCATION"
    if "health" in t or "hospital" in t:
        return "HEALTH"
    if "housing" in t:
        return "HOUSING"
    if "home" in t or "prison" in t:
        return "HOME"
    if "industri" in t or "bcic" in t:
        return "INDUSTRY"
    # Try ministry-level mapping
    if "ministry of water" in t:
        return "BWDB"
    if "ministry of local government" in t or "rural development" in t:
        return "LGED"
    if "ministry of road" in t or "bridges" in t:
        return "RHD"
    if "ministry of housing" in t or "public works" in t:
        return "PWD"
    if "ministry of power" in t or "energy" in t or "mineral" in t:
        return "POWER"
    if "ministry of education" in t:
        return "EDUCATION"
    if "ministry of health" in t:
        return "HEALTH"
    if "ministry of railways" in t:
        return "RAILWAY"
    if "ministry of home" in t or "public security" in t:
        return "HOME"
    return "OTHER"


def normalize_tender_id(raw: str) -> str:
    return re.sub(r"(?i)app[-_]?", "", str(raw)).strip()


def normalize_package_no(raw: str) -> str:
    """Clean and normalize a package_no for matching across APP and award data."""
    if not raw:
        return ""
    p = raw.strip()
    # Strip HTML entities
    p = re.sub(r'&nbsp;', ' ', p)
    p = re.sub(r'&amp;', '&', p)
    p = re.sub(r'&lt;', '<', p)
    p = re.sub(r'&gt;', '>', p)
    # Replace all whitespace sequences with single space
    p = re.sub(r'\s+', ' ', p)
    # Remove leading/trailing non-alphanumeric characters (keep internal punctuation)
    p = re.sub(r'^[^A-Za-z0-9]+', '', p)
    p = re.sub(r'[^A-Za-z0-9]+$', '', p)
    # Truncate absurdly long package_nos (likely descriptions, not IDs)
    if len(p) > 80:
        p = p[:80]
    return p.strip().upper()


# ── eGP Scrapers ──────────────────────────────────────────────────────

def fetch_url(url: str, retries: int = 3) -> Optional[str]:
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
            else:
                logger.warning(f"  Failed after {retries} retries: {url[:80]}... -> {e}")
    return None


def parse_app_amount(raw: str) -> float:
    """Parse APP estimated amounts: Crore, Lac, TK."""
    raw = raw.replace(",", "").strip()
    if "crore" in raw.lower():
        return float(re.sub(r"[^\d.]", "", raw)) * 10_000_000
    if "lac" in raw.lower() or "lakh" in raw.lower():
        return float(re.sub(r"[^\d.]", "", raw)) * 100_000
    try:
        return float(re.sub(r"[^\d.]", "", raw))
    except ValueError:
        return 0.0


def scrape_app_page(keyword: str, page: int = 1, size: int = 50) -> List[Dict]:
    """Scrape one page of APP records from the public SearchAPPServlet (keyword search)."""
    import urllib.parse
    url = f"{EGP_BASE}/SearchAPPServlet?action=advSearch&pageNo={page}&size={size}&keyWord={urllib.parse.quote(keyword)}"
    html = fetch_url(url)
    if not html or "No Records Found" in html:
        return []
    records = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)
    if not rows:
        lines = [l.strip() for l in html.split("\n") if l.strip() and not l.strip().startswith("<")]
        for line in lines:
            c = [x.strip() for x in line.split("\t") if x.strip()]
            if len(c) >= 5:
                records.append(_parse_app_cells(c))
    else:
        for row_html in rows:
            c = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)
            c = [re.sub(r"<[^>]+>", "", x).strip() for x in c]
            if len(c) >= 5:
                records.append(_parse_app_cells(c))
    return records


def _parse_app_cells(cells: List[str]) -> Dict:
    """Parse APP cells (keyword search) into a record.

    Column order: Tender ID | Procuring Entity | Procurement Type | Title | Package No | Est. Amount | Method
    """
    tid = ""
    for c in cells:
        m = re.search(r"(\d{6,})", c)
        if m:
            tid = m.group(1)
            break
    title = cells[3] if len(cells) > 3 else cells[0] if cells else ""
    package_no = cells[4] if len(cells) > 4 else ""
    if not package_no and "," in title:
        package_no = title.split(",")[0].strip()
    if package_no and re.match(r'^\d{4,}$', package_no):
        title_pkg = extract_pkg_from_title(title)
        if title_pkg and title_pkg != package_no:
            package_no = title_pkg
    estimated = 0.0
    for c in cells:
        if re.search(r"[\d,]+\.?\d*\s*(crore|lac|lakh|tk)", c.lower()):
            estimated = parse_app_amount(c)
            break
    if not estimated:
        for c in cells:
            m = re.search(r"(\d+\.?\d*)", c.replace(",", ""))
            if m:
                val = float(m.group(1))
                if val > 100:
                    estimated = val
                    break
    pe = cells[1] if len(cells) > 1 else ""
    ptype = cells[2] if len(cells) > 2 else "Works"
    method = cells[-1] if len(cells) > 6 else ""
    return {
        "tender_id": tid,
        "package_no": package_no,
        "title": title,
        "estimated_amount_bdt": estimated,
        "procurement_type": ptype,
        "procurement_method": method,
        "procuring_entity": pe,
        "agency_target": extract_agency_id(pe),
        "source": "APP",
    }


# ── Office-based APP Crawler (DB budget type, correct package_no) ───────

def scrape_app_by_office(office_id: int, page: int = 1, size: int = 50) -> Tuple[List[Dict], int]:
    """Scrape one page of APP records for a PE office with DB budget type.

    POSTs to SearchAPPServlet with bTypeId=1 (Development Budget).
    Returns (records, total_pages).
    """
    try:
        resp = _HTTPX.post(
            f"{EGP_BASE}/SearchAPPServlet",
            data={
                "bTypeId": "1",
                "pageNo": str(page),
                "office": str(office_id),
                "action": "advSearch",
                "size": str(size),
                "keyWord": "null",
            },
        )
    except Exception as exc:
        logger.warning(f"  Office {office_id} request failed: {exc}")
        return [], 0
    html = resp.text
    if not html.strip() or "No Records Found" in html or len(html) < 100:
        return [], 0
    # Extract total pages from hidden field
    total_m = re.search(r'id="totalPages"\s+value="?"?(\d+)"?"?', html)
    total_pages = int(total_m.group(1)) if total_m else 1
    records = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)
    for row_html in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)
        clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        # CRITICAL: Keep empty cells to preserve column alignment.
        # The APP Code (column 3) is often empty; filtering it out shifts every column left.
        if len(clean) >= 5 and not re.match(r'^(sl|no|serial|s\.?\s*no)$', clean[0], re.IGNORECASE):
            records.append(_parse_app_office_row(clean))
    return records, total_pages


def _parse_app_office_row(cells: List[str]) -> Dict:
    """Parse APP row from bTypeId=1 endpoint (6 columns: serial, app_id, app_code, title, package+desc, est+method)."""
    app_code = cells[2] if len(cells) > 2 else ""
    title = cells[3] if len(cells) > 3 else ""
    pkg_field = cells[4] if len(cells) > 4 else ""
    est_field = cells[5] if len(cells) > 5 else ""

    # Package no: first part before comma in column 4
    package_no = ""
    if pkg_field:
        package_no = pkg_field.split(",")[0].strip()
        if not _is_valid_pkg(package_no):
            package_no = extract_pkg_from_title(title) or ""

    # Tender ID (APP ID is column 1)
    tender_id = cells[1].strip() if len(cells) > 1 else ""
    if not tender_id or not tender_id.isdigit():
        for c in cells:
            m = re.search(r"(\d{6,})", c)
            if m:
                tender_id = m.group(1)
                break

    # Estimated cost from column 5 (format: "146445000.00, OTM")
    estimated = 0.0
    if est_field:
        amt_str = est_field.split(",")[0].strip()
        try:
            estimated = float(amt_str.replace(",", ""))
        except ValueError:
            pass

    # Procurement method from column 5 (after comma)
    method = ""
    if "," in est_field:
        method = est_field.split(",", 1)[1].strip()

    # Procurement type from title prefix (e.g., "Works, Title..." or "Goods, Title...")
    ptype = "Works"
    if title.startswith("Goods,"):
        ptype = "Goods"
        title = title[len("Goods,"):].strip()
    elif title.startswith("Services,"):
        ptype = "Services"
        title = title[len("Services,"):].strip()
    elif title.startswith("Works,"):
        title = title[len("Works,"):].strip()

    # Extract FY from APP Code
    fy = extract_fy_from_app_code(app_code)

    # Detect agency from title/package_no (not hardcoded)
    detected_agency = extract_agency_id(title + " " + package_no)
    if detected_agency == "OTHER":
        detected_agency = extract_agency_id(package_no)
    if detected_agency == "OTHER":
        detected_agency = extract_agency_id(app_code)

    return {
        "tender_id": tender_id,
        "app_id": cells[1].strip() if len(cells) > 1 else "",
        "app_code": app_code,
        "package_no": package_no,
        "title": title,
        "estimated_amount_bdt": estimated,
        "procurement_type": ptype,
        "procurement_method": method,
        "financial_year": fy,
        "agency_target": detected_agency,
        "source": "APP",
        "_office_search": True,
    }


def extract_fy_from_app_code(app_code: str) -> str:
    """Extract financial year from APP Code like 'APP/Betagi Project/2025-26' or 'APP/Project/2025-2026'."""
    m = re.search(r'(20\d{2})\s*[-–]\s*(20\d{2})', app_code)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m2 = re.search(r'(20\d{2})\s*[-–]\s*(\d{2})', app_code)
    if m2:
        return f"{m2.group(1)}-{m2.group(2)}"
    return ""


def scrape_noa_page(page: int = 1, size: int = 50) -> List[Dict]:
    """Scrape one page of NOA award records from the public SearchNoaServlet."""
    url = f"{EGP_BASE}/SearchNoaServlet?action=advSearch&pageNo={page}&size={size}"
    html = fetch_url(url)
    if not html or "No Records Found" in html:
        return []

    records = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)
    for row_html in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)
        cells_text = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]

        if len(cells_text) < 3:
            continue

        # From NOA table: Ministry, Tender ID + Title, Office, Location, Award Date, Winner, Amount
        tender_field = cells_text[2] if len(cells_text) > 2 else ""
        m_tid = re.search(r"(\d{6,})", tender_field)
        tid = m_tid.group(1) if m_tid else ""

        # Title is the part after the comma/TAB in tender_field
        title = ""
        if "," in tender_field:
            title = tender_field.split(",", 1)[1].strip()
        elif m_tid:
            title = tender_field[m_tid.end():].strip()

        # Parse amount (in Lac from eGP)
        amount = 0.0
        for c in cells_text:
            try:
                v = float(re.sub(r"[^\d.]", "", c))
                if v > 0:
                    amount = v
            except ValueError:
                continue
        # NOA amount is in Lac (1 Lac = 100,000 BDT)
        amount_bdt = amount * 100_000 if amount > 0 else 0

        pe = cells_text[1] if len(cells_text) > 1 else ""
        office = cells_text[3] if len(cells_text) > 3 else ""
        location = cells_text[4] if len(cells_text) > 4 else ""
        award_date = cells_text[5] if len(cells_text) > 5 else ""
        winner = cells_text[6] if len(cells_text) > 6 else ""
        source = cells_text[0] if len(cells_text) > 0 else "NOA"

        records.append({
            "tender_id": tid,
            "title": title,
            "winner": winner,
            "amount_bdt": amount_bdt,
            "procuring_entity": pe,
            "office": office,
            "location": location,
            "award_date": award_date,
            "source": source,
            "agency_target": extract_agency_id(pe + " " + office),
        })

    return records


# ── APP Crawler ───────────────────────────────────────────────────────

AGENCY_KEYWORDS = {
    "BWDB": ["BWDB", "Water Development Board", "Water Resources"],
    "LGED": ["LGED", "Local Government Engineering"],
    "PWD": ["PWD", "Public Works Department"],
    "RHD": ["RHD", "Road Transport", "Roads and Highways"],
    "RAILWAY": ["Bangladesh Railway"],
    "BBA": ["Bridge Authority"],
    "POWER": ["Power Division", "Electricity", "REB", "PGCB"],
    "EDUCATION": ["Education", "School", "College", "University"],
    "HEALTH": ["Health", "Hospital", "Medical"],
    "HOUSING": ["Housing", "Public Works"],
    "HOME": ["Home Affairs", "Prison", "Police"],
    "INDUSTRY": ["Industries", "BCIC"],
}


def crawl_app(agency: Optional[str] = None) -> List[Dict]:
    """Crawl APP records using office-based search for known depts, fallback to keyword."""
    if agency and agency.upper() in AGENCY_DEPT_MAP:
        info = AGENCY_DEPT_MAP[agency.upper()]
        return _crawl_app_by_offices(info["id"], info["name"])
    if agency and agency.upper() == "ALL":
        # Crawl all known departments
        all_recs: List[Dict] = []
        seen: Set[str] = set()
        for name, info in AGENCY_DEPT_MAP.items():
            recs = _crawl_app_by_offices(info["id"], info["name"])
            for r in recs:
                key = r.get("package_no", "") or r.get("tender_id", "")
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                all_recs.append(r)
        logger.info(f"Total APP records from all departments: {len(all_recs)}")
        return all_recs
    return _crawl_app_keyword(agency)


def _crawl_app_keyword(agency: Optional[str] = None) -> List[Dict]:
    """Fallback: crawl APP via keyword search (old method)."""
    all_records: List[Dict] = []
    seen_ids: Set[str] = set()
    keywords = AGENCY_KEYWORDS.get(agency.upper(), [agency]) if agency else [kw for v in AGENCY_KEYWORDS.values() for kw in v]
    for keyword in keywords:
        page = 1
        while page <= 200:
            records = scrape_app_page(keyword, page=page, size=50)
            if not records:
                break
            new = 0
            for rec in records:
                tid = rec.get("tender_id", "")
                if tid:
                    if tid in seen_ids:
                        continue
                    seen_ids.add(tid)
                rec["_source_keyword"] = keyword
                all_records.append(rec)
                new += 1
            logger.info(f"  APP keyword '{keyword}' page {page}: {new} new (total {len(all_records)})")
            if new < 50:
                break
            page += 1
    if agency:
        all_records = [r for r in all_records if r.get("agency_target", "").upper() == agency.upper()]
    logger.info(f"APP keyword crawl complete: {len(all_records)} records")
    return all_records


def _crawl_app_by_offices(department_id: int, dept_name: str = "") -> List[Dict]:
    """Crawl APP for a department by iterating through all PE offices with bTypeId=1.
    Handles pagination within each office.
    """
    label = dept_name or f"dept_{department_id}"
    offices = fetch_offices(department_id, dept_name)
    if not offices:
        logger.warning(f"No offices found for {label}, falling back to keyword crawl")
        return _crawl_app_keyword(label)

    # Skip keywords for field-office filtering (department-specific)
    skip_kw = ["circle", "zone", "director", "secretariat", "cell", "board",
               "accounting", "evaluation", "programme", "chief engineer",
               "project director", "management unit", "regional", "hope",
               "audit", "training", "monitoring"]

    all_records: List[Dict] = []
    seen_pkg_keys: Set[str] = set()

    for i, office in enumerate(offices):
        oid = office["id"]
        oname = office["name"]
        if any(kw in oname.lower() for kw in skip_kw):
            continue
        page = 1
        office_total = 0
        while True:
            records, total_pages = scrape_app_by_office(oid, page=page, size=50)
            if not records:
                break
            for rec in records:
                key = rec.get("package_no", "") or rec.get("tender_id", "")
                if key:
                    if key in seen_pkg_keys:
                        continue
                    seen_pkg_keys.add(key)
                rec["_office_id"] = oid
                rec["_office_name"] = oname
                rec["_department"] = label
                all_records.append(rec)
                office_total += 1
            if page >= total_pages:
                break
            page += 1
        if office_total > 0:
            logger.info(f"  [{label}] Office {oid} {oname[:30]}: {office_total} records (page {page}/{total_pages})")

    logger.info(f"APP office crawl complete for {label}: {len(all_records)} records")
    return all_records


def crawl_noa(agency: Optional[str] = None, max_pages: int = 200) -> List[Dict]:
    """Crawl NOA award records from eGP (public SearchNoaServlet)."""
    all_records: List[Dict] = []
    seen_keys: Set[str] = set()

    for page in range(1, max_pages + 1):
        records = scrape_noa_page(page=page, size=50)
        if not records:
            break
        new = 0
        for rec in records:
            tid = rec.get("tender_id", "")
            winner = rec.get("winner", "")
            key = f"{tid}|{winner}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            if agency and rec.get("agency_target", "").upper() != agency.upper():
                continue
            all_records.append(rec)
            new += 1
        logger.info(f"  NOA page {page}: {new} new (total {len(all_records)})")
        if new < 50:
            break

    logger.info(f"NOA crawl complete: {len(all_records)} unique records")
    return all_records


# ── eContracts Scraper (NOA + Detail Pages for Package No) ─────────────

def _parse_econtract_detail(html: str) -> Dict[str, Any]:
    """Parse eContracts detail page (ViewAwardedContracts.jsp) for package_no & values."""
    result = {"package_no": "", "amount_bdt": 0.0, "winner": "", "procurement_method": "", "procuring_entity": "", "award_date": ""}
    tables = re.findall(r'<table[^>]*>(.*?)</table>', html, re.DOTALL | re.IGNORECASE)
    for table in tables:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.DOTALL)
        for row in rows:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL | re.IGNORECASE)
            texts = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            if len(texts) < 2:
                continue
            key = texts[0].strip()
            val = texts[1].strip() if len(texts) > 1 else ""
            if "Package No." in key:
                result["package_no"] = val
            elif "Contract Value" in key:
                try:
                    result["amount_bdt"] = float(val.replace(",", ""))
                except ValueError:
                    pass
            elif "Name of the Economic Operator" in key:
                result["winner"] = val
            elif "Procurement Method" in key:
                result["procurement_method"] = val
            elif "Procuring Entity Name" in key:
                result["procuring_entity"] = val
            elif "Date of Notification of Award" in key:
                result["award_date"] = val
            elif "Agency:" in key:
                if not result.get("procuring_entity"):
                    result["procuring_entity"] = val
    return result


def fetch_url_with_session(url: str, data: Optional[Dict] = None, retries: int = 3) -> Optional[str]:
    """Fetch URL using shared httpx session with POST support."""
    for attempt in range(retries):
        try:
            if _HTTPX is None:
                req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
                if data:
                    import urllib.parse
                    body = urllib.parse.urlencode(data).encode()
                    req.data = body
                    req.method = "POST"
                with urlopen(req, timeout=30) as resp:
                    return resp.read().decode("utf-8")
            else:
                if data:
                    resp = _HTTPX.post(url, data=data)
                else:
                    resp = _HTTPX.get(url)
                if resp.status_code == 200 and len(resp.text) > 100:
                    return resp.text
                return None
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
            else:
                logger.warning(f"  Failed after {retries} retries: {url[:80]}... -> {e}")
    return None


def scrape_noa_with_econtracts(max_pages: int = 20, max_workers: int = 10) -> List[Dict]:
    """Search NOA and fetch each eContracts detail page to extract package_no.

    Detail page fetches run in parallel via ThreadPoolExecutor.
    Only returns records with a valid package_no.

    Returns enriched award records with tender_id, package_no, winner, amount_bdt.
    """
    ensure_session()
    all_awards: List[Dict] = []
    seen_keys: Set[str] = set()

    for page in range(1, max_pages + 1):
        html = fetch_url_with_session(f"{EGP_BASE}/SearchNoaServlet", {"keyword": "", "pageNo": str(page), "size": "50"})
        if not html or "No Records Found" in html:
            break

        row_infos = []
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
        for row_html in rows:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row_html, re.DOTALL | re.IGNORECASE)
            if len(cells) < 8:
                continue
            cell2_html = cells[2]
            link_match = re.search(r'href=(["\'])(/resources/common/ViewAwardedContracts\.jsp[^"\']+)\1', cell2_html, re.DOTALL)
            if not link_match:
                continue
            detail_url = link_match.group(2)
            cell_text = re.sub(r'<[^>]+>', '', cell2_html).strip()
            tender_id = ""
            m = re.search(r'(\d{6,})', cell_text)
            if m:
                tender_id = m.group(1)
            winner_approx = re.sub(r'<[^>]+>', '', cells[6]).strip() if len(cells) > 6 else ""
            key = f"{tender_id}|{winner_approx}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            row_infos.append((cells, detail_url, cell_text, tender_id, winner_approx, key))

        if not row_infos:
            continue

        # Parallel detail page fetches
        def fetch_detail(info):
            cells, detail_url, cell_text, tender_id, winner_approx, key = info
            try:
                detail_html = fetch_url_with_session(f"{EGP_BASE}{detail_url}")
                detail = _parse_econtract_detail(detail_html) if detail_html else {}
                return (cells, detail, cell_text, tender_id, winner_approx, key)
            except Exception:
                return None

        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(fetch_detail, info): info for info in row_infos}
            for f in as_completed(futures):
                res = f.result()
                if res:
                    results.append(res)

        new = 0
        for cells, detail, cell_text, tender_id, winner_approx, key in results:
            package_no = detail.get("package_no", "")
            if not package_no:
                continue

            title = cell_text
            if ", " in cell_text:
                parts = cell_text.split(", ", 1)
                if len(parts) > 1:
                    title = parts[1]

            amount_bdt = 0.0
            amount_lac_text = re.sub(r'<[^>]+>', '', cells[7]).strip() if len(cells) > 7 else "0"
            try:
                amount_bdt = float(amount_lac_text.replace(",", "")) * 100_000
            except ValueError:
                pass
            if detail.get("amount_bdt", 0) > 0:
                amount_bdt = detail["amount_bdt"]

            entity_cell = re.sub(r'<[^>]+>', '', cells[1]).strip() if len(cells) > 1 else ""
            agency_target = extract_agency_id(entity_cell)

            award = {
                "tender_id": tender_id,
                "package_no": package_no,
                "title": title[:300] if title else "",
                "winner": detail.get("winner", winner_approx),
                "amount_bdt": amount_bdt,
                "procuring_entity": detail.get("procuring_entity", entity_cell),
                "office": re.sub(r'<[^>]+>', '', cells[3]).strip() if len(cells) > 3 else "",
                "location": re.sub(r'<[^>]+>', '', cells[4]).strip() if len(cells) > 4 else "",
                "award_date": detail.get("award_date", re.sub(r'<[^>]+>', '', cells[5]).strip() if len(cells) > 5 else ""),
                "source": "ECONTRACT",
                "agency_target": agency_target,
                "procurement_method": detail.get("procurement_method", ""),
                "procurement_nature": "Works",
            }
            all_awards.append(award)
            new += 1

        logger.info(f"  eContracts page {page}: {new} new with package_no (total {len(all_awards)})")
        if new < 50:
            break

    logger.info(f"eContracts scrape complete: {len(all_awards)} records with package_no")
    return all_awards


# ── Local File Loaders ────────────────────────────────────────────────

def load_local_app() -> List[Dict]:
    """Load APP records from local files (knowledge/app/, data_intel/, knowledge/tenders/)."""
    records: List[Dict] = []
    seen_ids: Set[str] = set()

    def _add(batch, src: str):
        for r in batch:
            if not isinstance(r, dict):
                continue
            tid = normalize_tender_id(r.get("tender_id", "") or "")
            if tid and tid in seen_ids:
                continue
            if tid:
                seen_ids.add(tid)
            # Always try to extract meaningful package_no from title
            title_pkg = extract_pkg_from_title(r.get("title", ""))
            if title_pkg:
                r["package_no"] = title_pkg
            records.append(r)

    # knowledge/app/
    for fp in sorted((KNOWLEDGE / "app").glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            _add(data if isinstance(data, list) else data.get("records", data.get("data", [])), str(fp))
        except Exception as e:
            logger.warning(f"  Skip {fp.name}: {e}")

    # data_intel/tenders_*.json
    di = RUNTIME / "data_intel"
    for pattern in ["tenders_all_*.json", "tenders_live_*.json", "bwdb_all_tenders.json"]:
        for fp in sorted(di.glob(pattern)):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                _add(data if isinstance(data, list) else data.get("records", data.get("data", [])), str(fp))
            except Exception:
                pass

    # knowledge/tenders/
    for fp in sorted((KNOWLEDGE / "tenders").glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            _add(data if isinstance(data, list) else data.get("records", data.get("data", [])), str(fp))
        except Exception:
            pass

    return records


def load_local_awards() -> List[Dict]:
    """Load award records from local files (awards_batch/, data_intel/awards_*)."""
    records: List[Dict] = []
    seen_keys: Set[str] = set()

    def _add(batch, src: str):
        for r in batch:
            if not isinstance(r, dict):
                continue
            tid = normalize_tender_id(r.get("tender_id", "") or "")
            winner = (r.get("winner") or "").strip()
            if not tid or not winner or winner == "Unknown":
                continue
            key = f"{tid}|{winner}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            # Normalize amount
            amt = r.get("amount_bdt", 0) or r.get("award_amount", 0) or 0
            records.append({
                "tender_id": tid,
                "winner": winner,
                "amount_bdt": float(amt),
                "title": r.get("title", ""),
                "package_no": r.get("package_no", ""),
                "procuring_entity": r.get("procuring_entity", ""),
                "office": r.get("office", ""),
                "location": r.get("location", ""),
                "award_date": r.get("award_date", "") or r.get("publishing_date", ""),
                "source": r.get("source", src),
                "agency_target": r.get("agency_target", "") or extract_agency_id(r.get("procuring_entity", "") + " " + r.get("office", "")),
                "procurement_nature": r.get("procurement_nature", "Works"),
                "procurement_method": r.get("procurement_method", ""),
            })

    # awards_batch/ (primary)
    for fp in sorted((KNOWLEDGE / "awards_batch").glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            _add(data if isinstance(data, list) else data.get("records", data.get("data", [])), str(fp))
        except Exception:
            pass

    # data_intel/awards_*
    for fp in sorted((RUNTIME / "data_intel").glob("awards_*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            _add(data if isinstance(data, list) else data.get("records", data.get("data", [])), str(fp))
        except Exception:
            pass

    return records


# ── Matcher ───────────────────────────────────────────────────────────

def match_app_to_awards(
    app_records: List[Dict],
    award_records: List[Dict],
) -> Tuple[List[Dict], List[Dict]]:
    """
    Match APP ↔ awards using ONLY package_no (as required for eContracts data).
    Returns (matches_list, unmatched_awards_list).
    """
    # Pre-compute APP package_no index (both raw and normalized)
    app_by_pkg: Dict[str, Dict] = {}
    app_by_norm_pkg: Dict[str, List[Dict]] = {}

    for app in app_records:
        # Primary: package_no field
        raw_pkg = (app.get("package_no") or "").strip()
        if raw_pkg:
            app_by_pkg[raw_pkg.upper()] = app
        # Normalized version
        norm_pkg = normalize_package_no(raw_pkg)
        if norm_pkg and norm_pkg != raw_pkg.upper():
            app_by_norm_pkg.setdefault(norm_pkg, []).append(app)
        # Fallback: extract package from title prefix
        title_pkg = extract_pkg_from_title(app.get("title", "")).upper()
        if title_pkg and title_pkg not in app_by_pkg:
            app_by_pkg[title_pkg] = app
        norm_title_pkg = normalize_package_no(title_pkg)
        if norm_title_pkg and norm_title_pkg != title_pkg and norm_title_pkg not in app_by_norm_pkg:
            app_by_norm_pkg.setdefault(norm_title_pkg, []).append(app)

    # Build tender_id index for secondary matching
    app_by_tid: Dict[str, Dict] = {}
    for app in app_records:
        tid = normalize_tender_id(app.get("tender_id", "") or "")
        if tid:
            app_by_tid[tid] = app

    indexed_count = len(app_by_pkg) + len(app_by_norm_pkg)
    logger.info(f"  Indexed {len(app_by_pkg)} APP package_no entries + {len(app_by_norm_pkg)} normalized")

    matches: List[Dict] = []

    for award in award_records:
        aid = award["tender_id"]
        awinner = award["winner"]
        award_title = award.get("title", "")
        award_pkg_raw = (award.get("package_no") or "").strip().upper()

        # Skip awards without a valid package_no
        if not award_pkg_raw:
            continue

        best_app = None
        match_strategy = "none"

        # Strategy 1: Exact package_no match
        if award_pkg_raw in app_by_pkg:
            best_app = app_by_pkg[award_pkg_raw]
            match_strategy = "package_exact"
        else:
            # Strategy 2: Normalized package_no match
            norm_award_pkg = normalize_package_no(award_pkg_raw)
            if norm_award_pkg and norm_award_pkg in app_by_norm_pkg:
                candidates = app_by_norm_pkg[norm_award_pkg]
                if candidates:
                    best_app = candidates[0]
                    match_strategy = "package_normalized"
            if not best_app:
                # Strategy 3: Extract package from award title
                award_title_pkg = extract_pkg_from_title(award_title).upper()
                if award_title_pkg and award_title_pkg in app_by_pkg:
                    best_app = app_by_pkg[award_title_pkg]
                    match_strategy = "package_title_fallback"
            if not best_app:
                # Strategy 4: Match by tender_id
                norm_aid = normalize_tender_id(aid)
                if norm_aid and norm_aid in app_by_tid:
                    best_app = app_by_tid[norm_aid]
                    match_strategy = "tender_id_exact"

        estimated = float(best_app.get("estimated_amount_bdt", 0) or 0) if best_app else 0
        award_amt = float(award.get("amount_bdt", 0) or 0)

        npp = 0.0
        discount_pct = 0.0
        if estimated > 0 and award_amt > 0:
            npp = round((estimated - award_amt) / estimated, 6)
            discount_pct = round(npp * 100, 2)

        year = 0
        ad = award.get("award_date", "")
        m = re.search(r"(\d{4})", ad)
        if m:
            year = int(m.group(1))

        matches.append({
            "tender_id": aid,
            "package_no_award": award_pkg_raw,
            "package_no_app": best_app.get("package_no", "") if best_app else "",
            "winner": awinner,
            "award_amount_bdt": award_amt,
            "estimated_amount_bdt": estimated,
            "npp": npp,
            "discount_pct": discount_pct,
            "title": award_title,
            "agency": award["agency_target"],
            "procuring_entity": award.get("procuring_entity", ""),
            "award_date": award.get("award_date", ""),
            "year": year,
            "match_strategy": match_strategy,
            "procurement_nature": award.get("procurement_nature", "Works"),
            "procurement_method": award.get("procurement_method", ""),
        })

    matched = sum(1 for m in matches if m["match_strategy"] != "none")
    standalone = len(matches) - matched
    logger.info(f"Matched: {matched} APP→award via package_no + {standalone} standalone = {len(matches)} total")
    return matches, [m for m in matches if m["match_strategy"] == "none"]


# ── Synthetic APP Generator ───────────────────────────────────────────

def synthesize_app_for_unmatched(
    unmatched: List[Dict],
    matched_stats: Dict[str, Dict],
) -> List[Dict]:
    """
    For unmatched awards, estimate APP value:
    - Use average discount from same agency + procurement_nature matches
    - Fallback: assume 8% discount (estimate = award / 0.92)
    """
    # Compute average NPP per (agency, nature)
    agency_nature_npp: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    for m in matched_stats.get("all_matches", []):
        if m["npp"] != 0:
            agency_nature_npp[(m["agency"], m.get("procurement_nature", "Works"))].append(m["npp"])

    synthetic = []
    for award in unmatched:
        key = (award["agency"], award.get("procurement_nature", "Works"))
        avg_npp = 0.074  # default ~7.4% (1 - 1/1.08)
        if key in agency_nature_npp:
            vals = agency_nature_npp[key]
            avg_npp = sum(vals) / len(vals)
        elif award["agency"] in matched_stats.get("agency_avg_npp", {}):
            avg_npp = matched_stats["agency_avg_npp"][award["agency"]]

        # If avg_npp is negative (award > estimate), clamp to a reasonable range
        if avg_npp > 0.2:
            avg_npp = 0.074
        if avg_npp < -0.1:
            avg_npp = 0.074

        award_amt = award.get("award_amount_bdt", award.get("amount_bdt", 0))
        estimated = round(award_amt / (1 - avg_npp), 2) if award_amt > 0 else 0
        npp = round((estimated - award_amt) / estimated, 6) if estimated > 0 else 0
        discount_pct = round(npp * 100, 2)

        award["estimated_amount_bdt"] = estimated
        award["npp"] = npp
        award["discount_pct"] = discount_pct
        award["match_strategy"] = "synthetic"
        synthetic.append(award)

    logger.info(f"Synthetic APP created for {len(synthetic)} unmatched awards (avg NPP={avg_npp:.4f})")
    return synthetic


# ── Aggregation ───────────────────────────────────────────────────────

def build_contractor_dna(all_matches: List[Dict]) -> Dict[str, Dict]:
    """Aggregate award data into contractor DNA profiles with NPP/discount."""
    groups: Dict[str, List[Dict]] = defaultdict(list)
    for m in all_matches:
        groups[m["winner"]].append(m)

    profiles: Dict[str, Dict] = {}

    for name, entries in groups.items():
        wins = len(entries)
        amounts = [e["award_amount_bdt"] for e in entries if e["award_amount_bdt"]]
        discounts = [e["discount_pct"] for e in entries if e["match_strategy"] != "none" and (e["estimated_amount_bdt"] > 0)]
        years = sorted(set(e["year"] for e in entries if e["year"] > 0))

        total_amount = round(sum(amounts), 2)
        avg_amount = round(total_amount / len(amounts), 2) if amounts else 0
        avg_discount = round(sum(discounts) / len(discounts), 2) if discounts else 0

        # Per-agency breakdown
        ag_groups: Dict[str, List[Dict]] = defaultdict(list)
        for e in entries:
            ag_groups[e["agency"]].append(e)

        agencies: Dict[str, Any] = {}
        for ag, ag_entries in ag_groups.items():
            ag_amts = [e["award_amount_bdt"] for e in ag_entries if e["award_amount_bdt"]]
            ag_discs = [e["discount_pct"] for e in ag_entries if e["estimated_amount_bdt"] > 0]
            ag_ys = sorted(set(e["year"] for e in ag_entries if e["year"] > 0))
            recent = sorted(ag_entries, key=lambda x: x["year"], reverse=True)[:20]

            agencies[ag] = {
                "wins": len(ag_entries),
                "total_amount": round(sum(ag_amts), 2),
                "avg_amount": round(sum(ag_amts) / len(ag_amts), 2) if ag_amts else 0,
                "avg_discount_pct": round(sum(ag_discs) / len(ag_discs), 2) if ag_discs else 0,
                "first_award": str(min(ag_ys)) if ag_ys else "",
                "last_award": str(max(ag_ys)) if ag_ys else "",
                "tenders": [
                    {"tender_id": e["tender_id"], "amount": e["award_amount_bdt"],
                     "discount": e["discount_pct"], "year": e["year"]}
                    for e in recent
                ],
            }

        ptype_count: Dict[str, int] = defaultdict(int)
        for e in entries:
            ptype_count[e.get("procurement_nature", "Works")] += 1

        top_agency = max(agencies, key=lambda a: agencies[a]["wins"]) if agencies else "NONE"

        profiles[name] = {
            "contractor_name": name,
            "slug": slugify(name),
            "total_wins": wins,
            "total_amount_bdt": total_amount,
            "avg_amount_bdt": avg_amount,
            "avg_discount_percent": avg_discount,
            "years_active": [min(years), max(years)] if years else [],
            "procurement_type_breakdown": dict(ptype_count),
            "agencies": agencies,
            "top_agency": top_agency,
            "top_agency_wins": agencies[top_agency]["wins"] if top_agency in agencies else wins,
            "win_probability": {ag: round(agencies[ag]["wins"] / wins, 2) for ag in agencies} if wins > 0 else {},
            "_domain": "contractor_dna",
        }

    logger.info(f"Built {len(profiles)} contractor DNA profiles")
    return profiles


def build_agency_npp_trends(all_matches: List[Dict]) -> Dict[str, Any]:
    """Compute NPP trends per agency per month."""
    from collections import defaultdict
    monthly: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))

    for m in all_matches:
        if m["npp"] == 0 and m["match_strategy"] == "none":
            continue
        agency = m["agency"]
        month_key = str(m["year"]) if m["year"] else "unknown"
        monthly[agency][month_key].append(m["npp"])

    trends = {}
    for agency, months in monthly.items():
        trends[agency] = {}
        for month, npp_values in sorted(months.items()):
            vals = [v for v in npp_values if v != 0]
            if not vals:
                continue
            trends[agency][month] = {
                "count": len(vals),
                "avg_npp": round(sum(vals) / len(vals), 4),
                "min_npp": round(min(vals), 4),
                "max_npp": round(max(vals), 4),
            }

    # Also build a consolidated summary
    agency_summary = {}
    for agency, months in trends.items():
        all_npp = []
        for month_data in months.values():
            all_npp.append(month_data["avg_npp"])
        agency_summary[agency] = {
            "avg_npp": round(sum(all_npp) / len(all_npp), 4) if all_npp else 0,
            "monthly": months,
        }

    return agency_summary


def build_rate_analysis(all_matches: List[Dict]) -> Dict[str, Any]:
    """Build rate analytics per agency: avg discount by work type."""
    from collections import defaultdict
    rates: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))

    for m in all_matches:
        if m["estimated_amount_bdt"] <= 0:
            continue
        agency = m["agency"]
        nature = m.get("procurement_nature", "Works")
        rates[agency][nature].append(m["discount_pct"])

    result = {}
    for agency, natures in rates.items():
        result[agency] = {}
        for nature, discounts in natures.items():
            vals = [d for d in discounts if d != 0]
            if not vals:
                continue
            result[agency][nature] = {
                "count": len(vals),
                "avg_discount_pct": round(sum(vals) / len(vals), 2),
                "min_discount_pct": round(min(vals), 2),
                "max_discount_pct": round(max(vals), 2),
            }
    return result


# ── Writer ────────────────────────────────────────────────────────────

def write_output(
    profiles: Dict[str, Dict],
    npp_trends: Dict,
    rate_analysis: Dict,
    all_matches: List[Dict],
    rebuild: bool = False,
) -> None:
    """Write all outputs to knowledge/ directory."""
    now = datetime.now().isoformat()

    # 1. Contractor DNA
    dna_dir = KNOWLEDGE / "contractordna"
    dna_dir.mkdir(parents=True, exist_ok=True)
    if rebuild:
        for f in dna_dir.glob("*.json"):
            f.unlink()

    for name, profile in profiles.items():
        slug = profile["slug"]
        (dna_dir / f"{slug}.json").write_text(
            json.dumps(profile, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    idx = sorted(
        [{"slug": p["slug"], "contractor_name": p["contractor_name"],
          "total_wins": p["total_wins"], "total_amount_bdt": p["total_amount_bdt"],
          "avg_discount_percent": p["avg_discount_percent"],
          "years_active": p["years_active"], "top_agency": p["top_agency"],
          "top_agency_wins": p["top_agency_wins"]} for p in profiles.values()],
        key=lambda x: x["total_wins"], reverse=True,
    )
    (dna_dir / "_index.json").write_text(
        json.dumps({"generated_at": now, "total_contractors": len(profiles), "contractors": idx},
                    indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Wrote {len(profiles)} contractor DNA profiles")

    # 2. NPP Trends
    npp_dir = KNOWLEDGE / "npp"
    npp_dir.mkdir(parents=True, exist_ok=True)
    (npp_dir / "trends.json").write_text(
        json.dumps({"generated_at": now, "trends": npp_trends}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    logger.info(f"Wrote NPP trends ({len(npp_trends)} agencies)")

    # 3. Rates analysis
    rates_dir = KNOWLEDGE / "rates"
    rates_dir.mkdir(parents=True, exist_ok=True)
    for agency, data in rate_analysis.items():
        (rates_dir / f"{agency}_rates.json").write_text(
            json.dumps({"generated_at": now, "agency": agency, "rates": data},
                        indent=2, ensure_ascii=False), encoding="utf-8")
    (rates_dir / "agency_rates.json").write_text(
        json.dumps({ag: {"avg_discount_pct": sum(d["avg_discount_pct"] for d in data.values())/len(data) if data else 0,
                         "sample_size": sum(d["count"] for d in data.values())}
                    for ag, data in rate_analysis.items()},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Wrote rate analytics ({len(rate_analysis)} agencies)")

    # 4. Full match dump (for agent consumption)
    match_dir = KNOWLEDGE / "matches"
    match_dir.mkdir(parents=True, exist_ok=True)
    matched_ct = sum(1 for m in all_matches if m["match_strategy"] != "none")
    (match_dir / "all_matches.json").write_text(
        json.dumps({
            "generated_at": now,
            "total": len(all_matches),
            "matched": matched_ct,
            "standalone": len(all_matches) - matched_ct,
            "matches": all_matches,
        }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    logger.info(f"Wrote {len(all_matches)} match records")


# ── Main Pipeline ─────────────────────────────────────────────────────

def main(
    agency: Optional[str] = None,
    rebuild: bool = False,
    skip_crawl: bool = False,
    skip_app_crawl: bool = False,
    max_econtract_pages: int = 20,
) -> None:
    """Orchestrate the complete intelligence pipeline."""
    logger.info(f"Knowledge root: {KNOWLEDGE}")
    start = time.time()

    # ── Step 1: Load/Crawl APP data ──
    app_records = load_local_app()
    if not skip_crawl and not skip_app_crawl:
        logger.info("Crawling APP from eGP public SearchAPPServlet...")
        crawled = crawl_app(agency=agency)
        seen_tids = set(r.get("tender_id", "") for r in app_records if r.get("tender_id"))
        for r in crawled:
            tid = r.get("tender_id", "")
            if tid and tid not in seen_tids:
                app_records.append(r)
                seen_tids.add(tid)
        # Save merged APP data
        agency_name = (agency or "ALL").upper()
        out = KNOWLEDGE / "app" / f"{agency_name}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(app_records, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        logger.info(f"Saved {len(app_records)} APP records to {out}")
    logger.info(f"APP: {len(app_records)} records")

    # ── Step 2: Scrape eContracts award data (NOA + detail pages) ──
    award_records: List[Dict] = []
    if not skip_crawl:
        logger.info(f"Scraping eContracts (NOA + details, {max_econtract_pages} pages)...")
        award_records = scrape_noa_with_econtracts(max_pages=max_econtract_pages)
    else:
        # Fallback: load local awards (eExperience data) if --skip-crawl
        logger.info("Loading local award data (fallback)...")
        award_records = load_local_awards()
    logger.info(f"Awards/eContracts: {len(award_records)} records")

    if not app_records and not award_records:
        logger.error("No data found!")
        sys.exit(1)

    # ── Step 3: Match APP ↔ awards (ONLY by package_no) ──
    logger.info("Matching APP ↔ awards by package_no...")
    all_matches, unmatched_awards = match_app_to_awards(app_records, award_records)

    # ── Step 4: Synthesize APP estimates for unmatched awards ──
    agency_npp: Dict[str, List[float]] = defaultdict(list)
    for m in all_matches:
        if m["npp"] != 0:
            agency_npp[m["agency"]].append(m["npp"])
    agency_avg_npp = {ag: sum(v)/len(v) for ag, v in agency_npp.items()}

    synthetic_count = 0
    for m in all_matches:
        if m["match_strategy"] != "none" or m["estimated_amount_bdt"] > 0:
            continue
        amt = m["award_amount_bdt"]
        if amt <= 0:
            continue
        # Use agency-specific avg NPP or default 7.4%
        avg_npp = agency_avg_npp.get(m["agency"], 0.074)
        if abs(avg_npp) > 0.2:
            avg_npp = 0.074
        estimated = round(amt / (1 - avg_npp), 2)
        m["estimated_amount_bdt"] = estimated
        m["npp"] = round((estimated - amt) / estimated, 6)
        m["discount_pct"] = round(m["npp"] * 100, 2)
        m["match_strategy"] = "synthetic"
        synthetic_count += 1

    matched_final = sum(1 for m in all_matches if m["match_strategy"] != "none")
    logger.info(f"Final: {matched_final} matched (incl. {synthetic_count} synthetic)")

    # ── Step 5: Build contractor DNA ──
    logger.info("Building contractor DNA...")
    profiles = build_contractor_dna(all_matches)

    # ── Step 6: NPP Trends ──
    logger.info("Building NPP trends...")
    npp_trends = build_agency_npp_trends(all_matches)

    # ── Step 7: Rate Analysis ──
    logger.info("Building rate analysis...")
    rate_analysis = build_rate_analysis(all_matches)

    # ── Step 8: Write output ──
    write_output(profiles, npp_trends, rate_analysis, all_matches, rebuild=rebuild)

    elapsed = round(time.time() - start, 1)
    logger.info(f"=== Complete in {elapsed}s: {len(profiles)} contractors, {len(all_matches)} awards, {len(npp_trends)} agencies ===")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build complete procurement intelligence database")
    parser.add_argument("--agency", default=None, help="Filter single agency")
    parser.add_argument("--rebuild", action="store_true", help="Force overwrite output")
    parser.add_argument("--skip-crawl", action="store_true", help="Skip ALL eGP crawling (APP + eContracts), use only local data")
    parser.add_argument("--skip-app-crawl", action="store_true", help="Skip only APP crawl (use cached), still scrape eContracts")
    parser.add_argument("--max-econtract-pages", type=int, default=20, help="Max pages of eContracts to scrape (50 records/page)")
    parser.add_argument("--refresh-offices", type=str, default=None, help="Force refresh office cache for dept (e.g. BWDB, LGED, ALL)")
    parser.add_argument("--all", action="store_true", help="Crawl ALL known departments (BWDB, LGED, RHD, PWD, BADC, HED, etc.)")
    args = parser.parse_args()
    if args.refresh_offices:
        if args.refresh_offices.upper() == "ALL":
            for name, info in AGENCY_DEPT_MAP.items():
                fetch_offices(info["id"], info["name"], force_refresh=True)
        elif args.refresh_offices.upper() in AGENCY_DEPT_MAP:
            info = AGENCY_DEPT_MAP[args.refresh_offices.upper()]
            fetch_offices(info["id"], info["name"], force_refresh=True)
    agency_arg = "ALL" if args.all else args.agency
    main(agency=agency_arg, rebuild=args.rebuild, skip_crawl=args.skip_crawl, skip_app_crawl=args.skip_app_crawl, max_econtract_pages=args.max_econtract_pages)
