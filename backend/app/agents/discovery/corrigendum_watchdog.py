"""
Agent 3 - Corrigendum Watchdog Agent
Monitors tender amendments and notifies changes.
"""
from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from typing import Any, Dict, List
import logging

logger = logging.getLogger(__name__)

class CorrigendumWatchdogAgent(BaseAgent):
    agent_id = "agent-003-corrigendum-watchdog"
    agent_name = "Corrigendum Watchdog"
    description = "Tracks tender amendments and changes"
    dependencies = ["agent-002-tender-acquisition"]
    version = "1.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        tender_id = context.get("tender_id", "")
        changes = context.get("changes", [])
        detected = []
        for c in changes:
            detected.append({
                "field": c.get("field", ""),
                "old_value": c.get("old", ""),
                "new_value": c.get("new", ""),
                "severity": "high" if c.get("critical") else "low"
            })
        return AgentResult(status=AgentStatus.SUCCESS, output={
            "tender_id": tender_id,
            "changes_detected": detected,
            "change_count": len(detected)
        })
