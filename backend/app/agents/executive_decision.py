"""
Agent 21 — Executive Decision Agent
Provides the final executive recommendation by combining outputs from all relevant agents.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .base import BaseAgent, AgentResult, AgentStatus
from .schemas import ExecutiveDecision

logger = logging.getLogger(__name__)


class ExecutiveDecisionAgent(BaseAgent):
    agent_id = "agent-022-executive-decision"
    agent_name = "Executive Decision Agent"
    description = "Aggregates outputs from all agents to produce the final executive recommendation."
    dependencies: List[str] = [
        "agent-007-eligibility-compliance",
        "agent-008-risk-intelligence",
        "agent-016-win-probability",
        "agent-018-ai-bid-assistant",
        "agent-019-resource-capacity",
        "agent-021-financial-intelligence",
    ]
    version = "1.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        upstream = context.get("upstream", {})

        decision = await self._make_decision(upstream, context)

        output = {
            "decision": decision.decision,
            "risk_level": decision.risk_level,
            "win_chance": decision.win_chance,
            "win_chance_pct": f"{decision.win_chance:.1f}%",
            "expected_profit": decision.expected_profit,
            "expected_profit_formatted": decision.expected_profit_bdt,
            "confidence": decision.confidence,
            "summary": decision.summary,
            "agent_summaries": decision.agent_summaries,
        }

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=output,
        )

    async def _make_decision(self, upstream: Dict, context: Dict) -> ExecutiveDecision:
        decision = ExecutiveDecision()

        bid_assistant = upstream.get("agent-018-ai-bid-assistant", {})
        risk = upstream.get("agent-008-risk-intelligence", {})
        win_prob = upstream.get("agent-016-win-probability", {})
        financial = upstream.get("agent-021-financial-intelligence", {})
        eligibility = upstream.get("agent-007-eligibility-compliance", {})

        # Gather key metrics
        decision.win_chance = win_prob.get("win_probability", 50)
        decision.risk_level = risk.get("risk_level", "Medium")
        decision.expected_profit = financial.get("expected_profit", 6_300_000)
        decision.expected_profit_bdt = f"৳{decision.expected_profit:,.2f} Cr"

        # Decision logic
        is_compliant = eligibility.get("compliant", False)
        should_bid = bid_assistant.get("should_bid", False)

        if not is_compliant:
            decision.decision = "NO_BID"
            decision.confidence = "High"
        elif should_bid and decision.win_chance >= 60:
            decision.decision = "BID"
            decision.confidence = "High"
        elif should_bid and decision.win_chance >= 40:
            decision.decision = "BID"
            decision.confidence = "Medium"
        else:
            decision.decision = "NO_BID"
            decision.confidence = "Medium"

        # Build summaries
        decision.agent_summaries = {
            "Eligibility": "PASS" if is_compliant else "FAIL",
            "Risk": decision.risk_level,
            "Win Probability": f"{decision.win_chance:.0f}%",
            "Expected Profit": decision.expected_profit_bdt,
            "Recommendation": bid_assistant.get("recommendation", "N/A"),
        }

        decision.summary = (
            f"{'BID' if decision.decision == 'BID' else 'NO-BID'} | "
            f"Risk: {decision.risk_level} | "
            f"Win Chance: {decision.win_chance:.0f}% | "
            f"Expected Profit: {decision.expected_profit_bdt}"
        )

        return decision
