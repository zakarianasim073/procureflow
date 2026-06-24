"""
Procurement Flow Specialist BD — Price Escalation Calculator (GCC 70.1)
Implements BPPA price adjustment formula for contracts > 12 months.
Tracks material price indices and auto-calculates escalation amounts.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Bangladesh Market Price Indices (Base: Jan 2025 = 100) ──────────────
# Source: Bangladesh Bureau of Statistics (BBS), REHAB, local market survey

MARKET_INDICES = {
    "cement": {"base_index": 100.0, "current_index": 115.2, "trend": "up", "last_updated": "2026-05-01"},
    "ms_rod_60": {"base_index": 100.0, "current_index": 118.5, "trend": "up", "last_updated": "2026-05-01"},
    "ms_rod_40": {"base_index": 100.0, "current_index": 116.3, "trend": "up", "last_updated": "2026-05-01"},
    "brick_1st": {"base_index": 100.0, "current_index": 108.0, "trend": "stable", "last_updated": "2026-05-01"},
    "stone_chips": {"base_index": 100.0, "current_index": 112.5, "trend": "up", "last_updated": "2026-05-01"},
    "sand_coarse": {"base_index": 100.0, "current_index": 105.8, "trend": "stable", "last_updated": "2026-05-01"},
    "sand_fine": {"base_index": 100.0, "current_index": 103.2, "trend": "down", "last_updated": "2026-05-01"},
    "bitumen_80_100": {"base_index": 100.0, "current_index": 122.0, "trend": "up", "last_updated": "2026-05-01"},
    "paint_weather": {"base_index": 100.0, "current_index": 107.5, "trend": "stable", "last_updated": "2026-05-01"},
    "labor_skilled": {"base_index": 100.0, "current_index": 112.0, "trend": "up", "last_updated": "2026-04-01"},
    "labor_unskilled": {"base_index": 100.0, "current_index": 110.5, "trend": "up", "last_updated": "2026-04-01"},
    "equipment_excavator": {"base_index": 100.0, "current_index": 108.5, "trend": "stable", "last_updated": "2026-05-01"},
    "equipment_crane": {"base_index": 100.0, "current_index": 106.0, "trend": "stable", "last_updated": "2026-05-01"},
    "fuel_diesel": {"base_index": 100.0, "current_index": 125.0, "trend": "up", "last_updated": "2026-05-15"},
    "transport": {"base_index": 100.0, "current_index": 114.0, "trend": "up", "last_updated": "2026-05-01"},
}

# ── Standard Cost Breakdown (by work type) ───────────────────────────────
# [material%, labor%, equipment%, overhead%, profit%]

COST_BREAKDOWN = {
    "building": {"material": 50, "labor": 25, "equipment": 10, "overhead": 8, "profit": 7},
    "road": {"material": 40, "labor": 20, "equipment": 25, "overhead": 8, "profit": 7},
    "bridge": {"material": 35, "labor": 25, "equipment": 25, "overhead": 8, "profit": 7},
    "water": {"material": 45, "labor": 20, "equipment": 20, "overhead": 8, "profit": 7},
    "electrical": {"material": 55, "labor": 15, "equipment": 15, "overhead": 8, "profit": 7},
    "general": {"material": 45, "labor": 22, "equipment": 18, "overhead": 8, "profit": 7},
}


class PriceEscalationCalculator:
    """
    GCC 70.1 — Price Adjustment (Escalation) Calculator
    
    For contracts with completion period > 12 months.
    Uses weighted formula with BBS market indices.
    """
    
    def __init__(self):
        self.indices_file = Path("./runtime/market_indices.json")
        self._load_indices()

    def _load_indices(self):
        """Load market indices (with local override support)."""
        if self.indices_file.exists():
            try:
                with open(self.indices_file) as f:
                    override = json.load(f)
                    MARKET_INDICES.update(override)
            except Exception as e:
                logger.warning(f"Failed to load market indices override: {e}")

    def get_current_indices(self) -> Dict[str, Any]:
        """Get current market price indices."""
        return {
            "base_date": "January 2025",
            "base_value": 100,
            "indices": MARKET_INDICES,
            "last_updated": max(
                v["last_updated"] for v in MARKET_INDICES.values()
            ),
            "source": "BBS / REHAB / Local Market Survey",
        }

    def calculate_escalation(
        self,
        base_contract_value: float,
        contract_start: str,
        current_date: str,
        work_type: str = "general",
        material_index_change: Optional[float] = None,
        labor_index_change: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        GCC 70.1 Price Adjustment Formula:
        
        PA = P0 × (a + b×Im/I0 + c×Lm/L0 + d×Em/E0 - 1)
        
        Where:
        - P0 = Base contract value
        - a = Fixed portion (0.15)
        - b = Material weight
        - c = Labor weight
        - d = Equipment weight
        - Im/I0 = Material index ratio
        - Lm/L0 = Labor index ratio
        - Em/E0 = Equipment index ratio
        """
        from datetime import datetime
        
        breakdown = COST_BREAKDOWN.get(work_type, COST_BREAKDOWN["general"])
        fixed_portion = 0.15  # Non-adjustable
        
        material_weight = breakdown["material"] / 100.0
        labor_weight = breakdown["labor"] / 100.0
        equipment_weight = breakdown["equipment"] / 100.0
        
        # Index ratios (using default market indices or custom values)
        if material_index_change is not None:
            material_ratio = 1 + material_index_change / 100.0
        else:
            material_ratio = (
                MARKET_INDICES.get("cement", {}).get("current_index", 115) / 
                MARKET_INDICES.get("cement", {}).get("base_index", 100)
            )
            
        if labor_index_change is not None:
            labor_ratio = 1 + labor_index_change / 100.0
        else:
            labor_ratio = (
                MARKET_INDICES.get("labor_skilled", {}).get("current_index", 112) / 
                MARKET_INDICES.get("labor_skilled", {}).get("base_index", 100)
            )
        
        equipment_ratio = (
            MARKET_INDICES.get("equipment_excavator", {}).get("current_index", 108.5) / 
            MARKET_INDICES.get("equipment_excavator", {}).get("base_index", 100)
        )
        
        # Calculate adjustment factor
        adjustment_factor = (
            fixed_portion +
            material_weight * material_ratio +
            labor_weight * labor_ratio +
            equipment_weight * equipment_ratio
        )
        
        # Calculate months elapsed
        try:
            start = datetime.strptime(contract_start[:10], "%Y-%m-%d")
            current = datetime.strptime(current_date[:10], "%Y-%m-%d")
            months_elapsed = max((current.year - start.year) * 12 + (current.month - start.month), 0)
        except Exception:
            months_elapsed = 0

        # Only apply if > 12 months
        eligible = months_elapsed > 12
        
        if not eligible:
            adjustment_factor = 1.0
        
        adjusted_value = round(base_contract_value * adjustment_factor, 2)
        escalation_amount = round(adjusted_value - base_contract_value, 2) if eligible else 0
        escalation_pct = round((adjustment_factor - 1) * 100, 2) if eligible else 0
        
        return {
            "contract_value": round(base_contract_value, 2),
            "adjusted_value": adjusted_value,
            "escalation_amount": escalation_amount,
            "escalation_pct": escalation_pct,
            "eligible_for_escalation": eligible,
            "months_elapsed": months_elapsed,
            "formula_applied": "GCC 70.1" if eligible else "Not applicable (< 12 months)",
            "breakdown": {
                "fixed_portion_pct": round(fixed_portion * 100, 1),
                "material_weight_pct": round(material_weight * 100, 1),
                "material_index_ratio": round(material_ratio, 4),
                "labor_weight_pct": round(labor_weight * 100, 1),
                "labor_index_ratio": round(labor_ratio, 4),
                "equipment_weight_pct": round(equipment_weight * 100, 1),
                "equipment_index_ratio": round(equipment_ratio, 4),
                "adjustment_factor": round(adjustment_factor, 4),
            },
            "work_type": work_type,
            "contract_start": contract_start,
            "evaluation_date": current_date,
            "recommendation": (
                f"Claim BDT {escalation_amount:,.2f} as price escalation under GCC 70.1" 
                if escalation_amount > 0 else 
                "No escalation claim applicable at this time"
            ),
        }

    def estimate_future_escalation(
        self,
        base_contract_value: float,
        contract_start: str,
        contract_end: str,
        work_type: str = "general",
        annual_escalation_rate: float = 8.0,
    ) -> Dict[str, Any]:
        """
        Estimate total price escalation over the full contract period.
        Uses projected annual escalation rate.
        """
        from datetime import datetime
        
        try:
            start = datetime.strptime(contract_start[:10], "%Y-%m-%d")
            end = datetime.strptime(contract_end[:10], "%Y-%m-%d")
            total_months = max((end.year - start.year) * 12 + (end.month - start.month), 0)
        except Exception:
            total_months = 0
        
        # Monthly escalation rate (compounded)
        monthly_rate = annual_escalation_rate / 12 / 100.0
        
        # Project escalation for each month after 12th month
        total_escalation = 0.0
        monthly_projections = []
        
        for month in range(13, total_months + 1):
            escalation_month = month - 12
            cumulative_factor = (1 + monthly_rate) ** escalation_month
            month_escalation = base_contract_value * (cumulative_factor - 1) / total_months if total_months > 0 else 0
            total_escalation += month_escalation
            
            projection_date = f"Month {month}"
            monthly_projections.append({
                "month": month,
                "escalation_month": escalation_month,
                "cumulative_factor": round(cumulative_factor, 4),
                "monthly_escalation": round(month_escalation, 2),
            })
        
        final_value = round(base_contract_value + total_escalation, 2)
        escalation_pct = round((total_escalation / max(base_contract_value, 1)) * 100, 2)
        
        return {
            "base_value": round(base_contract_value, 2),
            "projected_final_value": final_value,
            "projected_total_escalation": round(total_escalation, 2),
            "projected_escalation_pct": escalation_pct,
            "total_contract_months": total_months,
            "escalation_months": max(total_months - 12, 0),
            "annual_escalation_rate_pct": annual_escalation_rate,
            "monthly_projections": monthly_projections[:24],  # First 24 months of escalation
            "recommendation": (
                f"Budget BDT {total_escalation:,.2f} for price escalation over {max(total_months-12, 0)} months" 
                if total_escalation > 0 else 
                "Short-term contract — no escalation needed"
            ),
        }


# Singleton
price_escalation = PriceEscalationCalculator()
