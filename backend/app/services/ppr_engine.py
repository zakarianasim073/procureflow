"""
Procurement Flow Specialist BD — PPR 2025 Math Engine
Implements exact BPPA e-PW3 (Oct 2025) formulas for TEC Evaluation.
ITT 14.1(d) Tender Capacity Formula, ITT 52.2 SLT Detection, GCC 70.1 Price Adjustment.
"""

from __future__ import annotations

import math
import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ── PPR 2025 Constants ──────────────────────────────────────────────────

PPR_2025 = {
    "SLT_THRESHOLD": 0.70,        # ITT 52.2(a): Seriously Low Tender = 70% of estimate
    "ALT_THRESHOLD": 0.60,        # ITT 52.2(b): Abnormally Low Tender = 60%
    "MAX_ARITHMETIC_ERROR": 0.20, # ITT 27: Max 20% correction before rejection
    "BID_SECURITY_PCT": 0.02,     # ITT 19.1: 2% of estimate (max 50L)
    "PERFORMANCE_SECURITY_PCT": 0.05, # GCC 66.1: 5% of contract value
    "ADVANCE_PAYMENT_MAX_PCT": 0.20,  # GCC 72.1: Max 20% advance
    "RETENTION_PCT": 0.05,        # GCC 68.1: 5% retention
    "RETENTION_LIMIT": 0.10,      # GCC 68.2: Max 10% cumulative
    "SUBCONTRACT_MAX_PCT": 0.30,  # ITT 7.1: Max 30% subcontracting
    "JV_MAX_PARTNERS": 3,         # ITT 6.1: Max 3 JV partners
}


@dataclass
class TECResult:
    """Tender Evaluation Criteria Result — BPPA e-PW3 compliant."""
    responsive: bool = True
    total_score: float = 0.0
    technical_score: float = 0.0
    financial_score: float = 0.0
    capacity_adequate: bool = True
    slt_status: str = "NONE"  # NONE, SLT, ALT
    arithmetic_errors: List[Dict] = field(default_factory=list)
    evaluation_notes: List[str] = field(default_factory=list)


def calculate_tender_capacity(
    annual_turnover: float,
    current_commitments: float,
    tender_estimated_value: float,
    years_in_business: int = 5,
) -> Dict[str, Any]:
    """
    ITT 14.1(d) — Tender Capacity Formula
    
    Tender Capacity (TC) = max(Annual Turnover × 2 - Current Commitments, 0)
    
    A tenderer is eligible if:
    TC ≥ Tender Estimated Value
    AND
    Annual Turnover ≥ 50% of Tender Estimated Value (for works)
    """
    max_capacity = annual_turnover * 2.0  # ITT 14.1(d): 2x turnover
    available_capacity = max(max_capacity - current_commitments, 0.0)
    capacity_ratio = available_capacity / max(tender_estimated_value, 1)
    turnover_ratio = annual_turnover / max(tender_estimated_value, 1)
    
    # Experience factor (e-PW3-6 requirement)
    min_experience_years = 5 if tender_estimated_value > 100_000_000 else 3
    experience_adequate = years_in_business >= min_experience_years
    
    # Determine capacity status
    if available_capacity >= tender_estimated_value and turnover_ratio >= 0.5:
        capacity_status = "ADEQUATE"
        capacity_score = 100
    elif available_capacity >= tender_estimated_value * 0.7:
        capacity_status = "MARGINAL"
        capacity_score = 60
    else:
        capacity_status = "INADEQUATE"
        capacity_score = 20
    
    return {
        "capacity_status": capacity_status,
        "capacity_score": capacity_score,
        "max_capacity": round(max_capacity, 2),
        "current_commitments": round(current_commitments, 2),
        "available_capacity": round(available_capacity, 2),
        "tender_value": round(tender_estimated_value, 2),
        "capacity_ratio": round(capacity_ratio, 2),
        "turnover_ratio": round(turnover_ratio, 2),
        "annual_turnover": round(annual_turnover, 2),
        "years_in_business": years_in_business,
        "min_experience_years": min_experience_years,
        "experience_adequate": experience_adequate,
        "formula": "TC = max(Annual Turnover × 2 - Current Commitments, 0)",
        "eligibility": "PASS" if (capacity_status == "ADEQUATE" and experience_adequate) else "FAIL",
    }


def detect_slt_alt(
    quoted_amount: float,
    estimated_value: float,
    num_bidders: int = 5,
    market_avg_discount: float = 5.0,
) -> Dict[str, Any]:
    """
    ITT 52.2 — Seriously Low Tender (SLT) / Abnormally Low Tender (ALT) Detection
    
    SLT threshold: 70% of estimated value (ITT 52.2(a))
    ALT threshold: 60% of estimated value (ITT 52.2(b))
    
    Also applies weighted standard deviation method when market data available.
    """
    bid_ratio = quoted_amount / max(estimated_value, 1)
    discount_pct = (1 - bid_ratio) * 100
    threshold_breach = ""
    
    if bid_ratio < PPR_2025["ALT_THRESHOLD"]:
        slt_status = "ALT"  # Abnormally Low Tender
        threshold_breach = f"Bid ({discount_pct:.1f}% discount) exceeds ALT threshold of {(1-PPR_2025['ALT_THRESHOLD'])*100:.0f}%"
    elif bid_ratio < PPR_2025["SLT_THRESHOLD"]:
        slt_status = "SLT"  # Seriously Low Tender
        threshold_breach = f"Bid ({discount_pct:.1f}% discount) exceeds SLT threshold of {(1-PPR_2025['SLT_THRESHOLD'])*100:.0f}%"
    else:
        slt_status = "NONE"
    
    # Weighted standard deviation method (advanced)
    discount_deviation = abs(discount_pct - market_avg_discount)
    std_dev_threshold = 8.0  # Standard deviation threshold
    
    if discount_deviation > std_dev_threshold * 1.5:
        weighted_slt = "HIGH_PROBABILITY"
    elif discount_deviation > std_dev_threshold:
        weighted_slt = "MODERATE_PROBABILITY"
    else:
        weighted_slt = "LOW_PROBABILITY"
    
    return {
        "slt_status": slt_status,
        "weighted_slt": weighted_slt,
        "bid_ratio": round(bid_ratio, 4),
        "discount_pct": round(discount_pct, 2),
        "estimated_value": round(estimated_value, 2),
        "quoted_amount": round(quoted_amount, 2),
        "threshold_breach": threshold_breach,
        "recommendation": (
            "Request detailed price breakdown per ITT 52.3" if slt_status in ("SLT", "ALT")
            else "No further action required"
        ),
        "formula": "SLT < 70% of Estimate | ALT < 60% of Estimate | Weighted Std Dev method",
    }


def check_arithmetic_errors(
    boq_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    ITT 27 — Arithmetic Error Correction
    
    Rule: If total error exceeds 20%, the tender is rejected.
    Individual errors: rate × quantity ≠ line total
    """
    errors = []
    total_correction = 0.0
    total_original = 0.0
    error_count = 0
    
    for item in boq_items:
        qty = float(item.get("qty", item.get("quantity", 0)))
        rate = float(item.get("rate", 0))
        line_total = float(item.get("amount", item.get("total", qty * rate)))
        
        calculated = qty * rate
        variance = abs(line_total - calculated)
        
        if variance > 1.0:  # More than 1 BDT tolerance
            errors.append({
                "item_no": item.get("item_no", ""),
                "description": item.get("description", item.get("desc", "")),
                "unit": item.get("unit", ""),
                "qty": qty,
                "rate": rate,
                "stated_total": round(line_total, 2),
                "calculated_total": round(calculated, 2),
                "error": round(line_total - calculated, 2),
                "error_pct": round((variance / max(calculated, 1)) * 100, 2) if calculated > 0 else 0,
            })
            total_correction += abs(line_total - calculated)
            error_count += 1
        
        total_original += line_total
    
    correction_pct = (total_correction / max(total_original, 1)) * 100
    is_rejectable = correction_pct > PPR_2025["MAX_ARITHMETIC_ERROR"] * 100
    
    return {
        "has_errors": error_count > 0,
        "error_count": error_count,
        "total_items": len(boq_items),
        "total_original": round(total_original, 2),
        "total_correction": round(total_correction, 2),
        "correction_pct": round(correction_pct, 2),
        "is_rejectable": is_rejectable,
        "max_allowed_pct": PPR_2025["MAX_ARITHMETIC_ERROR"] * 100,
        "errors": errors[:10],  # First 10 errors for readability
        "verdict": "REJECTED" if is_rejectable else "ACCEPTED with corrections",
        "formula": "ITT 27: Max 20% aggregate arithmetic error before rejection",
    }


def calculate_price_adjustment(
    base_price: float,
    contract_month: int,
    base_index: float = 100.0,
    current_index: float = 110.0,
    labor_weight: float = 0.30,
    material_weight: float = 0.50,
    equipment_weight: float = 0.20,
) -> Dict[str, Any]:
    """
    GCC 70.1 — Price Adjustment Formula (for contracts > 12 months)
    
    PA = P0 × (a + b × (Im/I0) + c × (Lm/L0) + d × (Em/E0))
    where a = fixed portion (0.15-0.20), b+c+d = non-fixed portion (0.80-0.85)
    """
    fixed_portion = 0.15  # Non-adjustable portion
    
    # Weighted indices
    material_factor = current_index / max(base_index, 1)
    labor_factor = 1.02  # Assume 2% labor escalation per year
    equipment_factor = 1.015  # Assume 1.5% equipment escalation
    
    adjustment_factor = (
        fixed_portion +
        material_weight * material_factor +
        labor_weight * labor_factor +
        equipment_weight * equipment_factor
    )
    
    adjusted_price = round(base_price * adjustment_factor, 2)
    adjustment_amount = round(adjusted_price - base_price, 2)
    adjustment_pct = round((adjustment_factor - 1) * 100, 2)
    
    return {
        "base_price": round(base_price, 2),
        "adjusted_price": adjusted_price,
        "adjustment_amount": adjustment_amount,
        "adjustment_pct": adjustment_pct,
        "contract_month": contract_month,
        "factors": {
            "fixed_portion": fixed_portion,
            "material_weight": material_weight,
            "material_index_change": round((material_factor - 1) * 100, 2),
            "labor_weight": labor_weight,
            "equipment_weight": equipment_weight,
        },
        "formula": "PA = P0 × (0.15 + 0.50×Im/I0 + 0.30×1.02 + 0.20×1.015)",
        "eligible_for_adjustment": contract_month > 12,
    }


def evaluate_bid_security(
    estimated_value: float,
    submitted_security: float,
) -> Dict[str, Any]:
    """
    ITT 19.1 — Bid Security (EMD) Check
    
    Required: 2% of estimated value, max BDT 50,00,000
    Validity: 28 days beyond bid validity
    """
    required_amount = min(estimated_value * PPR_2025["BID_SECURITY_PCT"], 5_000_000)
    shortfall = max(required_amount - submitted_security, 0)
    
    return {
        "required_amount": round(required_amount, 2),
        "submitted_amount": round(submitted_security, 2),
        "shortfall": round(shortfall, 2),
        "adequate": submitted_security >= required_amount,
        "pct_of_estimate": round((submitted_security / max(estimated_value, 1)) * 100, 2),
        "formula": "EMD = min(2% of Est. Value, BDT 50,00,000)",
    }


def calculate_performance_security(
    contract_value: float,
) -> Dict[str, Any]:
    """
    GCC 66.1 — Performance Security
    
    Required: 5% of contract value
    Valid until: 60 days after defects liability period
    """
    amount = contract_value * PPR_2025["PERFORMANCE_SECURITY_PCT"]
    
    return {
        "amount": round(amount, 2),
        "pct": PPR_2025["PERFORMANCE_SECURITY_PCT"] * 100,
        "formula": "PS = 5% of Contract Value (GCC 66.1)",
        "validity": "60 days after defects liability period",
    }


def calculate_advance_payment(
    contract_value: float,
    mobilization_required: float,
) -> Dict[str, Any]:
    """
    GCC 72.1 — Advance Payment
    
    Max: 20% of contract value
    Repayment: Amortized over first 50% of works
    """
    max_advance = contract_value * PPR_2025["ADVANCE_PAYMENT_MAX_PCT"]
    recommended = min(mobilization_required, max_advance)
    
    return {
        "max_advance": round(max_advance, 2),
        "recommended": round(recommended, 2),
        "mobilization_required": round(mobilization_required, 2),
        "pct_of_contract": round((recommended / max(contract_value, 1)) * 100, 2),
        "formula": "AP = max(20% of Contract Value, Mobilization Need) per GCC 72.1",
        "repayment": "Amortized over first 50% of work completed",
    }


def calculate_retention(
    monthly_invoices: List[float],
) -> Dict[str, Any]:
    """
    GCC 68.1/68.2 — Retention Calculation
    
    Rate: 5% per invoice
    Limit: 10% of contract value
    Release: 50% at handover, 50% at defects liability expiry
    """
    total_invoiced = sum(monthly_invoices) if monthly_invoices else 0
    retention_deducted = total_invoiced * PPR_2025["RETENTION_PCT"]
    retention_limit = total_invoiced * PPR_2025["RETENTION_LIMIT"]
    
    actual_retention = min(retention_deducted, retention_limit)
    total_releases = {
        "at_handover": round(actual_retention * 0.5, 2),
        "at_defects_expiry": round(actual_retention * 0.5, 2),
    }
    
    return {
        "monthly_rate_pct": PPR_2025["RETENTION_PCT"] * 100,
        "max_limit_pct": PPR_2025["RETENTION_LIMIT"] * 100,
        "total_invoiced": round(total_invoiced, 2),
        "retention_deducted": round(retention_deducted, 2),
        "retention_limit": round(retention_limit, 2),
        "actual_retention": round(actual_retention, 2),
        "release_schedule": total_releases,
        "formula": "Retention = 5% per invoice, max 10% cumulative (GCC 68.1/68.2)",
    }


def validate_subcontracting(
    subcontract_amount: float,
    contract_value: float,
) -> Dict[str, Any]:
    """
    ITT 7.1 — Subcontracting Limit
    
    Max 30% of contract value may be subcontracted.
    Key activities cannot be subcontracted.
    """
    max_allowed = contract_value * PPR_2025["SUBCONTRACT_MAX_PCT"]
    pct = (subcontract_amount / max(contract_value, 1)) * 100
    
    return {
        "subcontract_amount": round(subcontract_amount, 2),
        "contract_value": round(contract_value, 2),
        "pct": round(pct, 2),
        "max_allowed_pct": PPR_2025["SUBCONTRACT_MAX_PCT"] * 100,
        "max_allowed_amount": round(max_allowed, 2),
        "compliant": subcontract_amount <= max_allowed,
        "formula": "Subcontract ≤ 30% of Contract Value per ITT 7.1",
    }


def check_corrigendum_impact(
    original_deadline: str,
    new_deadline: str,
    original_value: float,
    new_value: float,
) -> Dict[str, Any]:
    """
    Check the impact of a corrigendum on bid strategy.
    
    Rule: If deadline extended by > 7 days, or value changed by > 10%, 
    re-evaluation is required.
    """
    from datetime import datetime
    
    impact_flags = []
    
    # Check deadline impact
    try:
        orig = datetime.strptime(original_deadline[:10], "%Y-%m-%d")
        new = datetime.strptime(new_deadline[:10], "%Y-%m-%d")
        days_change = (new - orig).days
        
        if days_change > 7:
            impact_flags.append(f"Deadline extended by {days_change} days — re-evaluate resource availability")
        elif days_change < 0:
            impact_flags.append(f"Deadline shortened by {abs(days_change)} days — URGENT review needed")
    except Exception:
        days_change = 0
    
    # Check value impact
    if new_value != original_value:
        value_change_pct = ((new_value - original_value) / max(original_value, 1)) * 100
        if abs(value_change_pct) > 10:
            impact_flags.append(f"Value changed by {value_change_pct:.1f}% — re-evaluate bid pricing")
    
    return {
        "has_impact": len(impact_flags) > 0,
        "impact_flags": impact_flags,
        "days_change": days_change,
        "value_change_pct": round(((new_value - original_value) / max(original_value, 1)) * 100, 1) if original_value else 0,
        "recommendation": "Re-run full evaluation" if len(impact_flags) > 0 else "No significant changes detected",
    }


class PPRWorksEngine:
    """Compatibility wrapper for the PPR 2025 works evaluation routes."""

    async def evaluate_works_tender(self, data: Dict[str, Any]) -> Dict[str, Any]:
        estimated_value = float(data.get("official_estimate", data.get("estimated_cost", 0)) or 0)
        responsive_bidders = data.get("responsive_bidders", []) or []
        bid_price = float(data.get("bid_price", data.get("quoted_bid_price", 0)) or 0)
        if bid_price <= 0 and responsive_bidders:
            first_bidder = responsive_bidders[0] if isinstance(responsive_bidders[0], dict) else {}
            bid_price = float(
                first_bidder.get("quoted_amount")
                or first_bidder.get("quoted_price")
                or first_bidder.get("bid_amount")
                or first_bidder.get("final_amount")
                or first_bidder.get("amount")
                or 0
            )
        bidder_count = int(data.get("bidder_count", len(responsive_bidders)) or 1)
        tender_id = data.get("tender_id", "")
        bid_ratio = bid_price / max(estimated_value, 1)
        discount_pct = max(0.0, (1.0 - bid_ratio) * 100.0)
        slt = detect_slt_alt(
            quoted_amount=bid_price,
            estimated_value=estimated_value,
            num_bidders=bidder_count,
            market_avg_discount=float(data.get("market_avg_discount", 5.0) or 5.0),
        )
        bid_security = evaluate_bid_security(
            estimated_value=estimated_value,
            submitted_security=float(data.get("bid_security_amount", data.get("bid_security", estimated_value * PPR_2025["BID_SECURITY_PCT"])) or 0),
        )
        arithmetic = check_arithmetic_errors(data.get("boq_items", []) or [])
        capacity = calculate_tender_capacity(
            annual_turnover=float(data.get("annual_turnover", data.get("turnover", estimated_value * 0.75)) or 0),
            current_commitments=float(data.get("current_commitments", 0) or 0),
            tender_estimated_value=estimated_value,
            years_in_business=int(data.get("years_in_business", data.get("experience_years", 5)) or 5),
        )
        performance_security = calculate_performance_security(max(estimated_value, bid_price))
        return {
            "tender_id": tender_id,
            "estimated_value": round(estimated_value, 2),
            "bid_price": round(bid_price, 2),
            "bid_ratio": round(bid_ratio, 4),
            "discount_pct": round(discount_pct, 2),
            "bidder_count": bidder_count,
            "slt_status": slt["slt_status"],
            "weighted_slt": slt["weighted_slt"],
            "threshold_breach": slt["threshold_breach"],
            "recommendation": slt["recommendation"],
            "bid_security": bid_security,
            "arithmetic": arithmetic,
            "capacity": capacity,
            "performance_security": performance_security,
            "responsive_bidders": responsive_bidders,
            "boq_items": data.get("boq_items", []) or [],
            "compliance_summary": {
                "responsive": arithmetic["verdict"] != "REJECTED" and bid_security["adequate"] and capacity["eligibility"] == "PASS",
                "slt_flag": slt["slt_status"],
                "capacity_eligibility": capacity["eligibility"],
                "security_adequate": bid_security["adequate"],
            },
        }
