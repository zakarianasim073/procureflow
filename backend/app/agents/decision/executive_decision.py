"""
Agent 22 - Executive Decision Agent
Makes bid/no-bid recommendations with confidence scoring.
"""
from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from typing import Any, Dict
import logging

logger = logging.getLogger(__name__)

class ExecutiveDecisionAgent(BaseAgent):
    agent_id = "agent-022-executive-decision"
    agent_name = "Executive Decision"
    description = "Bid/no-bid recommendation engine"
    dependencies = ["agent-016-win-probability", "agent-017-bid-position-optimizer"]
    version = "1.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        win_prob = float(context.get("win_probability", 0) or 0)
        margin = float(context.get("expected_margin", 0) or 0)
        capacity = bool(context.get("capacity_available", True))
        
        # Gather intelligence from other agents before making decision
        gathered = {}
        if self.brain and context.get("tender_id"):
            # Ask Win Probability for fresh prediction
            wp = await self.ask_agent(
                "agent-016-win-probability",
                "predict_win_probability",
                {"tender_id": context["tender_id"], "context": context}
            )
            if wp:
                gathered["win_probability_result"] = wp
            
            # Ask Bid Position Optimizer for discount range
            bpo = await self.ask_agent(
                "agent-017-bid-position-optimizer",
                "optimize_bid_position",
                {"tender_id": context["tender_id"], "context": context}
            )
            if bpo:
                gathered["bid_position_result"] = bpo
            
            # Ask Resource Capacity for workload check
            rc = await self.ask_agent(
                "agent-019-resource-capacity",
                "check_capacity",
                {"tender_id": context["tender_id"]}
            )
            if rc:
                gathered["capacity_result"] = rc

        win_source = gathered.get("win_probability_result") or {}
        bid_source = gathered.get("bid_position_result") or {}
        capacity_source = gathered.get("capacity_result") or {}

        if isinstance(win_source, dict):
            win_prob = float(
                win_source.get("probability", win_source.get("win_probability", win_prob)) or win_prob
            )
        if isinstance(bid_source, dict):
            recommendation = bid_source.get("recommendation", {}) or {}
            ranges = bid_source.get("ranges", []) or []
            fallback_range = ranges[1] if len(ranges) > 1 and isinstance(ranges[1], dict) else {}
            margin = float(
                recommendation.get("estimated_margin_pct")
                if isinstance(recommendation, dict) and recommendation.get("estimated_margin_pct") is not None
                else fallback_range.get("estimated_margin_pct", margin)
            )
        if isinstance(capacity_source, dict):
            capacity = bool(capacity_source.get("has_capacity", capacity))
        
        score = (win_prob * 0.45) + (margin * 2.0) + (15.0 if capacity else 0.0)
        decision = "BID" if score >= 60 else "NO-BID"
        
        # Share decision to knowledge lake
        await self.share_knowledge(
            entry_type="executive_decision",
            tender_id=context.get("tender_id", ""),
            data={"decision": decision, "score": score, "intel_gathered": gathered},
            summary=f"Decision: {decision} (confidence: {score:.1f})",
            tags=["executive_decision", decision.lower()]
        )
        
        return AgentResult(status=AgentStatus.SUCCESS, output={
            "decision": decision,
            "confidence_score": round(score, 1),
            "factors": {"win_probability": win_prob, "expected_margin": margin, "capacity": capacity},
            "intel_sources": gathered,
        })
