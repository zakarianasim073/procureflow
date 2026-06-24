"""
Rate Tracker Service - Extracts and tracks market rates from awards and SOR data.
"""
from __future__ import annotations
import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from sqlalchemy import text

logger = logging.getLogger(__name__)


class RateTracker:
    """Track market rates from award data and SOR records."""

    def __init__(self):
        self._rates_cache: Dict = {}
    
    def save_rates(self, awards: List[Dict]) -> Dict:
        """
        Extract rate information from awards.
        Returns stats about extracted rate entries.
        """
        if not awards:
            return {"total_entries": 0, "by_agency_work_type": {}}
        
        by_agency = {}
        total = 0
        
        for a in awards:
            agency = a.get("agency_target", a.get("procuring_entity", "Unknown"))
            amt = float(a.get("amount_bdt", a.get("award_amount", 0)) or 0)
            work_type = a.get("work_type", a.get("procurement_type", "Civil Works"))
            
            if agency not in by_agency:
                by_agency[agency] = {}
            if work_type not in by_agency[agency]:
                by_agency[agency][work_type] = {"count": 0, "total_amount": 0.0, "min": float('inf'), "max": 0}
            
            by_agency[agency][work_type]["count"] += 1
            by_agency[agency][work_type]["total_amount"] += amt
            by_agency[agency][work_type]["min"] = min(by_agency[agency][work_type]["min"], amt)
            by_agency[agency][work_type]["max"] = max(by_agency[agency][work_type]["max"], amt)
            total += 1
        
        # Compute averages
        for ag in by_agency:
            for wt in by_agency[ag]:
                c = by_agency[ag][wt]["count"]
                by_agency[ag][wt]["avg_amount"] = round(by_agency[ag][wt]["total_amount"] / c, 2) if c else 0
        
        return {
            "total_entries": total,
            "by_agency_work_type": by_agency,
        }


rate_tracker = RateTracker()
