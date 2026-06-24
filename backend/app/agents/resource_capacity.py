"""
Agent 19 — Resource Capacity Agent
Analyzes company capacity to execute the tender based on current workload, resources, and timeline.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, date

from .base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class ResourceCapacityAgent(BaseAgent):
    agent_id = "agent-019-resource-capacity"
    agent_name = "Resource Capacity Agent"
    description = "Analyzes organizational capacity to execute the tender based on current workload, personnel, equipment, and timeline."
    dependencies: List[str] = []
    version = "2.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        company = context.get("company_profile", {})
        tender = context.get("tender_info", {})

        capacity = await self._analyze_capacity(company, tender)

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=capacity,
        )

    async def _analyze_capacity(self, company: Dict, tender: Dict) -> Dict:
        """Analyze resource capacity for tender execution."""
        # Current resources
        total_staff = company.get("total_staff", 50)
        technical_staff = company.get("technical_staff", 20)
        field_crews = company.get("field_crews", 3)
        major_equipment = company.get("major_equipment", 10)
        
        # Current workload
        active_projects = company.get("active_projects", 2)
        total_contract_value_active = company.get("total_contract_value_active", 200_000_000)
        
        # Tender requirements
        project_duration = tender.get("contract_period_days", 365)
        tender_value = tender.get("estimated_value", 50_000_000)
        
        # Personnel analysis
        staff_per_project = max(technical_staff / max(active_projects + 1, 1), 2)
        required_staff = max(int(tender_value / 10_000_000 * 3), 5)
        staff_adequacy = (staff_per_project / max(required_staff, 1)) * 100
        
        # Equipment utilization
        equipment_per_project = max(major_equipment / max(active_projects + 1, 1), 1)
        required_equipment = max(int(tender_value / 20_000_000 * 2), 2)
        equipment_adequacy = (equipment_per_project / max(required_equipment, 1)) * 100
        
        # Timeline analysis
        if project_duration <= 180:
            timeline_risk = "HIGH"
            timeline_score = 30
        elif project_duration <= 365:
            timeline_risk = "MEDIUM"
            timeline_score = 55
        else:
            timeline_risk = "LOW"
            timeline_score = 80

        # Overall capacity score
        capacity_score = round(
            staff_adequacy * 0.35 +
            equipment_adequacy * 0.25 +
            timeline_score * 0.25 +
            (100 - min(active_projects * 10, 50)) * 0.15
        , 1)

        # Recommendations
        recommendations = []
        if capacity_score < 50:
            recommendations.append("Staff or equipment shortage — consider hiring or leasing")
            recommendations.append("Subcontract non-core activities to manage workload")
        if timeline_risk == "HIGH":
            recommendations.append("Tight timeline — accelerate mobilization planning")
        if active_projects >= 3:
            recommendations.append("High project load — evaluate impact on existing commitments")

        return {
            "capacity_score": capacity_score,
            "personnel_analysis": {
                "total_staff": total_staff,
                "technical_staff": technical_staff,
                "available_per_project": round(staff_per_project, 1),
                "required_for_tender": required_staff,
                "adequacy_pct": round(staff_adequacy, 1),
            },
            "equipment_analysis": {
                "major_equipment": major_equipment,
                "available_per_project": round(equipment_per_project, 1),
                "required_for_tender": required_equipment,
                "adequacy_pct": round(equipment_adequacy, 1),
            },
            "workload_analysis": {
                "active_projects": active_projects,
                "total_active_value": total_contract_value_active,
                "project_duration_days": project_duration,
                "timeline_risk": timeline_risk,
            },
            "recommendations": recommendations,
        }
