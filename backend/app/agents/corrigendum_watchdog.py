"""
Agent 3 — Corrigendum Watchdog Agent
Monitors tender documents for changes, compares versions, and alerts users to modifications.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentResult, AgentStatus
from .schemas import CorrigendumChange

logger = logging.getLogger(__name__)


class CorrigendumWatchdogAgent(BaseAgent):
    agent_id = "agent-003-corrigendum-watchdog"
    agent_name = "Corrigendum Watchdog Agent"
    description = "Monitors tender documents for changes, compares versions, and alerts users to modifications including deadline extensions, scope changes, and rate revisions."
    dependencies: List[str] = ["agent-002-tender-acquisition"]
    version = "2.0.0"

    # Tracked fields for corrigendum monitoring
    TRACKED_FIELDS = [
        ("emd_amount", "EMD Amount"),
        ("completion_period_days", "Completion Period"),
        ("deadline", "Submission Deadline"),
        ("estimated_value_bdt", "Estimated Value"),
        ("bid_document_price", "Document Price"),
        ("opening_date", "Opening Date"),
        ("pre_bid_meeting", "Pre-bid Meeting Date"),
        ("location", "Delivery Location"),
        ("eligibility_criteria", "Eligibility Criteria"),
    ]

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        upstream = context.get("upstream", {})
        tender_id = context.get("tender_id", "eGP-001")

        previous_version = context.get("previous_version", {})
        current_version = context.get("current_version", {})

        # If we have acquisition output, use stored documents as baseline
        acquisition_output = upstream.get("agent-002-tender-acquisition", {})

        changes = await self._detect_changes(tender_id, previous_version, current_version)
        severity = self._assess_severity(changes)
        
        output = {
            "tender_id": tender_id,
            "changes_detected": len(changes),
            "changes": [c.__dict__ for c in changes],
            "severity": severity,
            "alert_required": len(changes) > 0,
            "recommended_action": self._get_recommended_action(severity, changes),
        }

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=output,
        )

    async def _detect_changes(
        self,
        tender_id: str,
        previous: Dict[str, Any],
        current: Dict[str, Any],
    ) -> List[CorrigendumChange]:
        """Detect changes between previous and current versions of tracked fields."""
        detected = []

        for field, label in self.TRACKED_FIELDS:
            old_val = previous.get(field, "N/A")
            new_val = current.get(field, "N/A")
            if str(old_val) != str(new_val):
                detected.append(CorrigendumChange(
                    tender_id=tender_id,
                    field_changed=label,
                    old_value=str(old_val),
                    new_value=str(new_val),
                    detected_at=self._now(),
                ))

        return detected

    def _assess_severity(self, changes: List[CorrigendumChange]) -> str:
        """Assess the severity of detected changes."""
        high_impact_fields = {"Submission Deadline", "Estimated Value", "Completion Period", "Eligibility Criteria"}
        
        if not changes:
            return "NONE"
        
        for change in changes:
            if change.field_changed in high_impact_fields:
                return "HIGH"
        
        if len(changes) >= 3:
            return "MEDIUM"
        
        return "LOW"

    def _get_recommended_action(self, severity: str, changes: List[CorrigendumChange]) -> str:
        """Get recommended action based on severity of changes."""
        if severity == "HIGH":
            action = "URGENT: Review all changes immediately. "
            for c in changes:
                if c.field_changed == "Submission Deadline":
                    action += f"Deadline changed from {c.old_value} to {c.new_value}. "
                elif c.field_changed == "Estimated Value":
                    action += f"Budget revised from {c.old_value} to {c.new_value}. "
                elif c.field_changed == "Eligibility Criteria":
                    action += "Eligibility requirements have changed — re-check qualification. "
            return action.strip()
        elif severity == "MEDIUM":
            return "Review changes before proceeding with bid preparation"
        else:
            return "No immediate action required — monitor for further updates"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
