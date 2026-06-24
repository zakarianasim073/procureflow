"""
Agent 17 — Bid Position Optimizer v2
Phase 2: Decision Intelligence Engine

Produces 3 strategic ranges: Conservative | Balanced | Aggressive
Each with expected margin, win probability, and risk assessment.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from decimal import Decimal

from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from app.agents.core.regime import get_regime, regime_weight
from app.db.database import get_sync_engine
from sqlalchemy import text

logger = logging.getLogger(__name__)


class BidPositionOptimizerAgent(BaseAgent):
    agent_id = "agent-017-bid-position-optimizer"
    agent_name = "Bid Position Optimizer v2"
    description = "Phase 2 Decision Engine: Conservative/Balanced/Aggressive bid ranges with margin optimization."
    dependencies = ["agent-011-rate-analysis", "agent-013-competitor-intelligence", "agent-016-win-probability"]
    version = "2.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        tender_id = context.get("tender_id", "")
        estimate = context.get("estimate", context.get("estimated_amount", context.get("estimated_value", 0)))
        agency = context.get("agency", "")
        zone = context.get("zone", context.get("division", ""))
        company = context.get("company_profile", context.get("company", {}))
        risk_appetite = company.get("risk_appetite", "moderate")
        margin_target = company.get("margin_target", context.get("margin_target", "12"))

        # Get market intelligence
        market = await self._get_market_intelligence(agency, zone)
        competitor_count = market.get("avg_competitors", 5)
        avg_discount = market.get("avg_discount", 5.5)

        # Generate 3 strategic ranges
        ranges = self._compute_ranges(estimate, avg_discount, competitor_count, risk_appetite, float(margin_target))

        # Get current win probability for each range
        for r in ranges:
            wp = await self._estimate_win_prob(r["discount_pct"], avg_discount, competitor_count)
            r["win_probability"] = wp

        result = {
            "tender_id": tender_id,
            "estimate": float(estimate),
            "market_context": {
                "avg_discount": avg_discount,
                "avg_competitors": competitor_count,
                "competition_level": "Low" if competitor_count <= 3 else "Medium" if competitor_count <= 7 else "High"
            },
            "ranges": ranges,
            "recommendation": self._pick_optimal(ranges, risk_appetite),
            "version": "v2.0"
        }

        await self.share_knowledge(
            entry_type="bid_position", tender_id=tender_id, data=result,
            summary=f"Bid ranges: C={ranges[0]['discount_pct']}% B={ranges[1]['discount_pct']}% A={ranges[2]['discount_pct']}%",
            tags=["bid-position", "v2", agency]
        )

        return AgentResult(agent_id=self.agent_id, agent_name=self.agent_name,
                          status=AgentStatus.SUCCESS, output=result)

    async def _get_market_intelligence(self, agency: str, zone: str) -> Dict:
        result = {"avg_discount": 5.5, "avg_competitors": 5}
        try:
            engine = get_sync_engine()
            with engine.connect() as conn:
                if agency:
                    discount_row = conn.execute(text(
                        "SELECT AVG(lowest_percent_below_oe) FROM npp_records WHERE agency = :agency LIMIT 10"
                    ), {"agency": agency}).fetchone()
                    if discount_row and discount_row[0]:
                        result["avg_discount"] = float(discount_row[0])

                    comp_row = conn.execute(text(
                        "SELECT AVG(json_array_length(bidders)) FROM opening_reports "
                        "WHERE pe_office LIKE :agency AND bidders IS NOT NULL LIMIT 20"
                    ), {"agency": f"%{agency}%"}).fetchone()
                    if comp_row and comp_row[0]:
                        result["avg_competitors"] = float(comp_row[0])
        except Exception as e:
            logger.warning(f"Market intelligence error: {e}")
        return result

    def _compute_ranges(self, estimate: float, avg_discount: float, comp_count: int,
                        risk: str, margin_target: float) -> List[Dict]:
        """Conservative / Balanced / Aggressive ranges."""
        if not estimate or estimate <= 0:
            estimate = 50000000

        # Base discount around NPPI
        comp_factor = 1.0 + (comp_count - 5) * 0.05  # More competitors = slightly more discount

        ranges = []
        configs = [
            ("Conservative", 0.6, 0.05, margin_target * 1.3),
            ("Balanced", 1.0, 0.08, margin_target * 1.0),
            ("Aggressive", 1.4, 0.12, margin_target * 0.7),
        ]

        ranges = []
        for name, multiplier, risk_premium, expected_margin in configs:
            discount_pct = round(avg_discount * comp_factor * multiplier, 2)
            bid_amount = round(estimate * (1 - discount_pct / 100), 2)
            margin = round(expected_margin - discount_pct + avg_discount * 0.5, 1)

            ranges.append({
                "strategy": name,
                "discount_pct": discount_pct,
                "bid_amount": bid_amount,
                "estimated_margin_pct": max(3, margin),
                "bid_to_estimate_pct": round((1 - discount_pct / 100) * 100, 1),
                "risk_level": "LOW" if name == "Conservative" else "MEDIUM" if name == "Balanced" else "HIGH",
                "recommended_for": self._risk_recommendation(name, risk)
            })

        return ranges

    def _risk_recommendation(self, strategy: str, risk_appetite: str) -> str:
        mapping = {
            "Conservative": {"conservative": "Preferred", "moderate": "Alternative", "aggressive": "Last resort"},
            "Balanced": {"conservative": "Alternative", "moderate": "Preferred", "aggressive": "Alternative"},
            "Aggressive": {"conservative": "Avoid", "moderate": "Alternative", "aggressive": "Preferred"},
        }
        return mapping.get(strategy, {}).get(risk_appetite, "Alternative")

    async def _estimate_win_prob(self, discount: float, avg_discount: float, comp_count: int) -> int:
        """Simple win prob estimation based on discount position."""
        if discount < avg_discount * 0.7:
            return 30
        elif discount < avg_discount * 0.9:
            return 45
        elif discount < avg_discount * 1.1:
            return 60
        elif discount < avg_discount * 1.3:
            return 50
        else:
            return 35

    def _pick_optimal(self, ranges: List[Dict], risk_appetite: str) -> Dict:
        """Pick the optimal range based on risk appetite."""
        preference = {"conservative": 0, "moderate": 1, "aggressive": 2}
        idx = preference.get(risk_appetite, 1)
        opt = ranges[idx] if idx < len(ranges) else ranges[1]
        return {
            "strategy": opt["strategy"],
            "discount_pct": opt["discount_pct"],
            "bid_amount": opt["bid_amount"],
            "estimated_margin_pct": opt["estimated_margin_pct"],
            "win_probability": opt.get("win_probability", 50),
            "reason": f"Based on {risk_appetite} risk profile"
        }
