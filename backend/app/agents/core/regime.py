"""
PPR Regime Split — Central utility for PPR2008 vs PPR2025 era handling.

PPR-2008 Regime (Before 28 Sep 2025):
  - ±10% cap around official estimate
  - Simpler evaluation rules
  
PPR-2025 Regime (On/after 28 Sep 2025):
  - NPPI + SLT weighted formula
  - No ±10% cap
  - CPTU-compliant evaluation
  - SLT threshold at 70% of estimate
  - ALT threshold at 60% of estimate

Usage:
  from app.agents.core.regime import get_regime, filter_by_regime
  regime = get_regime(tender_date)
  filtered = filter_by_regime(query, "PPR2025")
"""
from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# ── Regime Constants ────────────────────────────────────────────────────

PPR_REGIME_CUTOFF = datetime(2025, 9, 28)
PPR_REGIME_CUTOFF_DATE = date(2025, 9, 28)

REGIME_PPR2008 = "PPR2008"
REGIME_PPR2025 = "PPR2025"


# ── Core Functions ──────────────────────────────────────────────────────

def get_regime(tender_date: Optional[Union[str, datetime, date]]) -> str:
    """
    Determine which procurement regime applies to a tender.
    
    Args:
        tender_date: The tender's opening/publication date
        
    Returns:
        "PPR2008" for before 28 Sep 2025
        "PPR2025" for on/after 28 Sep 2025
        "PPR2008" as default if no date
    """
    if tender_date is None:
        return REGIME_PPR2008
    
    if isinstance(tender_date, str):
        try:
            # Try ISO format first
            tender_date = datetime.fromisoformat(tender_date.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            try:
                # Try common formats
                from dateutil import parser as dateparser
                tender_date = dateparser.parse(tender_date)
            except (ImportError, ValueError):
                logger.warning(f"Cannot parse tender_date: {tender_date}, defaulting to PPR2008")
                return REGIME_PPR2008
    
    if isinstance(tender_date, datetime):
        tender_date = tender_date.date()
    
    if tender_date >= PPR_REGIME_CUTOFF_DATE:
        return REGIME_PPR2025
    
    return REGIME_PPR2008


def get_regime_label(regime: str) -> str:
    """Get human-readable label for a regime."""
    labels = {
        REGIME_PPR2008: "PPR-2008 (±10% Cap Regime)",
        REGIME_PPR2025: "PPR-2025 (NPPI + SLT Regime)",
    }
    return labels.get(regime, f"Unknown Regime ({regime})")


def regime_weight(regime: str, data_type: str = "pricing") -> float:
    """
    Get weight multiplier for different data types by regime.
    
    When computing pricing bands, PPR2025 data should be weighted more
    because it reflects current evaluation rules.
    For relationship/experience data, both regimes are equally valuable.
    
    Args:
        regime: "PPR2008" or "PPR2025"
        data_type: "pricing", "relationship", "experience", "competition"
        
    Returns:
        Weight multiplier (0.0 to 1.0)
    """
    weights = {
        REGIME_PPR2008: {
            "pricing": 0.3,       # Pre-2025 pricing less relevant
            "relationship": 1.0,   # Relationships fully relevant
            "experience": 1.0,     # Experience fully relevant
            "competition": 0.7,    # Competition patterns somewhat relevant
        },
        REGIME_PPR2025: {
            "pricing": 1.0,       # Current pricing most relevant
            "relationship": 1.0,   # Relationships always relevant
            "experience": 1.0,     # Experience always relevant
            "competition": 1.0,    # Competition fully relevant
        },
    }
    return weights.get(regime, weights[REGIME_PPR2008]).get(data_type, 0.5)


def get_relevant_discounts(discounts: List[Dict], data_type: str = "pricing") -> List[Dict]:
    """
    Filter and weight a list of discount records by regime.
    
    Args:
        discounts: List of dicts with 'discount_pct' and 'regime' and 'tender_date'
        data_type: What these discounts are used for
        
    Returns:
        Filtered list with weight multiplier added to each item
    """
    weighted = []
    for d in discounts:
        regime = d.get("regime", get_regime(d.get("tender_date")))
        w = regime_weight(regime, data_type)
        if w > 0:
            d["_regime_weight"] = w
            d["_regime"] = regime
            weighted.append(d)
    return weighted


def compute_weighted_percentile(values: List[float], weights: List[float], percentile: float = 0.5) -> float:
    """Compute weighted percentile for regime-aware discount analysis."""
    if not values or not weights:
        return 0.0
    if len(values) != len(weights):
        return sorted(values)[int(len(values) * percentile)]
    
    # Sort by value, keep weight alignment
    pairs = sorted(zip(values, weights), key=lambda x: x[0])
    total_weight = sum(weights)
    if total_weight == 0:
        return pairs[len(pairs) // 2][0] if pairs else 0.0
    
    cumulative = 0.0
    target = total_weight * percentile
    for value, weight in pairs:
        cumulative += weight
        if cumulative >= target:
            return value
    
    return pairs[-1][0] if pairs else 0.0


def regime_sql_filter(regime: Optional[str] = None, table_alias: str = "t") -> str:
    """
    Generate SQL WHERE clause for regime filtering.
    
    Args:
        regime: "PPR2008", "PPR2025", or None for no filter
        table_alias: SQL table alias (default "t" for tenders)
        
    Returns:
        SQL condition string or empty string
    """
    if regime is None:
        return ""
    if regime == REGIME_PPR2025:
        return f"AND {table_alias}.opening_date >= '2025-09-28'"
    return f"AND ({table_alias}.opening_date IS NULL OR {table_alias}.opening_date < '2025-09-28')"


def get_nppi_slt_defaults() -> Dict:
    """
    Get default NPPI and SLT values when no PPR2025 data exists.
    These are conservative estimates based on Bangladesh procurement patterns.
    """
    return {
        "nppi": 5.5,           # Default NPPI: 5.5% below estimate
        "slt_threshold": 8.0,  # Default SLT: 8% below estimate
        "slt_risk_below": 10.0, # Risk zone begins at 10%
        "confidence": "low",
        "note": "Default values used — limited PPR-2025 data available. Update as awards accumulate.",
    }


# ── Tender Metadata Injection ──────────────────────────────────────────

def enrich_tender_with_regime(tender: Dict) -> Dict:
    """Add regime info to a tender dict."""
    if not tender:
        return tender
    
    opening_date = tender.get("opening_date") or tender.get("tender_opening_date") or tender.get("submission_date")
    regime = get_regime(opening_date)
    
    tender["_regime"] = regime
    tender["_regime_label"] = get_regime_label(regime)
    
    return tender


def batch_enrich_with_regime(tenders: List[Dict]) -> List[Dict]:
    """Add regime info to a list of tender dicts."""
    return [enrich_tender_with_regime(t) for t in tenders]


__all__ = [
    "get_regime", "get_regime_label", "regime_weight",
    "get_relevant_discounts", "compute_weighted_percentile",
    "regime_sql_filter", "get_nppi_slt_defaults",
    "enrich_tender_with_regime", "batch_enrich_with_regime",
    "REGIME_PPR2008", "REGIME_PPR2025", "PPR_REGIME_CUTOFF",
]
