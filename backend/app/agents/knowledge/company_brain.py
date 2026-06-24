"""
Agent 40 — Company Brain Agent
Phase 3: Contractor Operating System

Merges private contractor data with public procurement intelligence.
Produces strategic insights, partnership recommendations.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from decimal import Decimal
from sqlalchemy import select, or_

from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from app.db.database import get_session

logger = logging.getLogger(__name__)


class CompanyBrainAgent(BaseAgent):
    agent_id = "agent-040-company-brain"
    agent_name = "Company Brain Agent"
    description = "Phase 3: Merges private company data with market intelligence for strategic insights."
    dependencies = ["agent-014-award-intelligence", "agent-016-win-probability", "agent-038-tender-pre-screener"]
    version = "1.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        action = context.get("action", "analyze")
        company_raw = context.get("company_profile", context.get("company", {}))
        company = company_raw if isinstance(company_raw, dict) else {"name": str(company_raw)}
        tender_id = context.get("tender_id", "")

        if action == "analyze":
            result = await self._full_analysis(company)
        elif action == "partnership":
            result = await self._partnership_recommendations(company)
        elif action == "gap_analysis":
            result = await self._gap_analysis(company, context)
        elif action == "capacity_check":
            result = await self._capacity_check(company, context)
        else:
            result = await self._full_analysis(company)

        await self.share_knowledge(entry_type="company_brain", tender_id=tender_id or "COMPANY",
            data=result, summary=f"Company Brain: {result.get('strategic_summary', '')}",
            tags=["company-brain", "phase3"])
        return AgentResult(status=AgentStatus.SUCCESS, output=result)

    async def _load_db_profile(self, name: str) -> Optional[Dict]:
        """Load contractor profile from the intelligence database."""
        try:
            from app.models.intelligence import Contractor, ContractorDNA
            async with get_session() as db:
                result = await db.execute(
                    select(Contractor, ContractorDNA)
                    .join(ContractorDNA, ContractorDNA.contractor_id == Contractor.id, isouter=True)
                    .where(or_(
                        Contractor.contractor_name.ilike(name),
                        Contractor.contractor_name.ilike(f"%{name}%"),
                    ))
                    .limit(1)
                )
                row = result.first()
                if row:
                    c, dna = row
                    profile = {
                        "name": c.contractor_name,
                        "total_contracts": c.total_contracts,
                        "total_amount_bdt": c.total_amount_bdt,
                        "agencies": c.agencies_worked or [],
                        "zones": c.districts_worked or [],
                        "avg_npp": c.avg_npp,
                        "first_award": str(c.first_award_date or ""),
                        "last_award": str(c.last_award_date or ""),
                    }
                    if dna:
                        profile.update({
                            "health_score": dna.health_score,
                            "win_rate": dna.win_rate,
                            "avg_discount_pct": dna.avg_discount_pct,
                            "completion_rate": dna.completion_rate,
                            "on_time_rate": dna.on_time_rate,
                            "avg_delay_days": dna.avg_delay_days,
                            "npp_volatility": dna.npp_volatility,
                            "experience_contracts": dna.total_experience_contracts,
                            "experience_value_bdt": dna.total_experience_value_bdt,
                        })
                    return profile
        except Exception as e:
            logger.warning(f"Could not load DB profile for {name}: {e}")
        return None

    async def _full_analysis(self, company: Dict) -> Dict:
        name = company.get("company_name", company.get("name", "Unknown"))
        db_profile = await self._load_db_profile(name)

        agencies = company.get("target_agencies", company.get("preferred_agencies", []))
        zones = company.get("target_zones", company.get("preferred_zones", []))
        manpower = company.get("manpower", company.get("total_manpower", 0))
        equipment = company.get("equipment", [])
        years = company.get("experience_years", company.get("years_in_business", 5))

        if db_profile:
            if not agencies and db_profile.get("agencies"):
                agencies = db_profile["agencies"]
            if not zones and db_profile.get("zones"):
                zones = db_profile["zones"]
            years = years or 5
            summary_parts = [f"{db_profile['name']}: {years}yr"]
            if db_profile.get("total_contracts"):
                summary_parts.append(f"{db_profile['total_contracts']} awards")
            if db_profile.get("total_amount_bdt"):
                summary_parts.append(f"BDT {db_profile['total_amount_bdt']:,.0f}")
            if db_profile.get("health_score", 0) > 0:
                summary_parts.append(f"health {db_profile['health_score']}")
            strategic_summary = " | ".join(summary_parts)
        else:
            strategic_summary = f"{name}: {years}yr, {manpower} staff, {len(equipment)} equipment types"

        return {
            "company": name,
            "strategic_summary": strategic_summary,
            "db_profile_found": db_profile is not None,
            "strengths": self._identify_strengths(company, db_profile),
            "weaknesses": self._identify_weaknesses(company, db_profile),
            "capacity_utilization": self._estimate_capacity_usage(company, db_profile),
            "recommended_strategy": self._recommend_strategy(company, agencies, zones, db_profile),
            "partnership_opportunities": [],
            "agency_focus": [{"agency": a, "strategy": self._agency_strategy(a, db_profile)} for a in agencies],
            "zone_focus": [{"zone": z, "priority": "High" if z in ["Dhaka"] else "Medium"} for z in zones]
        }

    async def _partnership_recommendations(self, company: Dict) -> Dict:
        name = company.get("company_name", "Unknown")
        agencies = company.get("target_agencies", [])
        db_profile = await self._load_db_profile(name)
        recs = []
        if db_profile:
            if db_profile.get("total_amount_bdt", 0) < 50000000:
                recs.append({"partner_type": "Financial partner", "reason": "Low total award value, needs capital", "urgency": "High"})
            if db_profile.get("avg_delay_days", 0) > 30:
                recs.append({"partner_type": "Technical partner", "reason": "History of delays, needs execution support", "urgency": "Medium"})
            if len(db_profile.get("agencies", [])) < 3:
                recs.append({"partner_type": "Market expansion partner", "reason": "Limited agency exposure", "urgency": "Low"})
        return {
            "company": name,
            "jv_recommendations": recs or [
                {"partner_type": "Financial partner", "reason": "Larger tenders >5Cr", "urgency": "Medium"},
                {"partner_type": "Technical partner", "reason": "Specialized works", "urgency": "Low"}
            ],
            "subcontracting_opportunities": [
                {"type": "Earthwork", "agencies": agencies},
                {"type": "Concrete works", "agencies": agencies}
            ]
        }

    async def _gap_analysis(self, company: Dict, context: Dict) -> Dict:
        name = company.get("company_name", "Unknown")
        db_profile = await self._load_db_profile(name)
        gaps = []
        if db_profile:
            if db_profile.get("health_score", 0) < 0.5:
                gaps.append("Low overall health score")
            if db_profile.get("completion_rate", 100) < 70:
                gaps.append(f"Low completion rate ({db_profile['completion_rate']}%)")
            if db_profile.get("on_time_rate", 100) < 60:
                gaps.append(f"Poor on-time delivery ({db_profile['on_time_rate']}%)")
            if db_profile.get("avg_npp", 0) > 0.15:
                gaps.append("High NPP ratio (low discounting)")
            if not db_profile.get("experience_contracts"):
                gaps.append("No eExperience execution history")
        return {"gaps": gaps, "missing_capabilities": [], "training_needs": []}

    async def _capacity_check(self, company: Dict, context: Dict) -> Dict:
        name = company.get("company_name", "Unknown")
        db_profile = await self._load_db_profile(name)
        if db_profile:
            active = db_profile.get("total_contracts", 0)
            max_cap = max(1, active * 2)
            utilization = min(100, round((active / max_cap) * 100))
            return {"can_handle": utilization < 80, "max_additional_projects": max(1, max_cap - active), "current_load": f"{utilization}%"}
        return {"can_handle": True, "max_additional_projects": 3, "current_load": "30%"}

    def _identify_strengths(self, c: Dict, db: Optional[Dict] = None) -> List:
        s = []
        if db:
            if db.get("health_score", 0) >= 0.7: s.append(f"High health score ({db['health_score']})")
            if db.get("completion_rate", 0) >= 90: s.append(f"Excellent completion rate ({db['completion_rate']}%)")
            if db.get("on_time_rate", 0) >= 80: s.append(f"Strong on-time delivery ({db['on_time_rate']}%)")
            if db.get("total_amount_bdt", 0) > 50000000: s.append(f"Large portfolio (BDT {db['total_amount_bdt']:,.0f})")
            if len(db.get("agencies", [])) >= 5: s.append(f"Multi-agency experience ({len(db['agencies'])} agencies)")
        if c.get("experience_years", 0) > 10: s.append(f"{c['experience_years']}+ years experience")
        if c.get("manpower", 0) > 50: s.append(f"Large workforce ({c['manpower']} staff)")
        if c.get("equipment"): s.append("Own equipment fleet")
        return s

    def _identify_weaknesses(self, c: Dict, db: Optional[Dict] = None) -> List:
        w = []
        if db:
            if db.get("health_score", 1) < 0.4: w.append(f"Low health score ({db['health_score']})")
            if db.get("completion_rate", 100) < 70: w.append(f"Low completion rate ({db['completion_rate']}%)")
            if db.get("avg_delay_days", 0) > 60: w.append(f"Significant delays (avg {db['avg_delay_days']} days)")
            if not db.get("experience_contracts"): w.append("No eExperience execution history")
        if not c.get("recent_awards"): w.append("No recent awards data")
        if not c.get("financial_capacity", {}).get("turnover_history"): w.append("No turnover history recorded")
        return w

    def _estimate_capacity_usage(self, c: Dict, db: Optional[Dict] = None) -> Dict:
        if db:
            active = db.get("total_contracts", 0)
            util = min(100, active * 5)
            return {"current": "High" if util > 70 else "Medium" if util > 30 else "Low", "available": "Low" if util > 70 else "Medium" if util > 30 else "High", "utilization_pct": util}
        return {"current": "Low", "available": "High", "utilization_pct": 30}

    def _recommend_strategy(self, c: Dict, agencies: List, zones: List, db: Optional[Dict] = None) -> str:
        if db and db.get("preferred_agency"):
            return f"Leverage {db['preferred_agency']} relationship; expand to complementary agencies"
        if "BWDB" in agencies:
            return "Focus on BWDB water resources works"
        return "Develop agency relationships in target zones"

    def _agency_strategy(self, agency: str, db: Optional[Dict] = None) -> str:
        if db and agency in db.get("agencies", []):
            return "Maintain"
        return "Develop"
