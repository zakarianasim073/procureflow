"""
Agent 15 — Competitor Pricing Predictor
Predicts competitor bid pricing based on historical behavior, market position, and tender characteristics.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List

from .base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class CompetitorPricingPredictorAgent(BaseAgent):
    agent_id = "agent-015-competitor-pricing-predictor"
    agent_name = "Competitor Pricing Predictor"
    description = "Predicts expected competitor bid prices using historical discount patterns, market position analysis, and tender characteristics."
    dependencies: List[str] = ["agent-013-competitor-intelligence", "agent-014-award-intelligence"]
    version = "2.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        tender_info = context.get("tender_info", {})
        upstream = context.get("upstream", {})
        competitor_data = upstream.get("agent-013-competitor-intelligence", {})
        award_data = upstream.get("agent-014-award-intelligence", {})

        predictions = await self._predict_pricing(tender_info, competitor_data, award_data)

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=predictions,
        )

    async def _predict_pricing(self, tender: Dict, competitor_data: Dict, award_data: Dict) -> Dict:
        """Predict pricing for each known competitor."""
        estimated_value = tender.get("estimated_value", 50_000_000)
        competitors = competitor_data.get("competitors", self._default_competitors())
        
        predictions = []
        for comp in competitors:
            prediction = self._predict_single_competitor(comp, estimated_value)
            predictions.append(prediction)
        
        # Market-level prediction
        if predictions:
            avg_expected = sum(p["expected_bid"] for p in predictions) / len(predictions)
            min_expected = min(p["expected_bid"] for p in predictions)
            max_expected = max(p["expected_bid"] for p in predictions)
        else:
            avg_expected = estimated_value * 0.95
            min_expected = estimated_value * 0.90
            max_expected = estimated_value * 0.98
        
        return {
            "competitor_predictions": sorted(predictions, key=lambda p: p["expected_bid"]),
            "market_prediction": {
                "estimated_value": estimated_value,
                "avg_expected_bid": round(avg_expected, 2),
                "lowest_expected_bid": round(min_expected, 2),
                "highest_expected_bid": round(max_expected, 2),
                "avg_discount_pct": round((1 - avg_expected / estimated_value) * 100, 1),
            },
            "num_competitors_analyzed": len(predictions),
        }

    def _predict_single_competitor(self, competitor: Dict, estimated_value: float) -> Dict:
        """Predict a single competitor's bid pricing."""
        name = competitor.get("name", "Unknown")
        historical_discount = competitor.get("avg_discount", 5.0)
        preferred_agency = competitor.get("preferred_agency", "")
        
        # Adjust discount based on competitor's historical behavior
        # Strong competitors tend to bid more aggressively
        win_rate = competitor.get("win_rate", 10)
        if win_rate > 15:
            discount_multiplier = 1.15  # Aggressive discounters
        elif win_rate > 8:
            discount_multiplier = 1.0  # Standard
        else:
            discount_multiplier = 0.9  # Conservative
        
        predicted_discount = historical_discount * discount_multiplier
        
        # Add small random variation for realism
        import random
        variation = random.uniform(-0.5, 0.5)
        predicted_discount += variation
        
        # Ensure discount is within reasonable bounds
        predicted_discount = max(2.0, min(15.0, predicted_discount))
        
        expected_bid = round(estimated_value * (1 - predicted_discount / 100), 2)
        
        # Confidence based on data availability
        if competitor.get("total_wins", 0) > 10:
            confidence = "HIGH"
        elif competitor.get("total_wins", 0) > 3:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        
        return {
            "competitor_name": name,
            "historical_avg_discount": historical_discount,
            "predicted_discount": round(predicted_discount, 1),
            "expected_bid": expected_bid,
            "discount_vs_estimate": round(predicted_discount, 1),
            "confidence": confidence,
            "factors": [
                f"Historical discount: {historical_discount}%",
                f"Win rate adjustment: {discount_multiplier}x",
                f"Preferred agency: {preferred_agency}",
            ],
        }

    def _default_competitors(self) -> List[Dict]:
        """Return default competitor profiles when no data available."""
        return [
            {"name": "XYZ Builders Ltd.", "avg_discount": 5.2, "win_rate": 18.5, "total_wins": 12, "preferred_agency": "LGED"},
            {"name": "ABC Construction Ltd.", "avg_discount": 4.8, "win_rate": 15.2, "total_wins": 10, "preferred_agency": "RHD"},
            {"name": "PQR Infrastructure Ltd.", "avg_discount": 6.1, "win_rate": 12.3, "total_wins": 8, "preferred_agency": "PWD"},
            {"name": "Delta Engineering Ltd.", "avg_discount": 3.9, "win_rate": 10.8, "total_wins": 7, "preferred_agency": "BWDB"},
            {"name": "Sigma Developers Ltd.", "avg_discount": 5.5, "win_rate": 9.2, "total_wins": 6, "preferred_agency": "BREB"},
        ]
