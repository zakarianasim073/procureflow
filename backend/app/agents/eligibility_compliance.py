"""
Agent 7 — Eligibility & Compliance Agent
Checks qualification requirements: experience, turnover, equipment, personnel, licenses.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .base import BaseAgent, AgentResult, AgentStatus
from .schemas import EligibilityCriteria

logger = logging.getLogger(__name__)


class EligibilityComplianceAgent(BaseAgent):
    agent_id = "agent-007-eligibility-compliance"
    agent_name = "Eligibility & Compliance Agent"
    description = "Checks all qualification criteria including experience, turnover, equipment, personnel, and licenses."
    dependencies: List[str] = ["agent-004-document-ai", "agent-006-spec-intelligence"]
    version = "1.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        company_profile = context.get("company_profile", {})
        tender_requirements = context.get("upstream", {}).get("agent-004-document-ai", {})

        criteria = await self._check_eligibility(company_profile, tender_requirements)

        output = {
            "compliant": criteria.compliant,
            "checks": {
                "experience_met": criteria.experience_met,
                "turnover_met": criteria.turnover_met,
                "equipment_met": criteria.equipment_met,
                "personnel_met": criteria.personnel_met,
                "licenses_met": criteria.licenses_met,
            },
            "missing_items": criteria.missing_items,
            "notes": criteria.notes,
        }

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=output,
        )

    async def _check_eligibility(self, company: Dict, requirements: Dict) -> EligibilityCriteria:
        criteria = EligibilityCriteria()

        # Experience check
        company_exp = company.get("years_experience", 8)
        req_exp = self._parse_experience(requirements.get("experience_required", "10 years"))
        criteria.experience_met = company_exp >= req_exp

        # Turnover check
        company_turnover = company.get("avg_turnover", 80_000_000)
        req_turnover = requirements.get("turnover_required", 50_000_000)
        criteria.turnover_met = company_turnover >= req_turnover

        # Equipment check
        company_equipment = set(company.get("equipment", ["Excavator", "Paver", "Roller"]))
        required_equipment = {"Excavator", "Paver", "Roller", "Concrete Mixer"}
        missing_eq = required_equipment - company_equipment
        criteria.equipment_met = len(missing_eq) == 0

        # Personnel check
        company_engineers = company.get("engineers_count", 15)
        criteria.personnel_met = company_engineers >= 5

        # Licenses check
        company_licenses = set(company.get("licenses", ["LGED", "RHD", "PWD"]))
        criteria.licenses_met = len(company_licenses) >= 1

        # Aggregate
        criteria.compliant = all([
            criteria.experience_met, criteria.turnover_met,
            criteria.equipment_met, criteria.personnel_met,
            criteria.licenses_met,
        ])

        if missing_eq:
            criteria.missing_items.append(f"Missing equipment: {', '.join(missing_eq)}")
        if not criteria.experience_met:
            criteria.missing_items.append(f"Need {req_exp} years experience, have {company_exp}")
        if not criteria.turnover_met:
            criteria.missing_items.append(f"Need ৳{req_turnover:,.0f} turnover, have ৳{company_turnover:,.0f}")

        criteria.notes = "All criteria met" if criteria.compliant else "Some criteria not met"
        return criteria

    def _parse_experience(self, exp_str: str) -> int:
        import re
        match = re.search(r'(\d+)', str(exp_str))
        return int(match.group(1)) if match else 5
