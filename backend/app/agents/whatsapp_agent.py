"""
Agent 031 — WhatsApp Automation Agent
Sends tender alerts and summaries via WhatsApp Web browser automation.
Uses OpenClaw to control a logged-in WhatsApp Web session.
Falls back to wa.me links when browser automation is unavailable.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from .base import BaseAgent, AgentResult, AgentStatus
from ..services.whatsapp_automation import whatsapp_automation
from ..services.whatsapp_service import whatsapp_service

logger = logging.getLogger(__name__)


class WhatsAppAutomationAgent(BaseAgent):
    agent_id = "agent-031-whatsapp-automation"
    agent_name = "WhatsApp Automation Agent"
    description = "Sends tender alerts and summaries via WhatsApp Web browser automation using OpenClaw"
    dependencies: List[str] = [
        "agent-023-report-generation",
        "agent-025-knowledge-lake",
    ]
    version = "1.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        action = context.get("action", "send_summary")
        phone = context.get("phone", "") or whatsapp_service.default_phone
        language = context.get("language", "bn")
        tenders = context.get("tenders", [])
        tender_id = context.get("tender_id")
        message = context.get("message", "")

        output = {
            "action": action,
            "phone": phone,
            "language": language,
        }

        if action == "check_status":
            status = await whatsapp_automation.check_login_status()
            output["status"] = status
            return AgentResult(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                status=AgentStatus.SUCCESS,
                output=output,
            )

        if not phone:
            return AgentResult(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                output=output,
                error="No phone number provided",
            )

        if action == "send_single" and tender_id:
            tender = self._find_tender(context, tender_id)
            if tender:
                result = await whatsapp_automation.send_tender_alert(tender, phone=phone, lang=language)
            else:
                return AgentResult(
                    agent_id=self.agent_id,
                    agent_name=self.agent_name,
                    status=AgentStatus.FAILED,
                    output=output,
                    error=f"Tender {tender_id} not found",
                )

        elif action == "send_summary" and tenders:
            result = await whatsapp_automation.send_batch_alerts(tenders, phone=phone, lang=language)

        elif action == "send_custom" and message:
            result = await whatsapp_automation.send_message(phone, message)

        else:
            return AgentResult(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                output=output,
                error=f"Invalid action '{action}' — provide tenders, tender_id, or message",
            )

        output["result"] = result
        status = AgentStatus.SUCCESS if result.get("success") else AgentStatus.FAILED
        error = result.get("error") if not result.get("success") else None

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=status,
            output=output,
            error=error,
        )

    def _find_tender(self, context: Dict[str, Any], tender_id: str) -> Dict[str, Any]:
        all_tenders = context.get("tenders", [])
        if isinstance(all_tenders, list):
            for t in all_tenders:
                if str(t.get("tender_id", "")) == str(tender_id):
                    return t
        return context.get("tender_data", {})
