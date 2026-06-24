"""
Discover agencies from eGP SearchNoaServlet by scanning all ministries.
Finds agencies with ≥50 lac total contract value, excluding already-covered ones.
"""
from __future__ import annotations

import json, logging, re, sys, time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import httpx

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("discover")

BASE = "https://www.eprocure.gov.bd"
BACKEND = Path(__file__).resolve().parent.parent / "backend"
KNOWLEDGE = BACKEND / "runtime" / "knowledge"

EXCLUDED_AGENCIES = {"BWDB", "LGED", "PWD", "RHD", "BBA", "EDUCATION", "BIWTA", "BADC", "DISASTER", "POWER"}

MIN_CONTRACT_VALUE_BDT = 1_000_000  # 10 lac

_client = httpx.Client(verify=False, timeout=100, follow_redirects=True)

MINISTRY_KEYWORDS = [
    "Ministry", "Division", "Bangladesh", "Government",
]

def discover_ministries() -> List[str]:
    """Scrape SearchNOA homepage to discover ministry list."""
    try:
        resp = _client.post(
            f"{BASE}/SearchNoaServlet",
            data={"keyword": "", "pageNo": "1", "size": "1"},
        )
        if resp.status_code != 200:
            logger.warning(f"NOA search returned {resp.status_code}")
            return []
        ministries = set()
        for m in re.findall(r'<option[^>]*value="([^"]+)"[^>]*>([^<]+)</option>', resp.text):
            val, label = m
            if val and val.strip() and "select" not in val.lower():
                ministries.add(label.strip())
        if not ministries:
            ministries = discover_from_homepage()
        return sorted(ministries)
    except Exception as e:
        logger.error(f"Failed to discover ministries: {e}")
        return []

def discover_from_homepage() -> Set[str]:
    try:
        resp = _client.get(BASE)
        html = resp.text
        ministries = set()
        for m in re.findall(r'(?:Ministry|Division|Directorate|Department|Authority|Board|Corporation)\s*[^<]*', html):
            m = m.strip()[:100]
            if len(m) > 5:
                ministries.add(m)
        return ministries
    except Exception as e:
        logger.error(f"Homepage scan failed: {e}")
        return set()

MINISTRY_PRESETS = [
    "Ministry of Agriculture",
    "Ministry of Civil Aviation and Tourism",
    "Ministry of Commerce",
    "Ministry of Communications",
    "Ministry of Cultural Affairs",
    "Ministry of Defence",
    "Ministry of Disaster Management and Relief",
    "Ministry of Education",
    "Ministry of Energy and Mineral Resources",
    "Ministry of Environment and Forests",
    "Ministry of Finance",
    "Ministry of Fisheries and Livestock",
    "Ministry of Food",
    "Ministry of Foreign Affairs",
    "Ministry of Health and Family Welfare",
    "Ministry of Home Affairs",
    "Ministry of Housing and Public Works",
    "Ministry of Industries",
    "Ministry of Information",
    "Ministry of Land",
    "Ministry of Law, Justice and Parliamentary Affairs",
    "Ministry of Local Government, Rural Development and Co-operatives",
    "Ministry of Planning",
    "Ministry of Power, Energy and Mineral Resources",
    "Ministry of Public Administration",
    "Ministry of Railways",
    "Ministry of Road Transport and Bridges",
    "Ministry of Science and Technology",
    "Ministry of Shipping",
    "Ministry of Social Welfare",
    "Ministry of Textiles and Jute",
    "Ministry of Water Resources",
    "Bangladesh Atomic Energy Commission",
    "Bangladesh Bank",
    "Bangladesh Election Commission",
]

def search_ministry_agencies(ministry: str) -> List[Dict[str, Any]]:
    """Search NOA for a given ministry and aggregate by procuring entity."""
    entities: Dict[str, Dict] = {}
    page = 1
    max_pages = 100
    while page <= max_pages:
        try:
            resp = _client.post(
                f"{BASE}/SearchNoaServlet",
                data={"keyword": ministry[:100], "pageNo": str(page), "size": "50"},
                timeout=15,
            )
            if resp.status_code != 200 or len(resp.text) < 200:
                break
            if "No Records Found" in resp.text:
                break
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", resp.text, re.DOTALL)
            found_any = False
            for row_html in rows:
                cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)
                if len(cells) < 8:
                    continue
                clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
                if re.match(r"^(sl|no|serial|s\.?\s*no)", clean[0], re.I):
                    continue
                found_any = True
                entity = clean[3] if len(clean) > 3 else ""
                if not entity:
                    continue
                amount_raw = clean[7] if len(clean) > 7 else "0"
                try:
                    val = float(re.sub(r"[^\d.]", "", amount_raw)) * 10_000_000
                except ValueError:
                    val = 0.0
                if entity not in entities:
                    entities[entity] = {"entity": entity, "total_contracts": 0, "total_value_bdt": 0.0, "ministry": ministry}
                entities[entity]["total_contracts"] += 1
                entities[entity]["total_value_bdt"] += val
            if not found_any:
                break
            page += 1
        except Exception as e:
            logger.warning(f"  Error on page {page} for '{ministry[:30]}': {e}")
            break
    return [e for e in entities.values() if e["total_value_bdt"] >= MIN_CONTRACT_VALUE_BDT]

def extract_agency_code(entity_name: str) -> str:
    upper = entity_name.upper()
    known = {
        "BWDB": ["WATER DEVELOPMENT", "BWDB"],
        "LGED": ["LOCAL GOVERNMENT ENGINEERING", "LGED"],
        "PWD": ["PUBLIC WORKS", "PWD"],
        "RHD": ["ROADS AND HIGHWAYS", "RHD"],
        "BBA": ["BRIDGE AUTHORITY", "BBA"],
        "DPHE": ["PUBLIC HEALTH ENGINEERING", "DPHE"],
        "BREB": ["RURAL ELECTRIFICATION", "BREB", "REB"],
        "BADC": ["AGRICULTURAL DEVELOPMENT", "BADC"],
        "BIWTA": ["INLAND WATER", "BIWTA"],
        "EDUCATION": ["EDUCATION ENGINEERING", "EDUCATION"],
        "HED": ["HEALTH ENGINEERING", "HED", "DIRECTORATE OF HEALTH"],
        "RAILWAY": ["RAILWAY", "BANGLADESH RAILWAY"],
        "BPDB": ["POWER DEVELOPMENT BOARD", "BPDB"],
        "WASA": ["WASA", "WATER SUPPLY AND SEWERAGE"],
        "BRIDGES": ["BRIDGES DIVISION", "BRIDGE DIVISION"],
        "REB": ["REB", "RURAL ELECTRIFICATION"],
        "RAJUK": ["RAJUK", "CAPITAL DEVELOPMENT"],
        "DISASTER": ["DISASTER", "DMA"],
        "POWER": ["PGCB", "POWER GRID"],
    }
    for code, markers in known.items():
        if any(m in upper for m in markers):
            return code
    words = re.sub(r'[^A-Z\s]', '', upper).split()
    if words:
        return words[0][:10]
    return ""

def main():
    logger.info("=" * 60)
    logger.info("eGP Agency Discovery Tool")
    logger.info("=" * 60)
    out_dir = KNOWLEDGE / "discovered_agencies"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_agencies: Dict[str, Dict] = {}
    for ministry in MINISTRY_PRESETS:
        logger.info(f"\nScanning: {ministry}")
        entities = search_ministry_agencies(ministry)
        for ent in entities:
            code = extract_agency_code(ent["entity"])
            if code in EXCLUDED_AGENCIES:
                continue
            if code not in all_agencies or ent["total_value_bdt"] > all_agencies[code]["total_value_bdt"]:
                all_agencies[code] = {**ent, "agency_code": code}

    logger.info(f"\n{'='*60}")
    logger.info(f"Discovered {len(all_agencies)} candidate agencies (≥50 lac)")
    logger.info(f"{'='*60}")

    results = sorted(all_agencies.values(), key=lambda x: x["total_value_bdt"], reverse=True)
    for r in results:
        cv_cr = r["total_value_bdt"] / 10_000_000
        logger.info(f"  {r['agency_code']:12s} | {cv_cr:>8.2f} Cr | {r['total_contracts']:5d} contracts | {r['entity'][:50]}")

    fp = out_dir / "discovered_agencies.json"
    fp.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"\nSaved {len(results)} agencies to {fp}")

    code_list = [r["agency_code"] for r in results]
    logger.info(f"\nAgency codes for crawl_econtracts:\n{json.dumps(code_list, indent=2)}")

if __name__ == "__main__":
    main()
