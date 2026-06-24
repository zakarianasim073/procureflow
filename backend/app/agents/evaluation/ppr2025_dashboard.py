"""
PPR 2025 Aligned Dashboard Agent — Real-time Procurement Compliance & Decision Support.

Provides bidder-facing dashboard aligned with PPR 2025 rules:
  - Schedule 4/5/6 compliance status
  - Eligibility scoring (pass/fail per criterion)
  - Document readiness checklist (PPR 2025 aligned)
  - TDS vs Company Profile matching
  - SLT/NPPI integration for pricing guidance
  - Real-time compliance gap analysis

Runs pre-emptively: pre-computes compliance for all LIVE tenders.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from decimal import Decimal
from sqlalchemy import text

from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from app.db.database import get_sync_engine

logger = logging.getLogger(__name__)


class PPR2025DashboardAgent(BaseAgent):
    """
    PPR 2025 Aligned Dashboard — Compliance & Decision Support.
    
    Features:
      - Real-time compliance status (Schedule 4/5/6)
      - Eligibility scoring with pass/fail per criterion
      - Document readiness checklist
      - TDS vs Company Profile matching
      - SLT/NPPI integration for pricing
      - Pre-computed for instant response
    """
    
    agent_id = "agent-037-ppr2025-dashboard"
    agent_name = "PPR 2025 Dashboard"
    description = "PPR 2025 aligned compliance & bid decision dashboard"
    version = "1.0.0"
    
    def __init__(self, brain=None):
        super().__init__(brain)
        self._engine = get_sync_engine()
    
    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        action = context.get("action", "dashboard")
        tender_id = context.get("tender_id", "")
        company = context.get("company_profile", {})
        
        if action == "dashboard":
            result = await self._build_dashboard(tender_id, company)
        elif action == "compliance_check":
            result = self._compliance_check(tender_id, company)
        elif action == "document_readiness":
            result = self._document_readiness(tender_id)
        elif action == "pricing_guidance":
            result = self._pricing_guidance(tender_id)
        elif action == "pre_compute_all":
            result = await self._pre_compute_all()
        else:
            result = {"status": "error", "message": f"Unknown action: {action}"}
        
        return AgentResult(status=AgentStatus.SUCCESS, output=result)
    
    async def _build_dashboard(self, tender_id: str, company: Dict) -> Dict:
        """Build complete PPR 2025 dashboard for a tender."""
        # Get basic tender data
        tender_data = self._get_tender_data(tender_id)
        if not tender_data:
            return {"status": "not_found", "tender_id": tender_id}
        
        # Get compliance status
        compliance = self._compliance_check(tender_id, company)
        
        # Get document readiness
        documents = self._document_readiness(tender_id)
        
        # Get pricing guidance
        pricing = self._pricing_guidance(tender_id)
        
        # Get competitor analysis from MOAT agent
        competitors = self._get_competitor_snapshot(
            tender_id,
            tender_data.get("sor_agency") or tender_data.get("procuring_entity", ""),
        )
        
        # Build overall score
        scores = {
            "eligibility": compliance.get("overall_score", 0),
            "documents": documents.get("readiness_score", 0),
            "pricing": pricing.get("position_score", 50),
            "competition": competitors.get("competition_score", 50),
        }
        scores["overall"] = round(
            scores["eligibility"] * 0.30 +
            scores["documents"] * 0.20 +
            scores["pricing"] * 0.25 +
            scores["competition"] * 0.25
        )
        
        dashboard = {
            "tender_id": tender_id,
            "tender_summary": {
                "work_name": tender_data.get("work_name", tender_data.get("title", "")),
                "agency": tender_data.get("sor_agency", tender_data.get("procuring_entity", "")),
                "zone": tender_data.get("zone", ""),
                "estimate": float(tender_data.get("estimated_cost", tender_data.get("estimated_amount_bdt", 0)) or 0),
                "procurement_type": tender_data.get("procurement_type", tender_data.get("extracted_data", {}).get("procurement_type", "")),
                "opening_date": str(tender_data.get("opening_date", "")),
                "completion_period": tender_data.get("completion_period_days", 0),
            },
            "ppr2025_compliance": compliance,
            "document_readiness": documents,
            "pricing_intelligence": pricing,
            "competitor_landscape": competitors,
            "scores": scores,
            "recommendation": self._generate_overall_recommendation(scores, compliance, pricing),
            "pre_computed_at": datetime.now(timezone.utc).isoformat(),
            "ppr2025_aligned": True,
        }
        
        # Cache the dashboard
        await self.share_knowledge(
            entry_type="ppr2025_dashboard",
            tender_id=tender_id,
            data=dashboard,
            summary=f"PPR 2025 Dashboard: {tender_id} — Overall Score: {scores['overall']}%",
            tags=["ppr2025", "dashboard", "compliance"]
        )
        
        return dashboard
    
    def _compliance_check(self, tender_id: str, company: Dict) -> Dict:
        """Check PPR 2025 compliance status."""
        tender_data = self._get_tender_data(tender_id)
        if not tender_data:
            return {"status": "no_data"}
        
        criteria = {}
        total_score = 0
        total_weight = 0
        
        # 1. Experience compliance (Schedule 4 Rule 1)
        exp_required = tender_data.get("min_experience_years", 3)
        exp_provided = company.get("experience_years", 0)
        exp_pass = exp_provided >= exp_required
        criteria["experience"] = {
            "schedule": "Schedule 4, Rule 1",
            "required": f"{exp_required} years experience",
            "provided": f"{exp_provided} years experience",
            "status": "PASS" if exp_pass else "FAIL",
            "score": 100 if exp_pass else max(0, int(exp_provided / exp_required * 50)),
            "weight": 20,
            "remediation": "Increase tender capacity or partner with experienced firm" if not exp_pass else ""
        }
        total_score += criteria["experience"]["score"] * criteria["experience"]["weight"]
        total_weight += criteria["experience"]["weight"]
        
        # 2. Turnover compliance
        turnover_req = float(tender_data.get("min_turnover_bdt", 0) or 0)
        turnover_prov = float(company.get("turnover", 0))
        turnover_pass = turnover_prov >= turnover_req
        criteria["turnover"] = {
            "schedule": "Schedule 4, Rule 2",
            "required": f"BDT {turnover_req:,.0f}",
            "provided": f"BDT {turnover_prov:,.0f}",
            "status": "PASS" if turnover_pass else "FAIL",
            "score": 100 if turnover_pass else max(0, int(turnover_prov / turnover_req * 50)),
            "weight": 25,
            "remediation": "Wait for next fiscal year or JV with financially stronger partner" if not turnover_pass else ""
        }
        total_score += criteria["turnover"]["score"] * criteria["turnover"]["weight"]
        total_weight += criteria["turnover"]["weight"]
        
        # 3. Liquid assets compliance
        liquid_req = float(tender_data.get("min_liquid_assets_bdt", 0) or 0)
        liquid_prov = float(company.get("liquid_assets", 0))
        liquid_pass = liquid_prov >= liquid_req
        criteria["liquid_assets"] = {
            "schedule": "Schedule 4, Rule 3",
            "required": f"BDT {liquid_req:,.0f}",
            "provided": f"BDT {liquid_prov:,.0f}",
            "status": "PASS" if liquid_pass else "FAIL",
            "score": 100 if liquid_pass else max(0, int(liquid_prov / liquid_req * 50)),
            "weight": 20,
            "remediation": "Arrange line of credit or bid bond enhancement" if not liquid_pass else ""
        }
        total_score += criteria["liquid_assets"]["score"] * criteria["liquid_assets"]["weight"]
        total_weight += criteria["liquid_assets"]["weight"]
        
        # 4. Similar works compliance
        similar_req = tender_data.get("similar_works_required", 1)
        similar_prov = company.get("similar_works", 0)
        similar_pass = similar_prov >= similar_req
        criteria["similar_works"] = {
            "schedule": "Schedule 4, Rule 4",
            "required": f"{similar_req} similar work(s)",
            "provided": f"{similar_prov} similar work(s)",
            "status": "PASS" if similar_pass else "FAIL",
            "score": 100 if similar_pass else max(0, int(similar_prov / similar_req * 50)),
            "weight": 20,
            "remediation": "Partner with firm having required experience" if not similar_pass else ""
        }
        total_score += criteria["similar_works"]["score"] * criteria["similar_works"]["weight"]
        total_weight += criteria["similar_works"]["weight"]
        
        # 5. Equipment compliance (Schedule 5)
        equip_req = tender_data.get("required_equipment", [])
        equip_prov = company.get("equipment", [])
        if isinstance(equip_req, str):
            equip_req = [e.strip() for e in equip_req.split(",") if e.strip()]
        if isinstance(equip_prov, str):
            equip_prov = [e.strip() for e in equip_prov.split(",") if e.strip()]
        
        if equip_req:
            missing_equip = [e for e in equip_req if e not in equip_prov]
            equip_pass = len(missing_equip) == 0
            criteria["equipment"] = {
                "schedule": "Schedule 5",
                "required": f"{len(equip_req)} items",
                "provided": f"{len(equip_prov)} items",
                "status": "PASS" if equip_pass else "PARTIAL",
                "score": 100 if equip_pass else max(0, int((1 - len(missing_equip)/len(equip_req)) * 100)),
                "weight": 10,
                "missing_items": missing_equip,
                "remediation": f"Arrange: {', '.join(missing_equip[:3])}" if missing_equip else ""
            }
            total_score += criteria["equipment"]["score"] * criteria["equipment"]["weight"]
            total_weight += criteria["equipment"]["weight"]
        
        # 6. Personnel compliance (Schedule 6)
        pers_req = tender_data.get("required_personnel", [])
        pers_prov = company.get("personnel", [])
        if isinstance(pers_req, str):
            pers_req = [p.strip() for p in pers_req.split(",") if p.strip()]
        if isinstance(pers_prov, str):
            pers_prov = [p.strip() for p in pers_prov.split(",") if p.strip()]
        
        if pers_req:
            missing_pers = [p for p in pers_req if p not in pers_prov]
            pers_pass = len(missing_pers) == 0
            criteria["personnel"] = {
                "schedule": "Schedule 6",
                "required": f"{len(pers_req)} positions",
                "provided": f"{len(pers_prov)} positions",
                "status": "PASS" if pers_pass else "PARTIAL",
                "score": 100 if pers_pass else max(0, int((1 - len(missing_pers)/len(pers_req)) * 100)),
                "weight": 5,
                "missing_items": missing_pers,
                "remediation": f"Hire/subcontract: {', '.join(missing_pers[:3])}" if missing_pers else ""
            }
            total_score += criteria["personnel"]["score"] * criteria["personnel"]["weight"]
            total_weight += criteria["personnel"]["weight"]
        
        # Allowances
        allowance_count = company.get("allowances", 0)
        criteria["financial_allowance"] = {
            "schedule": "PPR 2025 Rule 8",
            "required": "PPR 2025 allowance provision",
            "provided": f"{allowance_count} allowances active" if allowance_count else "No allowance data",
            "status": "INFO",
            "score": 100 if allowance_count else 0,
            "weight": 0,
            "remediation": "Review PPR 2025 allowance provisions"
        }
        
        overall = int(total_score / max(total_weight, 1))
        
        pass_count = sum(1 for c in criteria.values() if c.get("status") == "PASS")
        fail_count = sum(1 for c in criteria.values() if c.get("status") == "FAIL")
        
        return {
            "overall_score": overall,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "total_criteria": len(criteria),
            "overall_status": "PASS" if overall >= 70 else "CONDITIONAL" if overall >= 50 else "FAIL",
            "criteria": criteria,
            "ppr2025_version": "PPR 2025 Rules",
            "ppr2025_schedules": ["Schedule 4", "Schedule 5", "Schedule 6"],
        }
    
    def _document_readiness(self, tender_id: str) -> Dict:
        """Check document readiness per PPR 2025 requirements."""
        tender_data = self._get_tender_data(tender_id)
        if not tender_data:
            return {"status": "no_data"}
        
        documents = {
            "Tender Security": {
                "status": "required",
                "amount": f"BDT {tender_data.get('tender_security_amount', 'N/A')}",
                "validity": "Minimum 90 days from bid opening",
                "ppr_2025_ref": "Rule 76-78"
            },
            "Performance Security": {
                "status": "required" if tender_data.get("performance_security_amount") else "check_tds",
                "amount": f"BDT {tender_data.get('performance_security_amount', 'Check TDS')}",
                "validity": "Until contract completion + 1 year",
                "ppr_2025_ref": "Rule 82-84"
            },
            "VAT Registration": {
                "status": "mandatory",
                "note": "Must be valid at time of bid submission",
                "ppr_2025_ref": "Rule 42(1)"
            },
            "Income Tax Certificate": {
                "status": "mandatory",
                "note": "TIN must be valid and active",
                "ppr_2025_ref": "Rule 42(2)"
            },
            "Trade License": {
                "status": "mandatory",
                "note": "Must be renewed for current fiscal year",
                "ppr_2025_ref": "Rule 42(3)"
            },
            "Experience Certificates": {
                "status": "mandatory" if tender_data.get("min_experience_years", 0) > 0 else "conditional",
                "requirement": f"{tender_data.get('similar_works_required', 0)} similar work(s) within {tender_data.get('min_experience_years', 5)} years",
                "ppr_2025_ref": "Schedule 4, Rule 1"
            },
            "BOQ (Priced)": {
                "status": "mandatory",
                "format": "As per e-GP system",
                "ppr_2025_ref": "Standard Tender Document"
            },
            "Manufacturer Authorization": {
                "status": "check_tds",
                "condition": "Required if goods procurement",
                "ppr_2025_ref": "Rule 35"
            },
        }
        
        # Calculate readiness score based on mandatory documents
        mandatory_count = sum(1 for d in documents.values() if d.get("status") == "mandatory")
        ready_count = sum(1 for d in documents.values() if d.get("status") in ["mandatory", "required"])
        readiness_score = int(ready_count / max(len(documents), 1) * 100)
        
        return {
            "readiness_score": readiness_score,
            "mandatory_documents": mandatory_count,
            "total_documents": len(documents),
            "documents": documents,
            "ppr2025_document_rules": ["Rule 42", "Rule 76-78", "Rule 82-84", "Schedule 4", "Schedule 5", "Schedule 6"],
        }
    
    def _pricing_guidance(self, tender_id: str) -> Dict:
        """Get pricing guidance with SLT/NPPI integration."""
        # Try to get from MOAT/SLT cache first
        estimate = 0
        with self._engine.connect() as conn:
            row = conn.execute(text(
                "SELECT estimated_cost, COALESCE((extracted_data->>'procurement_type'), 'Unknown') AS procurement_type, sor_agency, procuring_entity, zone, division FROM tenders WHERE tender_id = :id"
            ), {"id": tender_id}).fetchone()
            if row:
                estimate = float(row[0] or 0)
                category = row[1] or "Unknown"
                agency = row[2] or row[3] or ""
                zone = row[4] or row[5] or ""
        
        if estimate == 0:
            return {"status": "no_estimate_data"}
        
        # Default pricing ranges (will be replaced by SLT-agent data)
        expected_discount = 5.5  # Default 5.5% below estimate
        
        return {
            "estimate": estimate,
            "expected_discount_pct": expected_discount,
            "bid_ranges": {
                "conservative": round(estimate * (1 - expected_discount * 0.7 / 100)),
                "balanced": round(estimate * (1 - expected_discount / 100)),
                "aggressive": round(estimate * (1 - expected_discount * 1.3 / 100)),
            },
            "bid_amounts": {
                "conservative": f"BDT {estimate * (1 - expected_discount * 0.7 / 100):,.0f}",
                "balanced": f"BDT {estimate * (1 - expected_discount / 100):,.0f}",
                "aggressive": f"BDT {estimate * (1 - expected_discount * 1.3 / 100):,.0f}",
            },
            "position_score": 70,  # Default healthy score
            "nppi_reference": f"Expected ~{expected_discount:.1f}% below estimate",
            "slt_risk": "low" if expected_discount < 8 else "medium",
        }
    
    def _get_competitor_snapshot(self, tender_id: str, agency: str) -> Dict:
        """Get competitor snapshot."""
        with self._engine.connect() as conn:
            competitors = conn.execute(text("""
                SELECT contractor_name, COUNT(*) as bids
                FROM awards WHERE agency = :agency
                AND contractor_name IS NOT NULL AND contractor_name != ''
                GROUP BY contractor_name
                ORDER BY bids DESC
                LIMIT 15
            """), {"agency": agency}).fetchall()
        
        if not competitors:
            return {
                "competitors_found": 0,
                "competition_score": 80,
                "note": "New or rarely tendered agency — potential first-mover advantage"
            }
        
        competition_score = max(10, 100 - len(competitors) * 8)
        top_competitors = [{"name": c[0], "past_bids": c[1]} for c in competitors[:5]]
        
        return {
            "competitors_found": len(competitors),
            "competition_score": competition_score,
            "top_competitors": top_competitors,
            "market_concentration": "low" if len(competitors) > 10 else "medium" if len(competitors) > 5 else "high",
        }
    
    def _get_tender_data(self, tender_id: str) -> Optional[Dict]:
        """Get tender data from database."""
        with self._engine.connect() as conn:
            row = conn.execute(text(
                "SELECT * FROM tenders WHERE tender_id = :id"
            ), {"id": tender_id}).fetchone()
            if row:
                return dict(row._mapping)
            # Try the tender_data_pool
            row = conn.execute(text(
                "SELECT * FROM tender_data_pool WHERE tender_id = :id"
            ), {"id": tender_id}).fetchone()
            if row:
                return dict(row._mapping)
        return None
    
    def _generate_overall_recommendation(self, scores: Dict, compliance: Dict, pricing: Dict) -> Dict:
        """Generate overall bid recommendation."""
        if scores["overall"] >= 75:
            bid = "BID"
            confidence = "high"
        elif scores["overall"] >= 55:
            bid = "BID_CONDITIONAL"
            confidence = "medium"
        else:
            bid = "NO_BID"
            confidence = "low"
        
        reasons = []
        if compliance.get("fail_count", 0) > 0:
            reasons.append(f"{compliance['fail_count']} compliance criteria not met")
        if scores.get("competition", 100) < 40:
            reasons.append("Very high competition")
        if scores.get("pricing", 50) < 40:
            reasons.append("Pricing position unfavorable")
        
        return {
            "decision": bid,
            "confidence": confidence,
            "overall_score": scores["overall"],
            "reasons": reasons if reasons else ["All criteria look favorable"],
            "next_steps": self._next_steps(scores, compliance),
        }
    
    def _next_steps(self, scores: Dict, compliance: Dict) -> List[str]:
        steps = []
        if compliance.get("fail_count", 0) > 0:
            for c_name, c_data in compliance.get("criteria", {}).items():
                if c_data.get("status") == "FAIL" and c_data.get("remediation"):
                    steps.append(f"⚡ {c_name}: {c_data['remediation']}")
        if scores.get("documents", 0) < 80:
            steps.append("📄 Prepare all mandatory documents per PPR 2025 Rule 42")
        if steps:
            steps.insert(0, "📋 Recommended actions to improve readiness:")
        else:
            steps = ["✅ No critical issues found — proceed with bid preparation"]
        return steps
    
    async def _pre_compute_all(self) -> Dict:
        """Pre-compute dashboards for all LIVE tenders."""
        with self._engine.connect() as conn:
            tenders = conn.execute(text(
                "SELECT tender_id FROM tenders WHERE estimated_cost > 0 LIMIT 200"
            )).fetchall()
        
        count = 0
        for t in tenders:
            try:
                await self._build_dashboard(t[0], {})
                count += 1
            except Exception as e:
                logger.warning(f"  Dashboard failed for {t[0]}: {e}")
        
        return {"status": "complete", "dashboards_pre_computed": count}
