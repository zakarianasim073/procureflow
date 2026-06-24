"""
Agent 16 — Win Probability Agent
Predicts chance of winning through historical, competitor, and client analysis using a weighted algorithm.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List

from .base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class WinProbabilityAgent(BaseAgent):
    agent_id = "agent-016-win-probability"
    agent_name = "Win Probability Agent"
    description = "Predicts overall win probability through historical analysis, competitor comparison, and client relationship scoring."
    dependencies: List[str] = ["agent-013-competitor-intelligence", "agent-014-award-intelligence"]
    version = "2.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        company = context.get("company_profile", {})
        tender = context.get("tender_info", {})
        upstream = context.get("upstream", {})

        probability = await self._calculate_probability(company, tender, context, upstream)

        output = {
            "win_probability": probability["probability"],
            "confidence": probability["confidence"],
            "factors": probability["factors"],
            "recommendations": probability["recommendations"],
        }

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=output,
        )

    async def _calculate_probability(
        self, company: Dict, tender: Dict, context: Dict, upstream: Dict
    ) -> Dict:
        """Calculate win probability using multiple weighted factors."""
        factors = []
        total_weight = 0
        weighted_score = 0

        # Factor 1: Historical relationship with procuring entity (weight: 25)
        entity = tender.get("procuring_entity", "")
        past_wins = context.get("past_wins_with_entity", 0)
        if past_wins > 0:
            score = min(past_wins * 15, 85)
            factors.append({
                "name": "Past Relationship",
                "score": score,
                "weight": 25,
                "detail": f"{past_wins} previous wins with {entity}",
            })
            weighted_score += score * 25
        else:
            factors.append({
                "name": "Past Relationship",
                "score": 30,
                "weight": 25,
                "detail": f"No previous wins with {entity} — neutral",
            })
            weighted_score += 30 * 25
        total_weight += 25

        # Factor 2: Competitor analysis (weight: 25)
        competitors_data = upstream.get("agent-013-competitor-intelligence", {})
        competitors = competitors_data.get("competitors", [])
        num_competitors = len(competitors) or 5
        if num_competitors <= 3:
            comp_score = 75
            detail = f"Low competition ({num_competitors} competitors)"
        elif num_competitors <= 7:
            comp_score = 55
            detail = f"Moderate competition ({num_competitors} competitors)"
        else:
            comp_score = 35
            detail = f"High competition ({num_competitors} competitors)"
        
        factors.append({
            "name": "Competition Level",
            "score": comp_score,
            "weight": 25,
            "detail": detail,
        })
        weighted_score += comp_score * 25
        total_weight += 25

        # Factor 3: Bid discount position (weight: 20)
        our_discount = context.get("our_discount_percent", 5.0)
        avg_market_discount = competitors_data.get("market_insights", {}).get("avg_market_discount", 5.0)
        
        if our_discount <= avg_market_discount * 0.8:
            discount_score = 70
            detail = f"Aggressive discount ({our_discount}% vs market avg {avg_market_discount}%)"
        elif our_discount <= avg_market_discount * 1.2:
            discount_score = 50
            detail = f"Competitive discount ({our_discount}% vs market avg {avg_market_discount}%)"
        else:
            discount_score = 30
            detail = f"Conservative discount ({our_discount}% vs market avg {avg_market_discount}%)"
        
        factors.append({
            "name": "Discount Position",
            "score": discount_score,
            "weight": 20,
            "detail": detail,
        })
        weighted_score += discount_score * 20
        total_weight += 20

        # Factor 4: Experience match (weight: 15)
        company_experience = company.get("years_in_business", 5)
        tender_complexity = tender.get("complexity", "medium")
        complexity_map = {"low": 3, "medium": 5, "high": 8}
        
        exp_gap = company_experience - complexity_map.get(tender_complexity, 5)
        if exp_gap >= 5:
            exp_score = 85
            detail = f"Extensive experience ({company_experience}+ years)"
        elif exp_gap >= 0:
            exp_score = 65
            detail = f"Adequate experience ({company_experience} years)"
        else:
            exp_score = 40
            detail = f"Limited experience ({company_experience} years) for complex tender"
        
        factors.append({
            "name": "Experience Match",
            "score": exp_score,
            "weight": 15,
            "detail": detail,
        })
        weighted_score += exp_score * 15
        total_weight += 15

        # Factor 5: Financial capacity (weight: 15)
        tender_value = tender.get("estimated_value", 50_000_000)
        company_capacity = company.get("annual_turnover", 500_000_000)
        
        if company_capacity >= tender_value * 5:
            fin_score = 80
            detail = "Strong financial capacity"
        elif company_capacity >= tender_value * 2:
            fin_score = 60
            detail = "Adequate financial capacity"
        else:
            fin_score = 35
            detail = "Financial capacity below comfort level"
        
        factors.append({
            "name": "Financial Capacity",
            "score": fin_score,
            "weight": 15,
            "detail": detail,
        })
        weighted_score += fin_score * 15
        total_weight += 15

        # Calculate final probability
        final_probability = round(weighted_score / total_weight if total_weight > 0 else 50, 1)
        
        # Confidence level
        if total_weight >= 80:
            confidence = "High" if final_probability > 70 else "Medium"
        else:
            confidence = "Low"

        # Recommendations
        recommendations = []
        if final_probability < 50:
            recommendations.append("Consider adjusting discount rate to be more competitive")
        if entity and past_wins == 0:
            recommendations.append(f"Build relationship with {entity} through smaller contracts first")
        if num_competitors > 7:
            recommendations.append("Focus on differentiating your bid through quality and experience")
        if company_capacity < tender_value * 2:
            recommendations.append("Consider forming a Joint Venture to strengthen financial capacity")

        return {
            "probability": round(final_probability, 1),
            "confidence": confidence,
            "factors": factors,
            "recommendations": recommendations,
        }
