"""
BWDB Schedule of Rates (SOR)
Zone-based unit rates — 4 zones (A, B, C, D) for geographical regions.
Source: Work Plan.xlsx 'rates' sheet (963 rate items)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_rates_path = os.path.join(os.path.dirname(__file__), "rates.json")
SOR_RATES: List[Dict[str, Any]] = []
if os.path.exists(_rates_path):
    with open(_rates_path, encoding="utf-8") as f:
        SOR_RATES = json.load(f)
    logger.info(f"Loaded {len(SOR_RATES)} BWDB SOR rates (4 zones)")


VALID_ZONES = {"A", "B", "C", "D"}
ZONE_FIELDS = {"A": "zone_a", "B": "zone_b", "C": "zone_c", "D": "zone_d"}


def normalize_code(code: str) -> str:
    """Normalize item code for matching. Pads single-dash codes."""
    code = code.strip().replace(" ", "")
    if code.count("-") == 1 and not code.endswith("-"):
        parts = code.split("-")
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            return f"{code}-00"
    return code


def get_rate(code: str, zone: str = "A") -> Optional[float]:
    """
    Look up SOR unit rate by item code and zone (A/B/C/D).
    
    Args:
        code: SOR item code (e.g. "40-170-40", "04-180")
        zone: "A", "B", "C", or "D"
    
    Returns:
        Unit rate in BDT, or None if not found
    """
    zone = zone.upper()
    if zone not in VALID_ZONES:
        raise ValueError(f"Invalid zone: {zone}. Must be A, B, C, or D")

    field = ZONE_FIELDS[zone]
    normalized = normalize_code(code)

    # Exact match
    for r in SOR_RATES:
        if r["code"] == normalized:
            return r.get(field) or r.get("zone_b")

    # Partial match
    for r in SOR_RATES:
        if r["code"].startswith(normalized) or normalized.startswith(r["code"]):
            return r.get(field) or r.get("zone_b")

    return None


def get_rate_info(code: str, zone: str = "A") -> Optional[Dict[str, Any]]:
    """Get full SOR info with rate for the given zone."""
    zone = zone.upper()
    if zone not in VALID_ZONES:
        return None
    field = ZONE_FIELDS[zone]
    normalized = normalize_code(code)
    
    for r in SOR_RATES:
        if r["code"] == normalized:
            rate = r.get(field) or r.get("zone_b")
            return {"code": r["code"], "description": r["description"],
                    "unit": r["unit"], "rate": rate, "zone": zone}
    
    for r in SOR_RATES:
        if r["code"].startswith(normalized) or normalized.startswith(r["code"]):
            rate = r.get(field) or r.get("zone_b")
            return {"code": r["code"], "description": r["description"],
                    "unit": r["unit"], "rate": rate, "zone": zone}
    return None


def get_all_rates(code: str) -> Optional[Dict[str, float]]:
    """Get rates for all 4 zones for a given item code."""
    result = {}
    for zone in ["A", "B", "C", "D"]:
        rate = get_rate(code, zone)
        if rate is not None:
            result[zone] = rate
    return result if result else None


def search(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """Search SOR items by code or description."""
    query = query.lower()
    results = []
    for r in SOR_RATES:
        desc = r.get("description", "").lower()
        if query in r["code"].lower() or query in desc:
            results.append(r)
            if len(results) >= max_results:
                break
    return results
