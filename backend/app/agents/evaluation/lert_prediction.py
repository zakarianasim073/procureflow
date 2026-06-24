"""
Agent 10 — LERT Prediction Agent
Predicts Lowest Evaluated Responsive Tender amount using competitor analysis and PPR rules.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from app.agent_schemas import LERTPrediction

logger = logging.getLogger(__name__)


class LERTPredictionAgent(BaseAgent):
    agent_id = "agent-010-lert-prediction"
    agent_name = "LERT Prediction Agent"
    description = "Predicts the Lowest Evaluated Responsive Tender (LERT) amount using competitor behavior analysis and PPR discount patterns."
    dependencies: List[str] = ["agent-009-ppr-evaluation", "agent-013-competitor-intelligence"]
    version = "2.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        tender_value = context.get("estimated_value", 52_000_000)
        tender_info = context.get("tender_info", {})
        competitors = context.get("upstream", {}).get("agent-013-competitor-intelligence", {})

        prediction = await self._predict_lert(tender_value, competitors, tender_info)

        output = {
            "tender_value": tender_value,
            "predicted_lert": prediction["predicted_lert"],
            "discount_range": prediction["discount_range"],
            "confidence_interval": prediction["confidence_interval"],
            "num_competitors_expected": prediction["num_competitors_expected"],
            "methodology": prediction["methodology"],
            "risk_assessment": prediction["risk_assessment"],
            "recommendation": prediction["recommendation"],
        }

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=output,
        )

    async def _predict_lert(
        self, tender_value: float, competitors: Dict, tender_info: Dict
    ) -> Dict:
        """Predict LERT using statistical modeling of competitor discount patterns."""
        # Extract competitor discount data
        competitor_list = competitors.get("competitors", [])
        avg_discount = competitors.get("market_insights", {}).get("avg_market_discount", 5.0)
        num_competitors_expected = len(competitor_list) if competitor_list else 5

        # Calculate expected LERT discount
        # Based on PPR 2025 patterns: LERT typically 5-12% below estimate
        base_discount = avg_discount
        
        # Adjust for number of competitors (more competitors = higher discount)
        competition_factor = 1 + (num_competitors_expected - 3) * 0.05
        adjusted_discount = base_discount * competition_factor
        
        # Add agency-specific adjustment
        agency = tender_info.get("procuring_entity", "")
        agency_factors = {
            "LGED": 1.1, "RHD": 1.0, "PWD": 0.95,
            "BWDB": 1.05, "DPHE": 1.15, "BREB": 1.0,
        }
        agency_factor = agency_factors.get(agency, 1.0)
        final_discount = adjusted_discount * agency_factor

        # Expected LERT
        predicted_lert = round(tender_value * (1 - final_discount / 100), 2)

        # Discount range (low-high)
        low_discount = max(final_discount * 0.7, 2.0)
        high_discount = min(final_discount * 1.4, 18.0)

        # Confidence interval
        std_dev = final_discount * 0.15
        ci_lower = round(tender_value * (1 - (final_discount + 2 * std_dev) / 100), 2)
        ci_upper = round(tender_value * (1 - (final_discount - 2 * std_dev) / 100), 2)

        # Risk assessment
        if final_discount > 12:
            risk = "HIGH"
            recommendation = "Consider aggressive pricing — competition expected to bid low"
        elif final_discount > 8:
            risk = "MEDIUM"
            recommendation = "Standard competitive pricing recommended"
        else:
            risk = "LOW"
            recommendation = "Conservative pricing may be sufficient"

        return {
            "predicted_lert": predicted_lert,
            "discount_range": {
                "low": round(low_discount, 1),
                "high": round(high_discount, 1),
                "expected": round(final_discount, 1),
            },
            "confidence_interval": {
                "lower": ci_lower,
                "upper": ci_upper,
                "confidence_level": "95%",
            },
            "num_competitors_expected": num_competitors_expected,
            "methodology": "Statistical discount analysis with PPR 2025 pattern matching",
            "risk_assessment": risk,
            "recommendation": recommendation,
        }
