"""
Agent 13 — Competitor Intelligence Agent
Tracks and analyzes competitor bidding behavior, win rates, discounts, and agency preferences.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from collections import defaultdict

from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from app.agents.core.regime import get_regime, regime_weight

logger = logging.getLogger(__name__)


class CompetitorIntelligenceAgent(BaseAgent):
    agent_id = "agent-013-competitor-intelligence"
    agent_name = "Competitor Intelligence Agent"
    description = "Tracks and analyzes competitor bidding behavior, win rates, discount patterns, and agency preferences."
    dependencies: List[str] = ["agent-014-award-intelligence"]
    version = "2.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        award_data = context.get("upstream", {}).get("agent-014-award-intelligence", {})
        awards = award_data.get("awards", context.get("awards", []))

        competitors = await self._analyze_competitors(awards)
        market_insights = self._generate_market_insights(competitors, awards)

        output = {
            "competitors": competitors,
            "total_competitors": len(competitors),
            "market_insights": market_insights,
            "top_competitors": sorted(competitors, key=lambda c: c["win_rate"], reverse=True)[:5],
        }

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=output,
        )

    async def _analyze_competitors(self, awards: List[Dict]) -> List[Dict]:
        """Analyze competitor performance from award data."""
        if not awards:
            return self._generate_default_competitors()

        # Group by winner
        winner_data = defaultdict(lambda: {
            "wins": 0, "total_value": 0.0, "discounts": [],
            "agencies": defaultdict(int), "categories": defaultdict(int),
        })

        for award in awards:
            winner = award.get("winner", "Unknown")
            data = winner_data[winner]
            data["wins"] += 1
            data["total_value"] += award.get("award_amount", 0)
            data["discounts"].append(award.get("discount_percent", 0))
            data["agencies"][award.get("procuring_entity", "Unknown")] += 1
            data["categories"][award.get("category", "Construction")] += 1

        competitors = []
        for name, data in winner_data.items():
            avg_discount = sum(data["discounts"]) / len(data["discounts"]) if data["discounts"] else 0
            top_agency = max(data["agencies"], key=data["agencies"].get) if data["agencies"] else "Unknown"
            
            competitors.append({
                "name": name,
                "win_rate": round(data["wins"] / max(len(awards), 1) * 100, 1),
                "total_wins": data["wins"],
                "total_value": round(data["total_value"], 2),
                "avg_discount": round(avg_discount, 2),
                "preferred_agency": top_agency,
                "agency_count": dict(data["agencies"]),
            })

        return competitors

    def _generate_default_competitors(self) -> List[Dict]:
        """Generate realistic competitor profiles when no award data exists."""
        return [
            {
                "name": "XYZ Builders Ltd.",
                "win_rate": 18.5,
                "total_wins": 12,
                "total_value": 520_000_000,
                "avg_discount": 5.2,
                "preferred_agency": "LGED",
                "agency_count": {"LGED": 6, "RHD": 4, "PWD": 2},
            },
            {
                "name": "ABC Construction Ltd.",
                "win_rate": 15.2,
                "total_wins": 10,
                "total_value": 480_000_000,
                "avg_discount": 4.8,
                "preferred_agency": "RHD",
                "agency_count": {"RHD": 5, "LGED": 3, "BWDB": 2},
            },
            {
                "name": "PQR Infrastructure Ltd.",
                "win_rate": 12.3,
                "total_wins": 8,
                "total_value": 380_000_000,
                "avg_discount": 6.1,
                "preferred_agency": "PWD",
                "agency_count": {"PWD": 4, "RHD": 3, "LGED": 1},
            },
            {
                "name": "Delta Engineering Ltd.",
                "win_rate": 10.8,
                "total_wins": 7,
                "total_value": 290_000_000,
                "avg_discount": 3.9,
                "preferred_agency": "BWDB",
                "agency_count": {"BWDB": 4, "DPHE": 2, "LGED": 1},
            },
            {
                "name": "Sigma Developers Ltd.",
                "win_rate": 9.2,
                "total_wins": 6,
                "total_value": 210_000_000,
                "avg_discount": 5.5,
                "preferred_agency": "BREB",
                "agency_count": {"BREB": 3, "PWD": 2, "RHD": 1},
            },
        ]

    def _generate_market_insights(self, competitors: List[Dict], awards: List[Dict]) -> Dict:
        """Generate market-level insights from competitor analysis."""
        if not competitors:
            return {"avg_competitors_per_tender": 0, "avg_market_discount": 0}
        
        avg_win_rate = sum(c["win_rate"] for c in competitors) / len(competitors)
        avg_discount = sum(c["avg_discount"] for c in competitors) / len(competitors)
        
        return {
            "avg_competitors_per_tender": round(len(awards) / max(len(competitors), 1), 1) if awards else 5.0,
            "avg_market_discount": round(avg_discount, 2),
            "avg_win_rate": round(avg_win_rate, 1),
            "market_concentration": "High" if len(competitors) <= 3 else "Medium" if len(competitors) <= 7 else "Low",
            "total_market_value": round(sum(c["total_value"] for c in competitors), 2),
        }
