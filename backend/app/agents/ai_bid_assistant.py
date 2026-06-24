"""
Agent 18 — AI Bid Assistant
Answers the question "Should We Bid?" by analyzing resources, margin, risk, and competition.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .base import BaseAgent, AgentResult, AgentStatus
from .schemas import AIAssistantOutput

logger = logging.getLogger(__name__)


class AIBidAssistantAgent(BaseAgent):
    agent_id = "agent-018-ai-bid-assistant"
    agent_name = "AI Bid Assistant"
    description = "Provides a comprehensive bid/no-bid recommendation by analyzing resources, margin, risk, and competition."
    dependencies: List[str] = [
        "agent-007-eligibility-compliance",
        "agent-008-risk-intelligence",
        "agent-011-rate-analysis",
        "agent-016-win-probability",
        "agent-019-resource-capacity",
        "agent-021-financial-intelligence",
    ]
    version = "1.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        upstream = context.get("upstream", {})

        analysis = await self._analyze(upstream, context)

        output = {
            "should_bid": analysis.should_bid,
            "recommendation": analysis.recommendation,
            "analysis": {
                "resource_ok": analysis.resource_ok,
                "margin_ok": analysis.margin_ok,
                "risk_ok": analysis.risk_ok,
                "competition_ok": analysis.competition_ok,
            },
            "reason": analysis.reason,
        }

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=output,
        )

    async def _analyze(self, upstream: Dict, context: Dict) -> AIAssistantOutput:
        result = AIAssistantOutput()

        resources = upstream.get("agent-019-resource-capacity", {})
        risk = upstream.get("agent-008-risk-intelligence", {})
        win_prob = upstream.get("agent-016-win-probability", {})
        financial = upstream.get("agent-021-financial-intelligence", {})

        # Resource check
        capacity = resources.get("capacity_percent", 80)
        result.resource_ok = capacity < 90

        # Margin check
        expected_margin = financial.get("margin_percent", 12)
        result.margin_ok = expected_margin >= 10

        # Risk check
        risk_level = risk.get("risk_level", "Medium")
        result.risk_ok = risk_level != "High"

        # Competition check
        win_chance = win_prob.get("win_probability", 50)
        result.competition_ok = win_chance >= 40

        # Decision
        positives = sum([result.resource_ok, result.margin_ok, result.risk_ok, result.competition_ok])
        result.should_bid = positives >= 3

        if result.should_bid:
            result.recommendation = "BID"
            result.reason = f"Positive assessment ({positives}/4 factors favorable)"
        else:
            result.recommendation = "NO-BID"
            result.reason = f"Only {positives}/4 factors favorable — insufficient confidence"

        return result
