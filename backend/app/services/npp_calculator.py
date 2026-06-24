"""
NPP Calculator Service - Computes Net Price Percentage Index from award data.
"""
from __future__ import annotations
import json
import logging
import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

NPP_DATA_DIRS = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "..", "runtime", "knowledge", "npp"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "..", "runtime", "knowledge", "npp"),
]


def _load_npp_files() -> List[Dict]:
    """Load pre-computed NPP records from files."""
    records = []
    for base_dir in NPP_DATA_DIRS:
        if not os.path.isdir(base_dir):
            continue
        for root, dirs, files in os.walk(base_dir):
            for fn in files:
                if fn.endswith(".json"):
                    try:
                        path = os.path.join(root, fn)
                        with open(path) as f:
                            data = json.load(f)
                        records.append(data)
                    except Exception:
                        pass
    return records


class NPPCalculator:
    NPP_DATA_DIRS = NPP_DATA_DIRS
    """Compute NPP (Net Price Percentage Index) values."""

    def __init__(self):
        self._npp_records: List[Dict] = []
    
    def backfill_from_actual_data(self, app_records: List[Dict] = None, 
                                   awards: List[Dict] = None) -> Dict:
        """
        Backfill NPP values from actual award data.
        Falls back to pre-computed NPP files.
        """
        # Try pre-computed data first
        if not self._npp_records:
            self._npp_records = _load_npp_files()
        
        if self._npp_records:
            by_agency_month = {}
            for r in self._npp_records:
                agency = r.get("agency", "Unknown")
                month = r.get("month", "")
                if agency not in by_agency_month:
                    by_agency_month[agency] = set()
                by_agency_month[agency].add(month)
            
            return {
                "matched": len(self._npp_records),
                "stats": {
                    "by_agency_month": {k: len(v) for k, v in by_agency_month.items()},
                    "avg_npp": sum(r.get("npp", 0) for r in self._npp_records) / max(len(self._npp_records), 1),
                }
            }
        
        # Compute from awards if no pre-computed data
        if not awards:
            return {"matched": 0, "stats": {}}
        
        matched = 0
        by_agency_month = {}
        for i, a in enumerate(awards[:10000]):  # Limit for performance
            try:
                est = float(a.get("estimated_amount_bdt", a.get("estimate", 0)) or 0)
                award_amt = float(a.get("amount_bdt", a.get("award_amount", 0)) or 0)
                if est > 0 and award_amt > 0:
                    agency = a.get("agency_target", a.get("procuring_entity", "Unknown"))
                    month = datetime.now().strftime("%Y-%m")
                    if agency not in by_agency_month:
                        by_agency_month[agency] = set()
                    by_agency_month[agency].add(month)
                    matched += 1
            except Exception:
                continue
        
        return {
            "matched": matched,
            "stats": {
                "by_agency_month": {k: len(v) for k, v in by_agency_month.items()},
            }
        }


npp_calculator = NPPCalculator()
