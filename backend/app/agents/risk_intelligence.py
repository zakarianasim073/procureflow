"""
Agent 8 — Risk Intelligence Agent
Identifies contractual risks: LD analysis, guarantee analysis, retention, insurance.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .base import BaseAgent, AgentResult, AgentStatus
from .schemas import RiskProfile

logger = logging.getLogger(__name__)


class RiskIntelligenceAgent(BaseAgent):
    agent_id = "agent-008-risk-intelligence"
    agent_name = "Risk Intelligence Agent"
    description = "Analyzes contractual risks including liquidated damages, guarantees, retentions, and insurance requirements."
    dependencies: List[str] = ["agent-004-document-ai"]
    version = "1.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        tender_profile = context.get("upstream", {}).get("agent-004-document-ai", {})

        risk = await self._analyze_risks(tender_profile)

        output = {
            "risk_level": risk.risk_level,
            "ld_analysis": {
                "rate": risk.ld_rate,
                "assessment": risk.ld_risk,
            },
            "guarantee_analysis": {
                "required": risk.guarantee_required,
                "assessment": risk.guarantee_risk,
            },
            "retention_analysis": {
                "percent": risk.retention_percent,
                "assessment": risk.retention_risk,
            },
            "insurance_requirements": risk.insurance_requirements,
            "risk_factors": risk.risk_factors,
        }

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=output,
        )

    async def _analyze_risks(self, profile: Dict) -> RiskProfile:
        risk = RiskProfile()
        emd = profile.get("emd_amount", 500_000)
        est_value = profile.get("estimated_value", 52_000_000)

        # LD Analysis
        risk.ld_rate = 0.001  # 0.1% per day
        risk.ld_risk = "Moderate — Standard LD rate of 0.1% per day applies"

        # Guarantee
        risk.guarantee_required = emd
        risk.guarantee_risk = f"Performance Guarantee at standard rate"

        # Retention
        risk.retention_percent = 5.0
        risk.retention_risk = f"5% retention on interim payments"

        # Insurance
        risk.insurance_requirements = [
            "CAR Insurance (Contractor's All Risk)",
            "Third Party Liability Insurance",
            "Workmen's Compensation Insurance",
        ]

        # Overall risk assessment
        risk.risk_factors = [
            f"EMD of ৳{emd:,.0f}",
            f"LD rate: {risk.ld_rate*100}%/day",
            f"Retention: {risk.retention_percent}%",
        ]

        # Determine risk level
        risk.risk_level = "Medium"
        if est_value > 100_000_000 or emd > 1_000_000:
            risk.risk_level = "High"

        return risk
