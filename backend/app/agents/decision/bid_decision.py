"""
Agent 39 — Bid/No-Bid Engine
Phase 2: Decision Intelligence Engine

If WinProb > threshold AND ProfitMargin > 15% → BID
Output: Confidence level + Expected margin
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from app.db.database import get_sync_engine
from sqlalchemy import text

logger = logging.getLogger(__name__)


class BidNoBidAgent(BaseAgent):
    agent_id = "agent-039-bid-no-bid"
    agent_name = "Bid/No-Bid Engine"
    description = "Decision engine: recommends BID or NO-BID with confidence level and expected margin."
    dependencies = ["agent-016-win-probability", "agent-017-bid-position-optimizer", "agent-022-executive-decision"]
    version = "1.0.0"

    AGENCY_BLACKLIST = []
    MIN_PROFIT_MARGIN = 12.0
    MIN_WIN_PROB = 40.0

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        tender_id = context.get("tender_id", "")
        agency = context.get("agency", "")
        estimate = context.get("estimate", context.get("estimated_amount", 0))
        company = context.get("company_profile", context.get("company", {}))

        # Gather intelligence from other agents
        win_data = await self._get_win_probability(tender_id, context)
        bid_data = await self._get_bid_position(tender_id, context)
        exec_data = await self._get_executive_decision(tender_id, context)

        # Check blacklist
        if agency in self.AGENCY_BLACKLIST:
            return self._decision("NO-BID", 0, {"reason": "Agency blacklisted"})

        # Core decision logic
        win_prob = win_data.get("probability", 50)
        margin = 10
        if bid_data:
            recommendation = bid_data.get("recommendation", {}) or {}
            ranges = bid_data.get("ranges", []) or []
            fallback_range = ranges[1] if len(ranges) > 1 and isinstance(ranges[1], dict) else {}
            margin = (
                recommendation.get("estimated_margin_pct")
                if isinstance(recommendation, dict) and recommendation.get("estimated_margin_pct") is not None
                else fallback_range.get("estimated_margin_pct", 10)
            )
        confidence = self._compute_confidence(win_data, bid_data, exec_data)

        decision, reasons = self._decide(win_prob, margin, agency, company)

        result = {
            "decision": decision,
            "confidence": confidence,
            "win_probability": win_prob,
            "expected_margin_pct": margin,
            "estimated_bid_amount": bid_data.get("recommendation", {}).get("bid_amount", 0) if bid_data else 0,
            "reasons": reasons,
            "factors": [
                {"name": "Win Probability", "value": f"{win_prob}%", "threshold": f">{self.MIN_WIN_PROB}%", "pass": win_prob >= self.MIN_WIN_PROB},
                {"name": "Expected Margin", "value": f"{margin}%", "threshold": f">{self.MIN_PROFIT_MARGIN}%", "pass": margin >= self.MIN_PROFIT_MARGIN},
                {"name": "Agency Risk", "value": agency, "pass": agency not in self.AGENCY_BLACKLIST},
            ],
            "version": "1.0"
        }

        await self.share_knowledge(entry_type="bid_decision", tender_id=tender_id,
            data=result, summary=f"{decision}: {win_prob}% WP, {margin}% margin",
            tags=["bid-decision", decision])

        return AgentResult(status=AgentStatus.SUCCESS, output=result)

    async def _get_win_probability(self, tender_id: str, ctx: Dict) -> Dict:
        if self.brain and tender_id:
            try:
                r = await self.ask_agent("agent-016-win-probability", "compute", ctx)
                return r or {}
            except Exception: pass
        return {}

    async def _get_bid_position(self, tender_id: str, ctx: Dict) -> Dict:
        if self.brain and tender_id:
            try:
                r = await self.ask_agent("agent-017-bid-position-optimizer", "compute", ctx)
                return r or {}
            except Exception: pass
        return {}

    async def _get_executive_decision(self, tender_id: str, ctx: Dict) -> Dict:
        if self.brain and tender_id:
            try:
                r = await self.ask_agent("agent-022-executive-decision", "evaluate", ctx)
                return r or {}
            except Exception: pass
        return {}

    def _decide(self, win_prob: float, margin: float, agency: str, company: Dict) -> tuple:
        reasons = []
        if win_prob >= self.MIN_WIN_PROB and margin >= self.MIN_PROFIT_MARGIN:
            decision = "BID"
            reasons.append(f"Win probability {win_prob}% exceeds threshold {self.MIN_WIN_PROB}%")
            reasons.append(f"Expected margin {margin}% exceeds threshold {self.MIN_PROFIT_MARGIN}%")
            if win_prob >= 70:
                reasons.append("High win probability — strong competitive position")
                decision = "AGGRESSIVE_BID"
            elif win_prob >= 55:
                reasons.append("Moderate win probability — bid competitively")
                decision = "BID"
            else:
                reasons.append("Marginal win probability — consider discount improvement")
                decision = "CAUTIOUS_BID"
        elif win_prob >= self.MIN_WIN_PROB:
            reasons.append(f"Win probability OK ({win_prob}%) but margin too low ({margin}% vs {self.MIN_PROFIT_MARGIN}%)")
            decision = "NO-BID"
        elif margin >= self.MIN_PROFIT_MARGIN:
            reasons.append(f"Margin OK ({margin}%) but win probability too low ({win_prob}% vs {self.MIN_WIN_PROB}%)")
            decision = "NO-BID"
        else:
            reasons.append(f"Below thresholds: WP={win_prob}% (need {self.MIN_WIN_PROB}%), Margin={margin}% (need {self.MIN_PROFIT_MARGIN}%)")
            decision = "NO-BID"
        return decision, reasons

    def _compute_confidence(self, win: Dict, bid: Dict, exec_: Dict) -> str:
        score = 0
        if win: score += 40
        if bid: score += 30
        if exec_: score += 30
        return "High" if score >= 70 else "Medium" if score >= 40 else "Low"
