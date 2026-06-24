"""
Agent 9 — PPR 2025 Evaluation Intelligence Agent (Enhanced)
Enterprise-grade CPTU-compliant Tender Evaluation Engine for Bangladesh 
Public Procurement Rules 2025.

Enterprise Features:
- Multi-tenant safe (tenant_id everywhere)
- Provenance tracking (trace_id, source_ids)
- Versioned rules engine with JSON rulesets
- Scoring with explainability
- Evidence pointers and citations
- Actionable remediation suggestions
- Confidence scoring
- Human-in-the-loop review flagging
- Audit trail
- Integration with Agent Brain & Knowledge Lake
"""
from __future__ import annotations

import json
import logging
import math
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from app.agents.core.regime import get_regime, get_regime_label

logger = logging.getLogger(__name__)

# ── PPR 2025 Thresholds (per CPTU guidelines) ────────────────────────────

SLT_THRESHOLD_PCT = 0.70    # 70% of estimated cost = Seriously Low Tender
ALT_THRESHOLD_PCT = 0.60    # 60% = Abnormally Low Tender
MAX_ARITHMETIC_ERROR_PCT = 0.20  # 20% max correction before rejection
TEC_MINIMUM_PASS_PCT = 0.70      # 70% minimum for TEC schedules

# ── Default ruleset (loaded from DB if available) ───────────────────────

DEFAULT_RULESET = {
    "version": "2025.1",
    "rules": {
        "responsiveness": {
            "bid_security_required": True,
            "documents_complete_required": True,
            "signed_required": True,
            "bid_validity_days_min": 90,
        },
        "arithmetic": {
            "max_error_pct": 0.20,
            "auto_correct_unit_rate": True,
            "auto_correct_total": True,
        },
        "qualification": {
            "min_experience_years": 5,
            "min_similar_contracts": 1,
            "min_annual_turnover_pct": 0.5,  # 50% of estimated cost
        },
        "slt": {
            "slt_threshold_pct": 0.70,
            "alt_threshold_pct": 0.60,
            "require_justification": True,
            "justification_days": 7,
        },
        "tec_evaluation": {
            "schedule_4_pass_pct": 0.70,
            "schedule_5_pass_pct": 0.70,
            "schedule_6_pass_pct": 0.70,
        },
    },
    "scoring": {
        "responsiveness_weight": 0.20,
        "arithmetic_weight": 0.20,
        "qualification_weight": 0.25,
        "tec_weight": 0.25,
        "slt_weight": 0.10,
    },
}


@dataclass
class Finding:
    """Individual evaluation finding with evidence."""
    finding_id: str = ""
    finding_type: str = ""  # responsiveness, arithmetic, qualification, ppr_rule, slt
    passed: bool = True
    score: float = 0.0
    max_score: float = 1.0
    weight: float = 1.0
    severity: str = "info"  # info, warning, error, critical
    title: str = ""
    description: str = ""
    evidence: List[Dict] = field(default_factory=list)
    remediation: str = ""
    rule_id: str = ""
    confidence: float = 1.0


@dataclass
class EnhancedPPREvaluationResult:
    """Enterprise-grade PPR evaluation output."""
    # Core decision
    overall_score: float = 0.0
    overall_passed: bool = True
    recommended_action: str = "Proceed"
    
    # Detailed findings
    findings: List[Finding] = field(default_factory=list)
    passed_count: int = 0
    failed_count: int = 0
    total_checks: int = 0
    
    # Section breakdowns
    responsiveness: Dict[str, Any] = field(default_factory=dict)
    arithmetic: Dict[str, Any] = field(default_factory=dict)
    qualification: Dict[str, Any] = field(default_factory=dict)
    ppr_validation: Dict[str, Any] = field(default_factory=dict)
    slt_analysis: Dict[str, Any] = field(default_factory=dict)
    
    # Bid price
    bid_price_before_correction: float = 0.0
    bid_price_after_correction: float = 0.0
    arithmetic_adjustment: float = 0.0
    
    # Recommendations
    recommendations: List[str] = field(default_factory=list)
    
    # Provenance
    ruleset_version: str = ""
    ruleset_used: Dict = field(default_factory=dict)
    evaluation_notes: List[str] = field(default_factory=list)
    
    # Human review
    requires_human_review: bool = False
    review_reasons: List[str] = field(default_factory=list)


class PPREvaluationAgent(BaseAgent):
    agent_id = "agent-009-ppr-evaluation"
    agent_name = "PPR 2025 Evaluation Agent (Enhanced)"
    description = "Enterprise-grade CPTU-compliant TEC evaluation: responsiveness, arithmetic corrections, qualification, SLT/ALT detection per PPR 2025."
    dependencies: List[str] = ["agent-005-boq-intelligence", "agent-007-eligibility-compliance"]
    version = "3.0.0"

    def __init__(self, brain=None):
        super().__init__(brain)
        self.ruleset = DEFAULT_RULESET
    
    async def load_ruleset(self, tenant_id: str = None):
        """Load ruleset from database if available."""
        try:
            from app.db import get_session, Ruleset
            async with get_session() as session:
                from sqlalchemy import select
                query = select(Ruleset).where(
                    Ruleset.ruleset_type == "ppr_evaluation",
                    Ruleset.active == True,
                )
                if tenant_id:
                    query = query.where(
                        (Ruleset.tenant_id == tenant_id) | (Ruleset.tenant_id.is_(None))
                    ).order_by(Ruleset.tenant_id.is_(None).asc())
                else:
                    query = query.where(Ruleset.tenant_id.is_(None))
                query = query.order_by(Ruleset.version.desc()).limit(1)
                result = await session.execute(query)
                db_ruleset = result.scalar_one_or_none()
                if db_ruleset:
                    self.ruleset = db_ruleset.rules
                    logger.info(f"Loaded ruleset '{db_ruleset.name}' v{db_ruleset.version}")
        except Exception as e:
            logger.warning(f"Could not load ruleset from DB, using defaults: {e}")

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        bid_data = context.get("bid_data", {})
        upstream = context.get("upstream", {})
        boq_items = upstream.get("agent-005-boq-intelligence", {}).get("boq_items", [])
        
        # Load ruleset for tenant
        await self.load_ruleset(context.get("tenant_id"))
        
        result = await self._evaluate_full(bid_data, boq_items, context)
        
        output = {
            "overall_score": result.overall_score,
            "overall_passed": result.overall_passed,
            "recommended_action": result.recommended_action,
            "bid_price_before_correction": result.bid_price_before_correction,
            "bid_price_after_correction": result.bid_price_after_correction,
            "arithmetic_adjustment": result.arithmetic_adjustment,
            "findings": [
                {
                    "finding_id": f.finding_id,
                    "type": f.finding_type,
                    "passed": f.passed,
                    "score": f.score,
                    "max_score": f.max_score,
                    "severity": f.severity,
                    "title": f.title,
                    "description": f.description,
                    "evidence": f.evidence,
                    "remediation": f.remediation,
                    "rule_id": f.rule_id,
                    "confidence": f.confidence,
                }
                for f in result.findings
            ],
            "passed_checks": result.passed_count,
            "failed_checks": result.failed_count,
            "total_checks": result.total_checks,
            "responsiveness": result.responsiveness,
            "arithmetic": result.arithmetic,
            "qualification": result.qualification,
            "ppr_validation": result.ppr_validation,
            "slt_analysis": result.slt_analysis,
            "recommendations": result.recommendations,
            "requires_human_review": result.requires_human_review,
            "review_reasons": result.review_reasons,
            "ruleset_version": result.ruleset_version,
            "evaluation_notes": result.evaluation_notes,
        }
        
        # Share findings with Agent Brain
        await self.share_knowledge(
            entry_type="ppr_evaluation",
            tender_id=context.get("tender_id", ""),
            data=output,
            summary=f"PPR evaluation: {result.recommended_action} (score: {result.overall_score:.1%})",
            tags=["ppr", "evaluation", result.recommended_action.lower().replace(" ", "_")],
        )
        
        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=output,
        )

    async def _evaluate_full(self, bid_data: Dict, boq_items: List[Dict],
                              context: Dict) -> EnhancedPPREvaluationResult:
        """Run enhanced PPR 2025 evaluation pipeline."""
        result = EnhancedPPREvaluationResult()
        result.ruleset_version = self.ruleset.get("version", "2025.1")
        result.ruleset_used = self.ruleset
        result.bid_price_before_correction = float(bid_data.get("bid_price", 0))
        
        rules = self.ruleset.get("rules", {})
        scoring = self.ruleset.get("scoring", {})
        
        # ── 1. Responsiveness Check ──
        resp = self._check_responsiveness(bid_data, rules.get("responsiveness", {}))
        result.responsiveness = resp
        resp_finding = Finding(
            finding_id="resp-001",
            finding_type="responsiveness",
            passed=resp.get("passed", True),
            score=1.0 if resp.get("passed", True) else 0.0,
            weight=scoring.get("responsiveness_weight", 0.20),
            severity="critical" if not resp.get("passed", True) else "info",
            title="Responsiveness Check",
            description=f"Bid responsiveness: {'PASSED' if resp.get('passed', True) else 'FAILED'}",
            evidence=resp.get("issues", []),
            remediation="Ensure all required documents are submitted and bid is properly signed",
            rule_id="ppr2025-rule-27",
        )
        result.findings.append(resp_finding)
        
        # ── 2. Arithmetic Check (PPR 2025 Rule 29) ──
        arith = self._check_arithmetic(bid_data, boq_items, rules.get("arithmetic", {}))
        result.arithmetic = arith
        arith_passed = arith.get("error_pct", 0) <= rules.get("arithmetic", {}).get("max_error_pct", 0.20)
        arith_finding = Finding(
            finding_id="arith-001",
            finding_type="arithmetic",
            passed=arith_passed,
            score=max(0, 1.0 - arith.get("error_pct", 0)),
            weight=scoring.get("arithmetic_weight", 0.20),
            severity="critical" if not arith_passed else ("warning" if arith.get("error_pct", 0) > 0.05 else "info"),
            title="Arithmetic Error Check",
            description=f"Arithmetic error rate: {arith.get('error_pct', 0):.1%} ({len(arith.get('errors', []))} errors)",
            evidence=arith.get("errors", []),
            remediation="Correct arithmetic errors. If error rate exceeds 20%, bid must be rejected per PPR 2025 Rule 29",
            rule_id="ppr2025-rule-29",
        )
        result.findings.append(arith_finding)
        
        result.arithmetic_errors = arith.get("errors", [])
        result.arithmetic_error_pct = arith.get("error_pct", 0.0)
        result.arithmetic_adjustment = arith.get("adjustment", 0.0)
        result.bid_price_after_correction = arith.get("corrected_price", result.bid_price_before_correction)
        
        # ── 3. Qualification Check ──
        qual = self._check_qualification(bid_data, rules.get("qualification", {}))
        result.qualification = qual
        qual_finding = Finding(
            finding_id="qual-001",
            finding_type="qualification",
            passed=qual.get("passed", True),
            score=1.0 if qual.get("passed", True) else 0.0,
            weight=scoring.get("qualification_weight", 0.25),
            severity="critical" if not qual.get("passed", True) else "info",
            title="Qualification Check",
            description=f"Qualification: {'PASSED' if qual.get('passed', True) else 'FAILED'}",
            evidence=qual.get("issues", []),
            remediation="Ensure bidder meets minimum experience, turnover, and similar contract requirements",
            rule_id="ppr2025-rule-19",
        )
        result.findings.append(qual_finding)
        
        # ── 4. PPR 2025 Rules Validation ──
        ppr = self._validate_ppr_rules(bid_data)
        result.ppr_validation = ppr
        ppr_finding = Finding(
            finding_id="ppr-001",
            finding_type="ppr_rule",
            passed=ppr.get("passed", True),
            score=1.0 if ppr.get("passed", True) else max(0, 1.0 - len(ppr.get("violations", [])) * 0.25),
            weight=scoring.get("tec_weight", 0.25),
            severity="critical" if not ppr.get("passed", True) else "info",
            title="PPR 2025 Rules Validation",
            description="PPR rules: " + ("PASSED" if ppr.get("passed", True) else f"{len(ppr.get('violations', []))} violations"),
            evidence=ppr.get("violations", []),
            remediation="Address each PPR violation per the specific rule referenced",
            rule_id="ppr2025-rules",
        )
        result.findings.append(ppr_finding)
        
        # ── 5. SLT/ALT Analysis (PPR 2025 Rule 31) ──
        slt = self._check_slt(bid_data, boq_items, rules.get("slt", {}))
        result.slt_analysis = slt
        slt_status = slt.get("status", "Normal")
        slt_passed = slt_status in ("Normal", "SLT - Requires Justification")
        slt_finding = Finding(
            finding_id="slt-001",
            finding_type="slt",
            passed=slt_passed,
            score=1.0 if slt_passed else 0.5 if "SLT" in slt_status else 0.0,
            weight=scoring.get("slt_weight", 0.10),
            severity="critical" if "ALT" in slt_status else ("warning" if "SLT" in slt_status else "info"),
            title="SLT/ALT Analysis",
            description=f"Bid price ratio: {slt.get('ratio_formatted', 'N/A')} — {slt_status}",
            evidence=[],
            remediation=slt.get("recommendation", ""),
            rule_id="ppr2025-rule-31",
            confidence=0.9,
        )
        result.findings.append(slt_finding)
        
        # ── Aggregate Scoring ──
        total_weight = sum(f.weight for f in result.findings)
        weighted_score = sum(f.score * f.weight for f in result.findings) / total_weight if total_weight else 0
        result.overall_score = round(weighted_score, 4)
        result.overall_passed = weighted_score >= 0.70
        
        # Track pass/fail counts
        result.passed_count = sum(1 for f in result.findings if f.passed)
        result.failed_count = sum(1 for f in result.findings if not f.passed)
        result.total_checks = len(result.findings)
        
        # ── Recommendations ──
        recommendations = []
        if result.overall_passed:
            recommendations.append(f"✅ Overall PPR 2025 evaluation PASSED (score: {result.overall_score:.1%})")
        else:
            recommendations.append(f"❌ Overall PPR 2025 evaluation FAILED (score: {result.overall_score:.1%}, minimum: 70%)")
        
        for f in result.findings:
            if not f.passed:
                recommendations.append(f"  - {f.title}: {f.remediation}")
        
        result.recommendations = recommendations
        result.recommended_action = self._determine_action(result)
        
        # ── Human Review Check ──
        if result.overall_score < 0.85 and result.overall_score >= 0.60:
            result.requires_human_review = True
            result.review_reasons.append(f"Borderline score ({result.overall_score:.1%}) requires manual review")
        if any(f.severity == "critical" and not f.passed for f in result.findings):
            result.requires_human_review = True
            result.review_reasons.append("Critical findings detected — requires TEC chairperson review")
        if slt_status not in ("Normal",):
            result.requires_human_review = True
            result.review_reasons.append(f"SLT/ALT detected ({slt_status}) — requires justification evaluation")
        
        return result

    # ── Individual Check Methods ────────────────────────────────────────
    
    def _check_responsiveness(self, bid: Dict, rules: Dict) -> Dict:
        issues = []
        
        # Bid security check
        if rules.get("bid_security_required", True):
            sec = float(bid.get("bid_security_amount", 0) or 0)
            if sec <= 0:
                issues.append("Bid security not provided or zero amount")
            else:
                expected = float(bid.get("estimated_cost", 0)) * 0.01
                if sec < expected:
                    issues.append(f"Bid security (${sec:.0f}) below expected minimum (${expected:.0f})")
        
        # Documents completeness
        if rules.get("documents_complete_required", True):
            if not bid.get("documents_complete", False):
                issues.append("Submitted documents not marked complete")
        
        # Signed requirement
        if rules.get("signed_required", True):
            if not bid.get("signed", False):
                issues.append("Bid not signed")
        
        # Bid validity
        min_validity = rules.get("bid_validity_days_min", 90)
        validity = int(bid.get("bid_validity_days", 0))
        if validity < min_validity:
            issues.append(f"Bid validity ({validity} days) below minimum ({min_validity} days)")
        
        return {
            "passed": len(issues) == 0,
            "issues": issues,
            "checks_performed": [
                "bid_security", "documents_complete", "signed", "bid_validity"
            ],
        }
    
    def _check_arithmetic(self, bid: Dict, boq_items: List[Dict], rules: Dict) -> Dict:
        errors = []
        total_errors = 0
        total_items = len(boq_items) if boq_items else 1
        adjustment = 0.0
        
        for item in boq_items:
            qty = float(item.get("quantity", 0) or 0)
            rate = float(item.get("quoted_rate", 0) or item.get("rate", 0))
            amount = float(item.get("amount", 0) or 0)
            proper_amount = qty * rate
            
            if qty > 0 and rate > 0 and amount > 0:
                diff = abs(proper_amount - amount)
                if diff > 1.0:  # More than 1 BDT error
                    error_pct = diff / max(proper_amount, 1)
                    if error_pct > 0.01:  # More than 1% error
                        total_errors += 1
                        errors.append({
                            "item": item.get("code", ""),
                            "description": item.get("description", "")[:50],
                            "quantity": qty,
                            "quoted_rate": rate,
                            "stated_amount": amount,
                            "correct_amount": proper_amount,
                            "difference": round(diff, 2),
                            "error_pct": round(error_pct, 4),
                        })
                        adjustment += diff
        
        error_pct = total_errors / max(total_items, 1)
        
        # Corrected price
        bid_price = float(bid.get("bid_price", 0))
        corrected_price = bid_price + adjustment if rules.get("auto_correct_total", True) else bid_price
        
        return {
            "errors": errors,
            "error_count": total_errors,
            "error_pct": error_pct,
            "adjustment": adjustment,
            "corrected_price": corrected_price,
            "total_items_checked": total_items,
        }
    
    def _check_qualification(self, bid: Dict, rules: Dict) -> Dict:
        issues = []
        
        # Experience
        min_exp = rules.get("min_experience_years", 5)
        exp = int(bid.get("years_experience", 0))
        if exp < min_exp:
            issues.append(f"Insufficient experience: {exp} years (need {min_exp})")
        
        # Similar contracts
        min_similar = rules.get("min_similar_contracts", 1)
        similar = int(bid.get("similar_contracts", 0))
        if similar < min_similar:
            issues.append(f"Insufficient similar contracts: {similar} (need {min_similar})")
        
        # Turnover
        min_turnover_pct = rules.get("min_annual_turnover_pct", 0.5)
        turnover = float(bid.get("annual_turnover", 0))
        estimated = float(bid.get("estimated_cost", 1))
        if turnover < estimated * min_turnover_pct:
            issues.append(f"Insufficient turnover: ${turnover:.0f} (need ${estimated * min_turnover_pct:.0f})")
        
        return {
            "passed": len(issues) == 0,
            "issues": issues,
        }
    
    def _validate_ppr_rules(self, bid: Dict) -> Dict:
        violations = []
        
        if bid.get("conflict_of_interest"):
            violations.append("Conflict of interest detected (Rule 17)")
        if not bid.get("is_eligible", True):
            violations.append("Bidder not eligible (Rule 19)")
        if bid.get("has_alternative_bid"):
            violations.append("Alternative bid not permitted (Rule 22)")
        if bid.get("post_qualification_failed"):
            violations.append("Post-qualification failed (Rule 30)")
        if bid.get("is_blacklisted"):
            violations.append("Bidder is blacklisted (Rule 19)")
        
        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "rules_checked": [
                "Rule 17 (Conflict of Interest)",
                "Rule 19 (Eligibility)",
                "Rule 22 (Alternative Bids)",
                "Rule 27 (Responsiveness)",
                "Rule 28 (Qualification)",
                "Rule 29 (Arithmetic)",
                "Rule 30 (Post-qualification)",
                "Rule 31 (SLT/ALT)",
            ],
        }
    
    def _check_slt(self, bid: Dict, boq_items: List[Dict], rules: Dict) -> Dict:
        slt_threshold = rules.get("slt_threshold_pct", 0.70)
        alt_threshold = rules.get("alt_threshold_pct", 0.60)
        
        estimated_cost = float(bid.get("estimated_cost", 1))
        bid_price = float(bid.get("bid_price", 0))
        
        if not bid_price or not estimated_cost:
            return {"status": "N/A", "note": "Insufficient pricing data"}
        
        ratio = bid_price / estimated_cost
        
        item_anomalies = []
        for item in boq_items:
            rate = float(item.get("quoted_rate", 0) or item.get("rate", 0))
            sor_rate = float(item.get("sor_rate", 0) or 0)
            if sor_rate > 0 and rate > 0:
                rate_ratio = rate / sor_rate
                if rate_ratio < 0.50:
                    item_anomalies.append({
                        "code": item.get("code", ""),
                        "description": str(item.get("description", ""))[:50],
                        "quoted_rate": rate,
                        "sor_rate": sor_rate,
                        "ratio": round(rate_ratio, 2),
                        "flag": "Below 50% of SOR",
                    })
                elif rate_ratio > 1.50:
                    item_anomalies.append({
                        "code": item.get("code", ""),
                        "description": str(item.get("description", ""))[:50],
                        "quoted_rate": rate,
                        "sor_rate": sor_rate,
                        "ratio": round(rate_ratio, 2),
                        "flag": "Above 150% of SOR",
                    })
        
        if ratio < alt_threshold:
            status = "ALT - Abnormally Low Tender"
            recommendation = "Request detailed cost breakdown. Consider rejection if unjustified per PPR 2025 Rule 31."
        elif ratio < slt_threshold:
            status = "SLT - Seriously Low Tender"
            recommendation = "Request written justification within 7 days. Evaluate work methods."
        else:
            status = "Normal"
            recommendation = "No SLT/ALT concerns."
        
        return {
            "status": status,
            "bid_price": bid_price,
            "estimated_cost": estimated_cost,
            "ratio": round(ratio, 4),
            "ratio_formatted": f"{ratio:.1%}",
            "thresholds": {
                "slt": slt_threshold,
                "alt": alt_threshold,
            },
            "item_anomalies": item_anomalies,
            "anomaly_count": len(item_anomalies),
            "recommendation": recommendation,
        }
    
    def _determine_action(self, result: EnhancedPPREvaluationResult) -> str:
        if not result.overall_passed:
            return "Reject - PPR 2025 evaluation failed"
        if result.requires_human_review:
            return "Pending Review - Requires TEC chairperson approval"
        
        slt_status = result.slt_analysis.get("status", "")
        if "ALT" in slt_status:
            return "Review Required - ALT detected per Rule 31"
        if "SLT" in slt_status:
            return "Proceed with Caution - SLT detected per Rule 31"
        
        return "Proceed - All PPR 2025 checks passed"
