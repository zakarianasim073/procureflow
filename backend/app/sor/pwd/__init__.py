"""PWD Schedule of Rates (SOR) — 4 zones: Dhaka/Mymensingh, Chattogram/Sylhet, Khulna/Barisal, Rajshahi/Rangpur."""
from __future__ import annotations
import json, os, logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
_rates_path = os.path.join(os.path.dirname(__file__), "rates.json")
SOR_RATES: List[Dict] = []
if os.path.exists(_rates_path):
    with open(_rates_path, encoding="utf-8") as f:
        SOR_RATES = json.load(f)
    logger.info(f"Loaded {len(SOR_RATES)} PWD SOR rates")

def get_rate(code: str, zone: str = "A") -> Optional[float]:
    zone = zone.upper()
    if zone not in ("A","B","C","D"): return None
    field = f"zone_{zone.lower()}"
    for r in SOR_RATES:
        if r["code"] == code:
            return r.get(field)
    return None

def search(query: str, max_results: int = 10) -> List[Dict]:
    query = query.lower()
    results = []
    for r in SOR_RATES:
        if query in r["code"].lower() or query in r.get("description","").lower():
            results.append(r)
            if len(results) >= max_results: break
    return results
