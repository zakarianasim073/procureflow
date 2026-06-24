"""
eGP Complete Crawler — APP / Award (NOA) / eExperience (eTenders+eCMS)
=====================================================================
All sources PUBLIC. No login required.
Outputs structured JSON organized by agency, with package_no + work_name
in every record as the primary join key.

Usage:
    python crawl_egp_all.py                        # Crawl all sources
    python crawl_egp_all.py --sources app,award     # Only APP + Awards
    python crawl_egp_all.py --sources experience    # Only eTenders+eCMS
    python crawl_egp_all.py --output ./my_data      # Custom output
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("egp-crawler")

BASE_URL = "https://www.eprocure.gov.bd"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "crawl_output"

AGENCIES = [
    "BADC", "BANGLADESH", "BBA", "BIWTA", "BPDB", "BREB", "BWDB",
    "CHIEF", "COMMON", "DKMP", "DPHE", "EDUCATION", "ENGINEERIN",
    "EXECUTIVE", "HED", "INFORMATIO", "LGED", "MINISTRY", "OFFICE",
    "PIU", "PWD", "RAILWAY", "RAJUK", "REB", "RHD", "UPGRADING", "WASA",
]

# ── Schema fields per source (package_no + work_name in all) ────────
APP_FIELDS = [
    "tender_id", "package_no", "work_name", "agency", "location", "district",
    "estimated_cost_bdt", "title", "status", "financial_year",
    "app_code", "category", "published_date", "deadline",
]

AWARD_FIELDS = [
    "tender_id", "package_no", "work_name", "amount_bdt", "contractor_name",
    "procurement_method", "award_date", "agency_code", "district", "pe_office",
]

EXPERIENCE_FIELDS = [
    "package_no", "work_name", "contract_value_bdt", "completed_value_bdt",
    "contractor_name", "completion_status", "completed_on_time",
    "actual_completion_date", "planned_completion_date",
    "contract_start_date", "contract_end_date", "progress_pct",
    "district", "agency_code", "pe_name",
]

# ── Helpers ─────────────────────────────────────────────────────────

def _parse_amount(text: str) -> float:
    text = (text or "").strip()
    if not text:
        return 0.0
    m = re.search(r"([\d,]+(?:\.\d+)?)", text)
    return float(m.group(1).replace(",", "")) if m else 0.0


def _extract_dates(text: str) -> List[str]:
    return re.findall(
        r"\b\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}\b"
        r"|\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b"
        r"|\b\d{4}-\d{2}-\d{2}\b",
        text or "",
    )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _is_noise(text: str) -> bool:
    noise = (
        "home page", "about e-gp", "forgot password", "user login",
        "annual procurement plans", "econtracts", "eexperience",
        "advance search", "view all notifications", "copyright",
    )
    t = _normalize(text).lower()
    return any(m in t for m in noise)


def _is_usable_contractor(text: str) -> bool:
    name = _normalize(text)
    if len(name) < 5 or len(re.sub(r"[^A-Za-z]", "", name)) < 4:
        return False
    skip = re.compile(r"\b(jv|joint venture|consortium)\b", re.IGNORECASE)
    return not skip.search(name) and not _is_noise(name)


def _pick_district(text: str) -> str:
    for d in [
        "DHAKA", "CHATTOGRAM", "KHULNA", "RAJSHAHI", "BARISHAL",
        "SYLHET", "RANGPUR", "MYMENSINGH",
    ]:
        if d in text.upper():
            return d.capitalize()
    return ""


NOISE_MARKERS = (
    "home page", "about e-gp", "forgot password", "user login",
    "annual procurement plans", "econtracts", "eexperience",
    "advance search", "view all notifications", "copyright",
)

# ══════════════════════════════════════════════════════════════════════
#  1. EXPERIENCE CRAWLER — eTenders (completed) + eCMS (ongoing)
#     Public endpoint: AdvSearcheCMSServlet
# ══════════════════════════════════════════════════════════════════════

class ExperienceCrawler:
    """Crawls eExperience completed (eTenders tab) and ongoing (eCMS tab)."""

    AJAX_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": f"{BASE_URL}/resources/common/SearcheCMS.jsp",
        "Origin": BASE_URL,
        "X-Requested-With": "XMLHttpRequest",
    }

    def __init__(self, client: httpx.Client, delay: float = 0.3):
        self.client = client
        self.delay = delay

    def crawl_all(self, max_pages: int = 0) -> Tuple[List[Dict], List[Dict]]:
        """Crawl all eTenders (completed) + eCMS (ongoing)."""
        completed = self._crawl_tab("eTenders", "EEXPERIENCE_ALL", max_pages)
        ongoing = self._crawl_tab("eCMS", "ECMS_ONGOING", max_pages)
        return completed, ongoing

    def _fetch_page(self, status_tab: str, page: int, size: int = 100) -> Optional[str]:
        for attempt in range(3):
            try:
                self.client.get(
                    f"{BASE_URL}/resources/common/SearcheCMS.jsp",
                    headers=self.AJAX_HEADERS, timeout=20,
                )
                resp = self.client.post(
                    f"{BASE_URL}/AdvSearcheCMSServlet",
                    headers=self.AJAX_HEADERS,
                    data={
                        "action": "geteCMSList",
                        "keyword": "", "expCertNo": "", "officeId": "",
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
                        "workStatus": "All",
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
                    logger.warning(f"  Fetch page {page} failed: {e}")
        return None

    def _fetch_total_pages(self, status_tab: str) -> int:
        html = self._fetch_page(status_tab, 1)
        if not html:
            return 0
        m = re.search(r'id="totalPages"[^>]*value="(\d+)"', html)
        return int(m.group(1)) if m else 1

    def _crawl_tab(self, status_tab: str, source: str, max_pages: int = 0) -> List[Dict]:
        total = self._fetch_total_pages(status_tab)
        pages = min(max_pages, total) if max_pages > 0 else total
        logger.info(f"[{status_tab}] Total pages: {total}, crawling {pages} pages")

        all_records: List[Dict] = []
        seen_keys: set = set()

        for page in range(1, pages + 1):
            html = self._fetch_page(status_tab, page)
            if not html:
                break
            records = self._parse_page(html, source)
            if not records:
                break
            new = 0
            for rec in records:
                key = f"{rec['tender_id']}-{rec['contractor_name']}-{rec['contract_start_date']}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_records.append(rec)
                    new += 1
            if page % 50 == 0 or page == pages:
                logger.info(f"  Page {page}/{pages}: +{new} new, {len(all_records)} total")
            if new == 0:
                break
            time.sleep(self.delay)

        return all_records

    def _parse_page(self, html: str, source: str) -> List[Dict]:
        soup = BeautifulSoup(f"<table>{html}</table>", "html.parser")
        records = []
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) != 10:
                continue
            text = [_normalize(c.get_text(" ", strip=True)) for c in cells]
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

            # tender_id
            tender_match = re.search(r"^\s*(\d{6,})\s*,", title_block)

            # ref_no / package_no from <a> tag
            title_link = row.find("a")
            title_text = _normalize(title_link.get_text(" ", strip=True)) if title_link else ""
            ref_no = ""
            if title_link:
                cell_html = str(cells[3])
                before_a = cell_html.split("<a", 1)[0] if "<a" in cell_html else ""
                raw_before = BeautifulSoup(before_a, "html.parser").get_text(" ", strip=True)
                ref_parts = re.sub(r"^\s*\d{6,}\s*,\s*", "", raw_before).strip()
                ref_no = re.sub(r"[,;\-]+$", "", ref_parts).strip()[:250]
            if not ref_no:
                ref_match = re.search(r"^\s*\d{6,}\s*,\s*([^,]+?)\s{2,}", title_block)
                if ref_match:
                    ref_no = ref_match.group(1).strip()[:250]
            title = title_text or title_block
            dates = _extract_dates(text[8])
            pub_dates = _extract_dates(title_block)

            record = {
                "tender_id": tender_match.group(1) if tender_match else "",
                "package_no": ref_no or "",
                "work_name": title[:300],
                "title": title[:500],
                "pe_name": pe_office,
                "agency_code": "",
                "procurement_method": text[2],
                "contractor_name": contractor_name,
                "company_unique_id": text[5],
                "experience_certificate_no": text[6],
                "contract_value_bdt": _parse_amount(text[7]),
                "completed_value_bdt": _parse_amount(text[7]),
                "contract_start_date": dates[0] if len(dates) > 0 else "",
                "contract_end_date": dates[1] if len(dates) > 1 else "",
                "planned_completion_date": dates[1] if len(dates) > 1 else "",
                "actual_completion_date": dates[1] if status == "Completed" and len(dates) > 1 else "",
                "published_date": pub_dates[-1] if pub_dates else "",
                "completion_status": status.lower(),
                "work_status": status,
                "status": status.lower(),
                "progress_pct": 100.0 if status == "Completed" else 0.0,
                "completed_on_time": None,
                "district": _pick_district(title_block + " " + pe_office),
                "data_source": source,
            }
            records.append(record)
        return records


# ══════════════════════════════════════════════════════════════════════
#  2. APP CRAWLER — SearchAPPServlet (public)
# ══════════════════════════════════════════════════════════════════════

class APPCrawler:
    """Crawls Annual Procurement Plans."""

    def __init__(self, client: httpx.Client, delay: float = 0.5):
        self.client = client
        self.delay = delay

    def crawl_agency(self, agency: str) -> List[Dict]:
        results: List[Dict] = []
        page = 1
        total_pages = 1

        while page <= total_pages:
            for attempt in range(3):
                try:
                    self.client.get(BASE_URL, timeout=10)
                    resp = self.client.post(
                        f"{BASE_URL}/SearchAPPServlet",
                        data={
                            "bTypeId": "",
                            "pageNo": str(page),
                            "office": agency,
                            "action": "advSearch",
                            "size": "100",
                            "keyWord": agency,
                        },
                        timeout=15,
                    )
                    if resp.status_code == 200 and len(resp.text) > 200:
                        page_data, total_pages = self._parse(resp.text, agency)
                        results.extend(page_data)
                        break
                except Exception as e:
                    if attempt < 2:
                        time.sleep(2)
                    else:
                        logger.warning(f"  APP page {page} failed: {e}")
            page += 1
            if page <= total_pages:
                time.sleep(self.delay)
        return results

    def _parse(self, html: str, agency: str) -> Tuple[List[Dict], int]:
        """
        APP table columns (from live eGP):
          Col[0]: row number
          Col[1]: tender_id (NUMERIC, universal key across ALL sources)
          Col[2]: app_code (reference)
          Col[3]: category (e.g. "Goods," / "Works, - Select Project -")
          Col[4]: package_no, work_name (first part = package_no, after comma = title)
          Col[5]: estimated_cost_bdt, procurement_method
        """
        records = []
        total_pages = 1
        pm = re.search(r'id="totalPages"\s*value="(\d+)"', html)
        if pm:
            total_pages = int(pm.group(1))

        soup = BeautifulSoup(html, "html.parser")
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 6:
                continue
            texts = [_normalize(c.get_text(" ", strip=True)) for c in cells]
            if not texts[0].isdigit():
                continue

            rec: Dict[str, Any] = {
                "agency": agency,
                "estimated_cost_bdt": 0.0,
                "status": "APP",
            }

            # Col[1]: tender_id — PRIMARY UNIVERSAL KEY
            rec["tender_id"] = texts[1] if len(texts) > 1 and texts[1].isdigit() else ""

            # Col[2]: app_code
            rec["app_code"] = texts[2][:100] if len(texts) > 2 else ""

            # Col[3]: category
            cat = texts[3] if len(texts) > 3 else ""
            for kw in ["Goods", "Works", "Service", "Physical", "Consultancy", "ICT", "Supply"]:
                if kw.lower() in cat.lower():
                    rec["category"] = kw
                    break
            rec.setdefault("category", cat.split(",")[0].strip()[:50])

            # Col[4]: "package_no, work_name"
            col4 = texts[4] if len(texts) > 4 else ""
            if ", " in col4:
                parts = col4.split(", ", 1)
                rec["package_no"] = parts[0].strip()[:250]
                rec["work_name"] = parts[1].strip()[:300]
                rec["title"] = col4[:500]
            else:
                rec["package_no"] = col4[:250]
                rec["work_name"] = col4[:300]
                rec["title"] = col4[:500]
            # Override work_name from <a> tag if available (cleaner text)
            a_tag = row.find("a")
            if a_tag:
                a_text = _normalize(a_tag.get_text(" ", strip=True))
                if a_text:
                    rec["work_name"] = a_text[:300]

            # Col[5]: "estimated_cost_bdt, procurement_method"
            col5 = texts[5] if len(texts) > 5 else ""
            if "," in col5:
                parts5 = col5.split(",", 1)
                try:
                    rec["estimated_cost_bdt"] = float(parts5[0].replace(",", "").strip())
                except ValueError:
                    rec["estimated_cost_bdt"] = 0.0
                rec["procurement_method"] = parts5[1].strip()[:100]
            else:
                try:
                    rec["estimated_cost_bdt"] = float(col5.replace(",", "").strip())
                except ValueError:
                    rec["estimated_cost_bdt"] = 0.0

            # Try to extract dates and financial_year from full text
            full = " ".join(texts)
            dates = _extract_dates(full)
            if dates:
                rec["published_date"] = dates[0]
                if len(dates) > 1:
                    rec["deadline"] = dates[1]
            fym = re.search(r"(20\d{2}[-/]20\d{2})", full)
            if fym:
                rec["financial_year"] = fym.group(1)

            # District from full text
            d = _pick_district(full)
            if d:
                rec["district"] = d

            if rec.get("tender_id") or rec.get("package_no"):
                records.append(rec)

        return records, total_pages


# ══════════════════════════════════════════════════════════════════════
#  3. AWARD (NOA) CRAWLER — SearchNoaServlet (public)
# ══════════════════════════════════════════════════════════════════════

class AwardCrawler:
    """Crawls Notification of Award."""

    def __init__(self, client: httpx.Client, delay: float = 0.5):
        self.client = client
        self.delay = delay

    def crawl_agency(self, agency: str) -> List[Dict]:
        results: List[Dict] = []
        page = 1
        total_pages = 1

        while page <= total_pages:
            for attempt in range(3):
                try:
                    self.client.get(BASE_URL, timeout=10)
                    resp = self.client.post(
                        f"{BASE_URL}/SearchNoaServlet",
                        data={"keyword": agency, "pageNo": str(page), "size": "100"},
                        timeout=15,
                    )
                    if resp.status_code == 200 and len(resp.text) > 200:
                        page_data, total_pages = self._parse(resp.text)
                        results.extend(page_data)
                        break
                except Exception as e:
                    if attempt < 2:
                        time.sleep(2)
                    else:
                        logger.warning(f"  NOA page {page} failed: {e}")
            page += 1
            if page <= total_pages:
                time.sleep(self.delay)
        return results

    def _parse(self, html: str) -> Tuple[List[Dict], int]:
        records = []
        total_pages = 1
        # Same totalPages detection as APP parser
        pm = re.search(r'id="totalPages"\s*value="(\d+)"', html)
        if pm:
            total_pages = int(pm.group(1))

        rows = re.findall(r"<tr[^>]*>.*?</tr>", html, re.DOTALL | re.IGNORECASE)
        for row in rows:
            cells_html = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.DOTALL)
            if len(cells_html) < 8:
                continue
            cells = [_normalize(re.sub(r"<[^>]+>", "", c)) for c in cells_html]
            if not cells[0].isdigit():
                continue

            rec: Dict[str, Any] = {}

            # agency_code
            rec["agency_code"] = cells[1].upper()[:20] if len(cells) > 1 else ""

            # tender_id + package_no + work_name from cell 2
            cell2 = cells[2] if len(cells) > 2 else ""
            tm = re.search(r"(\d{6,})", cell2)
            if tm:
                rec["tender_id"] = tm.group(1)
            pnm = re.search(r"([A-Z]+[\w/\-]+)", cell2)
            if pnm:
                rec["package_no"] = pnm.group(1)
            if ", " in cell2:
                rec["work_name"] = cell2.split(", ", 1)[1][:300]
                rec["title"] = cell2[:500]
            else:
                rec["work_name"] = cell2[:300]
                rec["title"] = cell2[:500]

            # pe_office
            if len(cells) > 3:
                rec["pe_office"] = cells[3][:200]

            # district / location
            if len(cells) > 4:
                loc = cells[4]
                rec["location"] = loc[:100]
                d = _pick_district(loc)
                if d:
                    rec["district"] = d
                else:
                    rec["district"] = loc.split(",")[-1].strip()[:50]

            # award_date
            if len(cells) > 5:
                rec["award_date"] = cells[5][:20]

            # contractor_name
            if len(cells) > 6:
                rec["contractor_name"] = cells[6][:200]

            # amount_bdt
            if len(cells) > 7:
                try:
                    amt = float(cells[7].replace(",", "").strip())
                    rec["amount_bdt"] = amt * 100_000
                except (ValueError, IndexError):
                    rec["amount_bdt"] = 0.0

            rec.setdefault("amount_bdt", 0.0)
            rec.setdefault("procurement_method", "NOT_SPECIFIED")

            if rec.get("tender_id") or rec.get("package_no"):
                records.append(rec)
        return records, max(total_pages, 1)


# ══════════════════════════════════════════════════════════════════════
#  OUTPUT WRITER
# ══════════════════════════════════════════════════════════════════════

def _clean(records: List[Dict], fields: List[str]) -> List[Dict]:
    out = []
    for rec in records:
        cleaned = {}
        for f in fields:
            val = rec.get(f)
            if val is None:
                if f in ("estimated_cost_bdt", "amount_bdt", "contract_value_bdt", "completed_value_bdt", "progress_pct"):
                    val = 0.0
                elif f == "completed_on_time":
                    val = None
                else:
                    val = ""
            cleaned[f] = val
        out.append(cleaned)
    return out


def write_output(
    output_dir: Path,
    app: Dict[str, List],
    awards: Dict[str, List],
    experience_completed: List[Dict],
    experience_ongoing: List[Dict],
):
    app_dir = output_dir / "APP"
    award_dir = output_dir / "Award"
    exp_dir = output_dir / "Experience"
    for d in [app_dir, award_dir, exp_dir]:
        d.mkdir(parents=True, exist_ok=True)

    totals = {"app": 0, "award": 0, "experience_completed": 0, "experience_ongoing": 0}

    # Per-agency APP
    for agency, recs in app.items():
        clean = _clean(recs, APP_FIELDS)
        if not clean:
            continue
        (app_dir / f"{agency}.json").write_text(
            json.dumps(clean, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )
        totals["app"] += len(clean)

    # Per-agency Awards
    for agency, recs in awards.items():
        clean = _clean(recs, AWARD_FIELDS)
        if not clean:
            continue
        (award_dir / f"{agency}.json").write_text(
            json.dumps(clean, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )
        totals["award"] += len(clean)

    # Experience — write as per-agency if we had agency filter; since we crawl
    # all, write as single files split by completed/ongoing
    completed_clean = _clean(experience_completed, EXPERIENCE_FIELDS)
    ongoing_clean = _clean(experience_ongoing, EXPERIENCE_FIELDS)

    (exp_dir / "all_completed.json").write_text(
        json.dumps(completed_clean, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    (exp_dir / "all_ongoing.json").write_text(
        json.dumps(ongoing_clean, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    totals["experience_completed"] = len(completed_clean)
    totals["experience_ongoing"] = len(ongoing_clean)

    # Aggregate files
    all_app = []
    for recs in app.values():
        all_app.extend(_clean(recs, APP_FIELDS))
    (output_dir / "all_app.json").write_text(
        json.dumps(all_app, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    all_awards = []
    for recs in awards.values():
        all_awards.extend(_clean(recs, AWARD_FIELDS))
    (output_dir / "all_awards.json").write_text(
        json.dumps(all_awards, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    (output_dir / "all_experience_completed.json").write_text(
        json.dumps(completed_clean, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    (output_dir / "all_experience_ongoing.json").write_text(
        json.dumps(ongoing_clean, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    manifest = {
        "crawl_timestamp": datetime.now().isoformat(),
        "sources": ["APP", "Award", "eExperience"],
        "agencies_crawled": len(AGENCIES),
        "totals": totals,
        "files": {
            "app_per_agency": str(app_dir),
            "award_per_agency": str(award_dir),
            "experience_completed": str(exp_dir / "all_completed.json"),
            "experience_ongoing": str(exp_dir / "all_ongoing.json"),
            "app_aggregate": str(output_dir / "all_app.json"),
            "award_aggregate": str(output_dir / "all_awards.json"),
        },
        "schema": {
            "app": {"fields": APP_FIELDS, "join_key": "tender_id"},
            "award": {"fields": AWARD_FIELDS, "join_key": "tender_id"},
            "experience": {"fields": EXPERIENCE_FIELDS, "join_key": "tender_id"},
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return manifest


# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="eGP Complete Data Crawler — all sources public")
    parser.add_argument(
        "--sources", default="app,award,experience",
        help="Comma-separated: app,award,experience (default: all)",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output directory")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between pages (seconds)")
    parser.add_argument(
        "--experience-pages", type=int, default=0,
        help="Max pages per experience tab (0 = all available)",
    )
    parser.add_argument("--agency", default="", help="Single agency to crawl (default: all)")
    args = parser.parse_args()

    sources = [s.strip().lower() for s in args.sources.split(",")]
    output_dir = Path(args.output)
    agencies = [args.agency.upper()] if args.agency else AGENCIES

    logger.info(f"Sources: {sources} | Agencies: {len(agencies)} | Output: {output_dir}")

    client = httpx.Client(verify=False, timeout=30, follow_redirects=True)
    start = time.time()

    app_data: Dict[str, List] = {}
    award_data: Dict[str, List] = {}
    exp_completed: List[Dict] = []
    exp_ongoing: List[Dict] = []

    try:
        # Experience — global crawl (no keyword filter, gets all agencies at once)
        if "experience" in sources:
            logger.info("\n" + "=" * 60)
            logger.info("CRAWLING eExperience (eTenders + eCMS)")
            logger.info("=" * 60)
            ec = ExperienceCrawler(client, delay=args.delay)
            exp_completed, exp_ongoing = ec.crawl_all(max_pages=args.experience_pages)
            logger.info(f"  Completed: {len(exp_completed)} | Ongoing: {len(exp_ongoing)}")

        # APP — per agency with per-agency checkpoint save
        if "app" in sources:
            logger.info("\n" + "=" * 60)
            logger.info("CRAWLING APP (Annual Procurement Plans)")
            logger.info("=" * 60)
            ac = APPCrawler(client, delay=args.delay)
            app_ckpt = output_dir / "APP" / "_checkpoint.json"
            done_agencies = set()
            if app_ckpt.exists():
                done_agencies = set(json.loads(app_ckpt.read_text()).get("done", []))
                logger.info(f"  Resuming APP crawl — {len(done_agencies)} agencies already done")
            app_dir = output_dir / "APP"
            app_dir.mkdir(parents=True, exist_ok=True)
            for i, agency in enumerate(agencies):
                if agency in done_agencies:
                    logger.info(f"  [{i+1}/{len(agencies)}] {agency}... SKIP (already done)")
                    fp = app_dir / f"{agency}.json"
                    if fp.exists():
                        app_data[agency] = json.loads(fp.read_text(encoding="utf-8"))
                    continue
                logger.info(f"  [{i+1}/{len(agencies)}] {agency}...")
                records = ac.crawl_agency(agency)
                app_data[agency] = records
                app_dir.mkdir(parents=True, exist_ok=True)
                clean = _clean(records, APP_FIELDS)
                (app_dir / f"{agency}.json").write_text(
                    json.dumps(clean, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
                )
                done_agencies.add(agency)
                app_ckpt.write_text(json.dumps({"done": sorted(done_agencies)}), encoding="utf-8")
                logger.info(f"    {len(records)} records — saved checkpoint")
            total_app = sum(len(v) for v in app_data.values())
            logger.info(f"  Total APP: {total_app}")

        # Award/NOA — per agency with checkpoint
        if "award" in sources:
            logger.info("\n" + "=" * 60)
            logger.info("CRAWLING AWARDS (Notification of Award)")
            logger.info("=" * 60)
            awc = AwardCrawler(client, delay=args.delay)
            award_ckpt = output_dir / "Award" / "_checkpoint.json"
            done_awards = set()
            if award_ckpt.exists():
                done_awards = set(json.loads(award_ckpt.read_text()).get("done", []))
                logger.info(f"  Resuming Award crawl — {len(done_awards)} agencies already done")
            award_dir = output_dir / "Award"
            award_dir.mkdir(parents=True, exist_ok=True)
            for i, agency in enumerate(agencies):
                if agency in done_awards:
                    logger.info(f"  [{i+1}/{len(agencies)}] {agency}... SKIP (already done)")
                    fp = award_dir / f"{agency}.json"
                    if fp.exists():
                        award_data[agency] = json.loads(fp.read_text(encoding="utf-8"))
                    continue
                logger.info(f"  [{i+1}/{len(agencies)}] {agency}...")
                records = awc.crawl_agency(agency)
                award_data[agency] = records
                clean = _clean(records, AWARD_FIELDS)
                (award_dir / f"{agency}.json").write_text(
                    json.dumps(clean, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
                )
                done_awards.add(agency)
                award_ckpt.write_text(json.dumps({"done": sorted(done_awards)}), encoding="utf-8")
                logger.info(f"    {len(records)} records — saved checkpoint")
            total_award = sum(len(v) for v in award_data.values())
            logger.info(f"  Total Awards: {total_award}")

        # Write output
        manifest = write_output(
            output_dir, app_data, award_data, exp_completed, exp_ongoing
        )

        elapsed = time.time() - start
        logger.info("\n" + "=" * 60)
        logger.info("CRAWL COMPLETE")
        logger.info("=" * 60)
        logger.info(f"  Duration: {elapsed:.0f}s")
        for k, v in manifest["totals"].items():
            logger.info(f"  {k}: {v}")
        logger.info(f"  Output: {output_dir.resolve()}")
        logger.info(f"  Manifest: {output_dir / 'manifest.json'}")

    finally:
        client.close()


if __name__ == "__main__":
    main()
