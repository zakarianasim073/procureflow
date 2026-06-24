"""
Agent 14 - Financial Intelligence Agent
Analyzes financial capacity, cash flow, and bid bonding capacity.
"""
from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from typing import Any, Dict
import logging

logger = logging.getLogger(__name__)

class FinancialIntelligenceAgent(BaseAgent):
    agent_id = "agent-021-financial-intelligence"
    agent_name = "Financial Intelligence"
    description = "Analyzes financial capacity and bid bonding"
    dependencies = ["agent-007-eligibility-compliance"]
    version = "1.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        turnover = context.get("turnover", 0)
        estimate = context.get("estimated_amount", 0)
        liquid_assets = context.get("liquid_assets", 0)
        capacity = (turnover * 0.5 + liquid_assets * 0.3)
        sufficient = capacity >= estimate * 0.1
        return AgentResult(status=AgentStatus.SUCCESS, output={
            "financial_capacity": capacity,
            "sufficient_for_bid": sufficient,
            "max_bonding_capacity": turnover * 0.2,
            "recommendation": "proceed" if sufficient else "caution"
        })
