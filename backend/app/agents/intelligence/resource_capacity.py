"""
Agent 19 - Resource Capacity Agent
Evaluates company resource availability (equipment, engineers, workforce).
"""
from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from typing import Any, Dict, List
import logging

logger = logging.getLogger(__name__)

class ResourceCapacityAgent(BaseAgent):
    agent_id = "agent-019-resource-capacity"
    agent_name = "Resource Capacity"
    description = "Evaluates equipment, personnel, and workload capacity"
    dependencies = []
    version = "1.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        available = context.get("resources", {})
        required = context.get("requirements", {})
        gaps = []
        for k, v in required.items():
            avail = available.get(k, 0)
            if avail < v:
                gaps.append({"resource": k, "available": avail, "required": v, "shortfall": v - avail})
        return AgentResult(status=AgentStatus.SUCCESS, output={
            "has_capacity": len(gaps) == 0,
            "resource_gaps": gaps,
            "gap_count": len(gaps)
        })
