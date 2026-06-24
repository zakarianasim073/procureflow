"""
Agent 9 — PPR 2025 Evaluation Intelligence Agent
CPTU-compliant Tender Evaluation Engine for Bangladesh Public Procurement Rules 2025.
Evaluates: responsiveness, arithmetic corrections, qualification, SLT/ALT detection.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from .base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


# ── PPR 2025 Thresholds (per CPTU guidelines) ────────────────────────────

SLT_THRESHOLD_PCT = 0.70  # 70% of estimated cost = Seriously Low Tender
ALT_THRESHOLD_PCT = 0.60  # 60% = Abnormally Low Tender
MAX_ARITHMETIC_ERROR_PCT = 0.20  # 20% max correction before rejection
CRITICAL_RATE_RATIO = 0.50  # Below 50% SOR → critical anomaly
WARNING_RATE_RATIO = 0.70   # Below 70% SOR → warning anomaly
HIGH_RATE_RATIO = 1.50       # Above 150% SOR → high rate flag

# Work-type cost-component estimates (material/labor/plant split)
WORK_TYPE_COST_SPLIT = {
    "earthwork": {"material": 0.05, "labor": 0.55, "plant": 0.40},
    "concrete": {"material": 0.55, "labor": 0.25, "plant": 0.20},
    "reinforcement": {"material": 0.70, "labor": 0.15, "plant": 0.15},
    "brickwork": {"material": 0.50, "labor": 0.30, "plant": 0.20},
    "finishing": {"material": 0.40, "labor": 0.40, "plant": 0.20},
    "painting": {"material": 0.45, "labor": 0.40, "plant": 0.15},
    "plumbing": {"material": 0.60, "labor": 0.25, "plant": 0.15},
    "electrical": {"material": 0.65, "labor": 0.20, "plant": 0.15},
    "roadwork": {"material": 0.40, "labor": 0.20, "plant": 0.40},
    "piling": {"material": 0.35, "labor": 0.25, "plant": 0.40},
    "steelwork": {"material": 0.65, "labor": 0.15, "plant": 0.20},
    "general": {"material": 0.40, "labor": 0.30, "plant": 0.30},
}


@dataclass
class PPREvaluationResult:
    """Structured PPR 2025 evaluation output."""
    responsive: bool = True
    arithmetic_errors: List[Dict] = field(default_factory=list)
    arithmetic_error_pct: float = 0.0
    arithmetic_adjustment: float = 0.0
    qualification_met: bool = True
    qualification_issues: List[str] = field(default_factory=list)
    ppr_rules_validated: bool = True
    ppr_violations: List[str] = field(default_factory=list)
    slt_analysis: Dict[str, Any] = field(default_factory=dict)
    evaluation_notes: List[str] = field(default_factory=list)
    recommended_action: str = "Proceed"
    bid_price_after_correction: float = 0.0


class PPREvaluationAgent(BaseAgent):
    agent_id = "agent-009-ppr-evaluation"
    agent_name = "PPR 2025 Evaluation Agent"
    description = "CPTU-compliant TEC evaluation: responsiveness, arithmetic, qualification, SLT analysis per PPR 2025."
    dependencies: List[str] = ["agent-005-boq-intelligence", "agent-007-eligibility-compliance"]
    version = "2.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        bid_data = context.get("bid_data", {})
        upstream = context.get("upstream", {})
        boq_items = upstream.get("agent-005-boq-intelligence", {}).get("boq_items", [])
        
        result = await self._evaluate_full(bid_data, boq_items)
        
        output = {
            "responsive": result.responsive,
            "arithmetic_errors": result.arithmetic_errors,
            "arithmetic_error_pct": result.arithmetic_error_pct,
            "arithmetic_adjustment": result.arithmetic_adjustment,
            "qualification_met": result.qualification_met,
            "qualification_issues": result.qualification_issues,
            "ppr_rules_validated": result.ppr_rules_validated,
            "ppr_violations": result.ppr_violations,
            "slt_analysis": result.slt_analysis,
            "evaluation_notes": result.evaluation_notes,
            "recommended_action": result.recommended_action,
            "bid_price_after_correction": result.bid_price_after_correction,
            "sections": {
                "responsiveness": self._check_responsiveness(bid_data),
                "arithmetic": self._check_arithmetic(bid_data, boq_items),
                "qualification": self._check_qualification(bid_data),
                "ppr_validation": self._validate_ppr_rules(bid_data),
                "slt": self._check_slt(bid_data, boq_items),
            },
        }
        
        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=output,
        )

    async def _evaluate_full(self, bid_data: Dict, boq_items: List[Dict]) -> PPREvaluationResult:
        """Run full PPR 2025 evaluation pipeline."""
        result = PPREvaluationResult()
        
        # 1. Responsiveness check
        resp = self._check_responsiveness(bid_data)
        if not resp.get("passed", True):
            result.responsive = False
            result.evaluation_notes.extend(resp.get("issues", []))
        
        # 2. Arithmetic check (PPR 2025 Rule 29)
        arith = self._check_arithmetic(bid_data, boq_items)
        result.arithmetic_errors = arith.get("errors", [])
        result.arithmetic_error_pct = arith.get("error_pct", 0.0)
        result.arithmetic_adjustment = arith.get("adjustment", 0.0)
        result.bid_price_after_correction = arith.get("corrected_price", bid_data.get("bid_price", 0))
        
        if result.arithmetic_error_pct > MAX_ARITHMETIC_ERROR_PCT:
            result.responsive = False
            result.evaluation_notes.append(
                f"Arithmetic errors exceed {MAX_ARITHMETIC_ERROR_PCT:.0%}: {result.arithmetic_error_pct:.1%}"
            )
        
        # 3. Qualification check
        qual = self._check_qualification(bid_data)
        result.qualification_met = qual.get("passed", True)
        result.qualification_issues = qual.get("issues", [])
        
        # 4. PPR 2025 rules validation
        ppr = self._validate_ppr_rules(bid_data)
        result.ppr_rules_validated = ppr.get("passed", True)
        result.ppr_violations = ppr.get("violations", [])
        
        # 5. SLT/ALT analysis (PPR 2025 Rule 31)
        slt = self._check_slt(bid_data, boq_items)
        result.slt_analysis = slt
        
        # 6. Determine recommended action
        result.recommended_action = self._determine_action(result)
        
        return result

    def _check_responsiveness(self, bid: Dict) -> Dict:
        """Check bid responsiveness per PPR 2025 Rule 27."""
        issues = []
        
        # Check bid security (EMD)
        emd = bid.get("bid_security", 0)
        emd_required = bid.get("bid_security_required", 0)
        if emd < emd_required:
            issues.append(f"Insufficient bid security: {emd} < {emd_required}")
        
        # Check validity period
        validity = bid.get("bid_validity_days", 0)
        if validity < 90:
            issues.append(f"Bid validity too short: {validity} days (min 90)")
        
        # Check document completeness
        missing_docs = bid.get("missing_documents", [])
        if missing_docs:
            issues.append(f"Missing documents: {', '.join(missing_docs)}")
        
        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "bid_security_ok": emd >= emd_required,
            "validity_ok": validity >= 90,
        }

    def _check_arithmetic(self, bid: Dict, boq_items: List[Dict]) -> Dict:
        """
        PPR 2025 Rule 29: Arithmetic error correction.
        - Unit rate prevails over total
        - Multiplication error: correct quantity × rate
        - Addition error: correct line total
        """
        errors = []
        total_original = 0.0
        total_corrected = 0.0
        
        for item in boq_items:
            qty = float(item.get("quantity", 0))
            rate = float(item.get("quoted_rate", 0) or item.get("rate", 0))
            line_total = float(item.get("line_total", qty * rate))
            
            original_total = line_total
            corrected_total = qty * rate
            
            total_original += original_total
            total_corrected += corrected_total
            
            if abs(original_total - corrected_total) > 1.0:
                errors.append({
                    "item_no": item.get("item_no", ""),
                    "code": item.get("code", ""),
                    "description": item.get("description", "")[:50],
                    "quantity": qty,
                    "rate": rate,
                    "original_total": original_total,
                    "corrected_total": corrected_total,
                    "error_amount": corrected_total - original_total,
                })
        
        error_pct = abs(total_corrected - total_original) / max(total_corrected, 1)
        adjustment = total_corrected - total_original
        
        return {
            "errors": errors,
            "total_errors": len(errors),
            "original_price": total_original,
            "corrected_price": total_corrected,
            "adjustment": adjustment,
            "error_pct": error_pct,
            "error_pct_formatted": f"{error_pct:.2%}",
        }

    def _check_qualification(self, bid: Dict) -> Dict:
        """Check bidder qualification per PPR 2025 Rule 28."""
        issues = []
        
        # Experience
        years = bid.get("years_experience", 0)
        required_years = bid.get("required_experience_years", 5)
        if years < required_years:
            issues.append(f"Insufficient experience: {years} years (need {required_years})")
        
        # Turnover
        turnover = bid.get("annual_turnover", 0)
        required_turnover = bid.get("required_turnover", 0)
        if required_turnover and turnover < required_turnover:
            issues.append(f"Turnover too low: ৳{turnover:,.0f} (need ৳{required_turnover:,.0f})")
        
        # Similar contracts
        similar = bid.get("similar_contracts", 0)
        required_similar = bid.get("required_similar_contracts", 1)
        if similar < required_similar:
            issues.append(f"Insufficient similar contracts: {similar} (need {required_similar})")
        
        return {
            "passed": len(issues) == 0,
            "issues": issues,
        }

    def _validate_ppr_rules(self, bid: Dict) -> Dict:
        """Validate against key PPR 2025 rules."""
        violations = []
        
        # Rule 17: Conflict of interest
        if bid.get("conflict_of_interest"):
            violations.append("Conflict of interest detected (Rule 17)")
        
        # Rule 19: Eligibility
        if not bid.get("is_eligible"):
            violations.append("Bidder not eligible (Rule 19)")
        
        # Rule 22: Alternative bids
        if bid.get("has_alternative_bid"):
            violations.append("Alternative bid not permitted (Rule 22)")
        
        # Rule 30: Post-qualification
        if bid.get("post_qualification_failed"):
            violations.append("Post-qualification failed (Rule 30)")
        
        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "rules_checked": ["Rule 17", "Rule 19", "Rule 22", "Rule 27", "Rule 28", "Rule 29", "Rule 30", "Rule 31"],
        }

    def _check_slt(self, bid: Dict, boq_items: List[Dict]) -> Dict:
        """
        PPR 2025 Rule 31: Seriously Low Tender (SLT) & Abnormally Low Tender (ALT).
        Enhanced analysis with item-level, work-type, cost-component, and risk scoring.
        """
        estimated_cost = float(bid.get("estimated_cost", 1))
        bid_price = float(bid.get("bid_price", 0))
        
        if not bid_price or not estimated_cost:
            return {"status": "N/A", "note": "Insufficient pricing data"}
        
        return _analyze_slt(boq_items, estimated_cost, bid_price)

    def _determine_action(self, result: PPREvaluationResult) -> str:
        """Determine TEC recommended action based on all checks."""
        if not result.responsive:
            if result.arithmetic_error_pct > MAX_ARITHMETIC_ERROR_PCT:
                return "Reject - Excessive arithmetic errors"
            return "Reject - Non-responsive bid"
        
        if not result.qualification_met:
            return "Reject - Qualification not met"
        
        if not result.ppr_rules_validated:
            return "Review - PPR violations found"
        
        slt_status = result.slt_analysis.get("overall", {}).get("status", "")
        if not slt_status:
            slt_status = result.slt_analysis.get("status", "")
        if "ALT" in slt_status:
            return "Review - Abnormally Low Tender (Rule 31)"
        if "SLT" in slt_status:
            return "Proceed with caution - Seriously Low Tender (Rule 31)"
        
        return "Proceed - All PPR 2025 checks passed"


# ── Standalone SLT Analysis (usable from API) ──────────────────────────────


def _infer_work_type(description: str, code: str = "") -> str:
    """Infer work type from item description or code."""
    text = f"{description} {code}".lower()
    if any(k in text for k in ("earth", "excavation", "cutting", "filling", "embankment", "dredging")):
        return "earthwork"
    if any(k in text for k in ("concrete", "cement", "cc ", "rcc", "pcc")):
        return "concrete"
    if any(k in text for k in ("reinforcement", "steel", "rebar", "ms rod", "deformed bar")):
        return "reinforcement"
    if any(k in text for k in ("brick", "block", "masonry")):
        return "brickwork"
    if any(k in text for k in ("plaster", "tile", "floor", "finish", "skirting")):
        return "finishing"
    if any(k in text for k in ("paint", "varnish", "distemper")):
        return "painting"
    if any(k in text for k in ("pipe", "plumb", "sanitary", "water supply", "drainage")):
        return "plumbing"
    if any(k in text for k in ("cable", "wire", "electrical", "switch", "light", "conduit")):
        return "electrical"
    if any(k in text for k in ("road", "pavement", "asphalt", "bitumen", "carpet")):
        return "roadwork"
    if any(k in text for k in ("pile", "piling", "boring")):
        return "piling"
    if any(k in text for k in ("truss", "purlin", "rafter", "structural steel")):
        return "steelwork"
    return "general"


def _classify_rate_anomaly(rate: float, sor_rate: float) -> Optional[str]:
    """Classify a rate anomaly severity."""
    if rate <= 0:
        return "zero_rate"
    ratio = rate / sor_rate
    if ratio < CRITICAL_RATE_RATIO:
        return "critical"
    if ratio < WARNING_RATE_RATIO:
        return "warning"
    if ratio > HIGH_RATE_RATIO:
        return "above_sor"
    return None


def _analyze_slt(
    boq_items: List[Dict],
    estimated_cost: float,
    bid_price: float,
) -> Dict:
    """
    Full PPR 2025 Rule 31 SLT/ALT analysis engine.
    Returns structured analysis with overall status, item anomalies,
    work-type breakdown, cost-component estimates, risk scoring,
    and justification requirements.
    """
    ratio = bid_price / estimated_cost if estimated_cost > 0 else 1.0

    # ── 1. Item-level anomaly analysis ────────────────────────────────────
    critical_items = []
    warning_items = []
    above_sor_items = []
    zero_rate_items = []
    item_details_by_type: Dict[str, list] = {}

    for item in boq_items:
        rate = float(item.get("quoted_rate", 0) or item.get("rate", 0))
        sor_rate = float(item.get("sor_rate", 0) or 0)
        desc = str(item.get("description", ""))[:80]
        code = str(item.get("code", ""))
        qty = float(item.get("quantity", 0))
        work_type = item.get("work_type", "") or _infer_work_type(desc, code)
        line_total = rate * qty
        sor_total = sor_rate * qty

        record = {
            "code": code,
            "description": desc,
            "work_type": work_type,
            "quantity": qty,
            "unit": str(item.get("unit", "")),
            "quoted_rate": round(rate, 2),
            "sor_rate": round(sor_rate, 2),
            "line_total": round(line_total, 2),
            "sor_total": round(sor_total, 2),
        }

        if work_type not in item_details_by_type:
            item_details_by_type[work_type] = []
        item_details_by_type[work_type].append(record)

        if sor_rate > 0 and rate > 0:
            rate_ratio = rate / sor_rate
            record["ratio"] = round(rate_ratio, 4)
            record["ratio_formatted"] = f"{rate_ratio:.1%}"
            anomaly = _classify_rate_anomaly(rate, sor_rate)
            if anomaly == "critical":
                record["flag"] = "CRITICAL - Below 50% SOR"
                record["severity"] = "high"
                critical_items.append(record)
            elif anomaly == "warning":
                record["flag"] = "WARNING - Below 70% SOR"
                record["severity"] = "medium"
                warning_items.append(record)
            elif anomaly == "above_sor":
                record["flag"] = "Above 150% SOR"
                record["severity"] = "medium"
                above_sor_items.append(record)
        elif rate <= 0 and sor_rate > 0:
            record["flag"] = "ZERO RATE"
            record["severity"] = "high"
            zero_rate_items.append(record)

    # ── 2. Work-type level aggregation ────────────────────────────────────
    work_type_analysis = []
    for wt, items in item_details_by_type.items():
        wt_sor = sum(i.get("sor_total", 0) for i in items)
        wt_quoted = sum(i.get("line_total", 0) for i in items)
        wt_discount_pct = round((wt_sor - wt_quoted) / wt_sor * 100, 1) if wt_sor > 0 else 0
        critical_count = sum(1 for i in items if i.get("severity") == "high")
        
        risk = "low"
        if critical_count > 3:
            risk = "high"
        elif critical_count > 1:
            risk = "medium"

        work_type_analysis.append({
            "work_type": wt,
            "items": len(items),
            "sor_amount": round(wt_sor, 2),
            "quoted_amount": round(wt_quoted, 2),
            "discount_pct": wt_discount_pct,
            "critical_anomalies": critical_count,
            "risk": risk,
        })

    # Sort by discount_pct descending (most discounted first)
    work_type_analysis.sort(key=lambda x: x["discount_pct"], reverse=True)
    driving_types = [wt for wt in work_type_analysis if wt["discount_pct"] > 15]

    # ── 3. Cost component estimate ───────────────────────────────────────
    total_quoted = sum(i.get("line_total", 0) for i in boq_items) or bid_price
    material_total = 0.0
    labor_total = 0.0
    plant_total = 0.0

    for wt, items in item_details_by_type.items():
        split = WORK_TYPE_COST_SPLIT.get(wt, WORK_TYPE_COST_SPLIT["general"])
        wt_quoted = sum(i.get("line_total", 0) for i in items)
        material_total += wt_quoted * split["material"]
        labor_total += wt_quoted * split["labor"]
        plant_total += wt_quoted * split["plant"]

    def _flag_component(amount: float, total: float, label: str) -> Dict:
        pct = round(amount / total * 100, 1) if total > 0 else 0
        flag = "normal"
        if label == "labor" and pct < 15:
            flag = "low - potential labor exploitation risk"
        elif label == "material" and pct < 25:
            flag = "low - possible material cost under-estimation"
        elif label == "plant" and pct < 10:
            flag = "low - minimal plant/equipment allocation"
        return {"amount": round(amount, 2), "pct": pct, "flag": flag}

    cost_components = {
        "material": _flag_component(material_total, total_quoted, "material"),
        "labor": _flag_component(labor_total, total_quoted, "labor"),
        "plant": _flag_component(plant_total, total_quoted, "plant"),
    }

    # ── 4. Risk scoring ──────────────────────────────────────────────────
    risk_factors = []
    risk_score = 0

    # Ratio risk
    if ratio < ALT_THRESHOLD_PCT:
        risk_score += 40
        risk_factors.append("Bid-to-estimate ratio below ALT threshold (60%)")
    elif ratio < SLT_THRESHOLD_PCT:
        risk_score += 25
        risk_factors.append("Bid-to-estimate ratio below SLT threshold (70%)")
    elif ratio < 0.85:
        risk_score += 10
        risk_factors.append("Bid-to-estimate ratio below 85% (moderate discount)")

    # Anomaly risk
    anomaly_penalty = min(len(critical_items) * 5, 25)
    if anomaly_penalty > 0:
        risk_score += anomaly_penalty
        risk_factors.append(f"{len(critical_items)} item(s) with rates below 50% of SOR")

    warning_penalty = min(len(warning_items) * 2, 10)
    if warning_penalty > 0:
        risk_score += warning_penalty
        risk_factors.append(f"{len(warning_items)} item(s) with rates below 70% of SOR")

    zero_rate_penalty = min(len(zero_rate_items) * 8, 20)
    if zero_rate_penalty > 0:
        risk_score += zero_rate_penalty
        risk_factors.append(f"{len(zero_rate_items)} item(s) with zero quoted rate")

    # Work type concentration risk
    if driving_types:
        concentration_penalty = min(len(driving_types) * 3, 10)
        risk_score += concentration_penalty
        risk_factors.append(f"{len(driving_types)} work type(s) with >15% discount driving SLT risk")

    # Cost component risk
    for comp_name, comp_data in cost_components.items():
        if "low" in comp_data["flag"]:
            risk_score += 5
            risk_factors.append(f"{comp_name.capitalize()} component unusually low ({comp_data['pct']}%)")

    risk_score = min(risk_score, 100)
    if risk_score >= 70:
        risk_level = "critical"
    elif risk_score >= 45:
        risk_level = "high"
    elif risk_score >= 25:
        risk_level = "medium"
    else:
        risk_level = "low"

    # ── 5. Overall classification ────────────────────────────────────────
    if ratio < ALT_THRESHOLD_PCT:
        status = "ALT - Abnormally Low Tender"
        summary_note = (
            "Bid price is less than 60% of estimated cost. Per PPR 2025 Rule 31(1)(b), "
            "this qualifies as an Abnormally Low Tender requiring detailed cost breakdown "
            "and potential rejection if justification is inadequate."
        )
    elif ratio < SLT_THRESHOLD_PCT:
        status = "SLT - Seriously Low Tender"
        summary_note = (
            "Bid price is less than 70% of estimated cost. Per PPR 2025 Rule 31(1)(a), "
            "this qualifies as a Seriously Low Tender requiring written justification "
            "from the bidder on work methods and cost savings."
        )
    else:
        status = "Normal"
        summary_note = "Bid price is within acceptable range. No SLT/ALT concerns under PPR 2025 Rule 31."

    # ── 6. Justification requirements ────────────────────────────────────
    items_requiring_justification = []
    for item in critical_items + warning_items + zero_rate_items:
        items_requiring_justification.append({
            "code": item["code"],
            "description": item["description"],
            "work_type": item["work_type"],
            "quoted_rate": item["quoted_rate"],
            "sor_rate": item["sor_rate"],
            "flag": item.get("flag", ""),
            "reason": (
                "Rate is below 50% of SOR - justify cost saving method"
                if item.get("severity") == "high" and "zero" not in item.get("flag", "").lower()
                else "Rate is below 70% of SOR - provide justification"
                if item.get("severity") == "medium"
                else "Zero rate provided - clarify or correct"
            ),
        })

    requires_justification = ratio < SLT_THRESHOLD_PCT or len(critical_items) > 0 or len(zero_rate_items) > 0

    # ── 7. Recommendation ───────────────────────────────────────────────
    if ratio < ALT_THRESHOLD_PCT:
        recommendation = (
            "Request detailed cost breakdown from bidder within 7 days. "
            "Evaluate component costs (material, labor, plant) against market rates. "
            "If justification is inadequate, TEC may recommend rejection per PPR 2025 Rule 31(3)."
        )
    elif ratio < SLT_THRESHOLD_PCT:
        recommendation = (
            "Request written justification from bidder within 7 days. "
            "Assess proposed work methods, technology advantages, and cost-saving measures. "
            "Proceed with evaluation if justification is satisfactory."
        )
    elif len(critical_items) > 0 or len(zero_rate_items) > 0:
        recommendation = (
            f"Bid overall is within normal range, but {len(critical_items) + len(zero_rate_items)} item(s) "
            f"require clarification. Request written justification for flagged items."
        )
    else:
        recommendation = "No SLT/ALT concerns. Proceed with standard evaluation."

    return {
        "overall": {
            "status": status,
            "bid_price": bid_price,
            "estimated_cost": estimated_cost,
            "ratio": round(ratio, 4),
            "ratio_formatted": f"{ratio:.1%}",
            "thresholds": {
                "slt": SLT_THRESHOLD_PCT,
                "alt": ALT_THRESHOLD_PCT,
            },
            "summary": summary_note,
        },
        "item_anomalies": {
            "critical": critical_items,
            "warning": warning_items,
            "above_sor": above_sor_items,
            "zero_rate": zero_rate_items,
            "total_critical": len(critical_items),
            "total_warning": len(warning_items),
            "total_above_sor": len(above_sor_items),
            "total_zero_rate": len(zero_rate_items),
        },
        "work_type_analysis": {
            "by_type": work_type_analysis,
            "driving_types": driving_types,
            "total_types": len(work_type_analysis),
        },
        "cost_components": cost_components,
        "risk_assessment": {
            "score": risk_score,
            "level": risk_level,
            "factors": risk_factors,
        },
        "justification_requirements": {
            "required": requires_justification,
            "items": items_requiring_justification,
            "total_items_flagged": len(items_requiring_justification),
            "deadline_days": 7,
            "ppr_reference": "PPR 2025 Rule 31(2)",
        },
        "recommendation": recommendation,
    }
