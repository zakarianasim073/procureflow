"""
Agent 20 — Financial Intelligence Agent
Analyzes financial health, bid capacity, working capital, and provides financial recommendations.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class FinancialIntelligenceAgent(BaseAgent):
    agent_id = "agent-021-financial-intelligence"
    agent_name = "Financial Intelligence Agent"
    description = "Analyzes financial health, bid capacity, working capital requirements, and provides financial risk assessment."
    dependencies: List[str] = ["agent-019-resource-capacity"]
    version = "2.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        company = context.get("company_profile", {})
        tender = context.get("tender_info", {})
        bid_amount = context.get("bid_amount", tender.get("estimated_value", 50_000_000))

        analysis = await self._analyze_financials(company, tender, bid_amount)

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=analysis,
        )

    async def _analyze_financials(self, company: Dict, tender: Dict, bid_amount: float) -> Dict:
        """Perform comprehensive financial analysis."""
        turnover = company.get("annual_turnover", 500_000_000)
        current_assets = company.get("current_assets", 200_000_000)
        current_liabilities = company.get("current_liabilities", 100_000_000)
        cash_in_hand = company.get("cash_in_hand", 50_000_000)
        existing_obligations = company.get("existing_contract_obligations", 150_000_000)
        profit_margin = company.get("avg_profit_margin", 10.0)

        # Bid capacity calculation (CPTU guideline: 2x turnover for single bid)
        max_bid_capacity = turnover * 0.5  # Conservative: 50% of annual turnover per bid
        total_bid_capacity = turnover * 2  # Total outstanding bids allowed
        current_bid_load = existing_obligations

        # Working capital analysis
        working_capital = current_assets - current_liabilities
        wc_ratio = current_assets / max(current_liabilities, 1)
        
        # Required working capital for this project (typically 10-20% of bid)
        required_wc = bid_amount * 0.15
        wc_sufficiency = (working_capital / max(required_wc, 1)) * 100
        
        # Cash position
        cash_shortfall = max(0, required_wc * 0.3 - cash_in_hand)
        
        # Bond/guarantee capacity
        max_bond_capacity = turnover * 0.1  # 10% of turnover for bid bonds
        required_bond = bid_amount * 0.02  # 2% bid security
        bond_adequacy = (max_bond_capacity / max(required_bond, 1)) * 100

        # Overall financial health score (0-100)
        scores = []
        
        # Liquidity score
        if wc_ratio >= 2:
            liquidity_score = 90
        elif wc_ratio >= 1.5:
            liquidity_score = 70
        elif wc_ratio >= 1:
            liquidity_score = 50
        else:
            liquidity_score = 25
        scores.append(("Liquidity", liquidity_score, 25))
        
        # Capacity score
        if bid_amount <= max_bid_capacity * 0.5:
            capacity_score = 85
        elif bid_amount <= max_bid_capacity:
            capacity_score = 60
        else:
            capacity_score = 30
        scores.append(("Bid Capacity", capacity_score, 25))
        
        # Working capital score
        if wc_sufficiency >= 150:
            wc_score = 90
        elif wc_sufficiency >= 100:
            wc_score = 70
        elif wc_sufficiency >= 50:
            wc_score = 45
        else:
            wc_score = 20
        scores.append(("Working Capital", wc_score, 25))
        
        # Bond capacity score
        if bond_adequacy >= 200:
            bond_score = 85
        elif bond_adequacy >= 100:
            bond_score = 65
        else:
            bond_score = 40
        scores.append(("Bond Capacity", bond_score, 25))

        # Weighted average
        total_health = sum(s * w for _, s, w in scores) / sum(w for _, _, w in scores)

        # Risk classification
        if total_health >= 75:
            risk_level = "LOW"
            recommendation = "Financially well-positioned for this bid"
        elif total_health >= 50:
            risk_level = "MEDIUM"
            recommendation = "Consider Joint Venture or subcontracting to strengthen financial position"
        else:
            risk_level = "HIGH"
            recommendation = "Financial constraints may affect bid competitiveness — seek financing or partnership"

        return {
            "financial_health_score": round(total_health, 1),
            "risk_level": risk_level,
            "bid_capacity": {
                "max_single_bid": round(max_bid_capacity, 2),
                "total_outstanding_capacity": round(total_bid_capacity, 2),
                "current_bid_load": round(current_bid_load, 2),
                "available_capacity": round(max(max_bid_capacity - bid_amount, 0), 2),
            },
            "working_capital": {
                "total": round(working_capital, 2),
                "current_ratio": round(wc_ratio, 2),
                "required_for_project": round(required_wc, 2),
                "sufficiency_pct": round(wc_sufficiency, 1),
                "cash_shortfall": round(cash_shortfall, 2),
            },
            "bond_capacity": {
                "max_available": round(max_bond_capacity, 2),
                "required_bid_security": round(required_bond, 2),
                "adequacy_pct": round(bond_adequacy, 1),
            },
            "detailed_scores": [
                {"category": name, "score": s, "weight": w}
                for name, s, w in scores
            ],
            "recommendation": recommendation,
            "factors_considered": [
                "Annual turnover vs bid amount",
                "Working capital adequacy",
                "Current ratio / liquidity",
                "Existing contract obligations",
                "Bid bond / guarantee capacity",
                "Cash in hand for mobilization",
            ],
        }
