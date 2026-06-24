"""
Agent 24 - Submission Validation Agent
Validates tender submissions for completeness and compliance.
"""
from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from typing import Any, Dict, List
import logging

logger = logging.getLogger(__name__)

class SubmissionValidationAgent(BaseAgent):
    agent_id = "agent-024-submission-validation"
    agent_name = "Submission Validation"
    description = "Validates submission completeness and compliance"
    dependencies = ["agent-032-document-preparation"]
    version = "1.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        documents = context.get("documents", {})
        checklist = context.get("checklist", [])
        results = []
        for item in checklist:
            present = item.get("name") in documents
            results.append({"document": item.get("name"), "required": item.get("required"), "present": present})
        all_present = all(r["present"] or not r["required"] for r in results)
        return AgentResult(status=AgentStatus.SUCCESS, output={
            "valid": all_present,
            "checks": results,
            "passed": sum(1 for r in results if r["present"]),
            "total": len(results)
        })
