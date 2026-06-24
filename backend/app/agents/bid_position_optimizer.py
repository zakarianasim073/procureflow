"""
Agent 17 — Bid Position Optimizer
Analyzes optimal bid positioning: discount rate, expected margin, and competitiveness.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class BidPositionOptimizerAgent(BaseAgent):
    agent_id = "agent-017-bid-position-optimizer"
    agent_name = "Bid Position Optimizer Agent"
    description = "Optimizes bid pricing position by balancing win probability, margin targets, and competitive landscape."
    dependencies: List[str] = ["agent-011-rate-analysis", "agent-013-competitor-intelligence", "agent-016-win-probability"]
    version = "2.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        upstream = context.get("upstream", {})
        tender = context.get("tender_info", {})

        optimization = await self._optimize_position(tender, upstream)

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=optimization,
        )

    async def _optimize_position(self, tender: Dict, upstream: Dict) -> Dict:
        """Calculate optimal bid position."""
        estimated_value = tender.get("estimated_value", 50_000_000)
        
        # Get upstream data
        lert_data = upstream.get("agent-010-lert-prediction", {})
        competitor_data = upstream.get("agent-013-competitor-intelligence", {})
        win_prob = upstream.get("agent-016-win-probability", {})
        
        predicted_lert = lert_data.get("predicted_lert", estimated_value * 0.93)
        discount_range = lert_data.get("discount_range", {"low": 3, "high": 8, "expected": 5})
        
        # Calculate target margin
        base_margin = 12.0  # base target margin %
        
        # Adjust margin based on competition
        num_competitors = len(competitor_data.get("competitors", [])) or 5
        if num_competitors > 7:
            margin_adjustment = -3
        elif num_competitors > 4:
            margin_adjustment = -1
        else:
            margin_adjustment = 2
        
        target_margin = base_margin + margin_adjustment
        
        # Generate bid scenarios
        scenarios = []
        for discount_pct in [3, 4, 5, 6, 7, 8, 10]:
            bid_amount = round(estimated_value * (1 - discount_pct / 100), 2)
            margin = target_margin - discount_pct + (predicted_lert / max(bid_amount, 1) - 1) * 100
            
            # Win probability estimation for this scenario
            if discount_pct <= discount_range.get("low", 3):
                win_chance = 25
            elif discount_pct <= discount_range.get("expected", 5):
                win_chance = 50
            elif discount_pct <= discount_range.get("high", 8):
                win_chance = 65
            else:
                win_chance = 40  # Too aggressive may indicate risk
            
            expected_value = bid_amount * (win_chance / 100) * (margin / 100)
            
            scenarios.append({
                "discount_pct": discount_pct,
                "bid_amount": bid_amount,
                "estimated_margin_pct": round(margin, 1),
                "win_probability": win_chance,
                "expected_value": round(expected_value, 2),
                "risk_level": "LOW" if discount_pct <= 4 else "MEDIUM" if discount_pct <= 7 else "HIGH",
            })
        
        # Select optimal scenario (highest expected value with acceptable risk)
        optimal = max(scenarios, key=lambda s: s["expected_value"] if s["risk_level"] != "HIGH" else 0)
        
        return {
            "optimal_discount": {
                "percentage": optimal["discount_pct"],
                "bid_amount": optimal["bid_amount"],
                "expected_margin": optimal["estimated_margin_pct"],
                "win_probability": optimal["win_probability"],
            },
            "scenarios": scenarios,
            "market_positioning": {
                "predicted_lert": predicted_lert,
                "lert_discount_range": discount_range,
                "num_competitors": num_competitors,
                "base_target_margin": base_margin,
                "adjusted_target_margin": round(target_margin, 1),
            },
            "recommendation": (
                f"Optimal bid: {optimal['discount_pct']}% discount (BDT {optimal['bid_amount']:,.0f}) "
                f"with {optimal['estimated_margin_pct']}% expected margin and "
                f"{optimal['win_probability']}% win probability"
            ),
        }
