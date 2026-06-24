"""
Agent 43 — Client Intelligence Agent
Multi-tenant client management: priority analysis, sanitized outputs, subscription-aware recommendations.
Layer 3: Meta-allocator for multi-client conflict resolution.
"""
from __future__ import annotations
import logging, uuid
from typing import Any, Dict, List, Optional

from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from app.services.client_manager import get_client_manager
from app.services.meta_allocator import get_meta_allocator

logger = logging.getLogger(__name__)


class ClientIntelligenceAgent(BaseAgent):
    agent_id = "agent-043-client-intelligence"
    agent_name = "Client Intelligence Agent"
    description = "Multi-tenant client manager: priority, quota, sanitized outputs, conflict resolution."
    dependencies = ["agent-016-win-probability", "agent-017-bid-position-optimizer", 
                    "agent-022-executive-decision", "agent-039-bid-no-bid"]
    version = "1.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        action = context.get("action", "analyze")
        tenant_id = context.get("tenant_id", "")
        tender_id = context.get("tender_id", "")
        overrides = context.get("company_profile", context.get("profile", {}))

        cm = get_client_manager()
        ma = get_meta_allocator()

        if action == "create_client":
            result = cm.create_client(
                name=context.get("name", ""), slug=context.get("slug", ""),
                email=context.get("email", ""), phone=context.get("phone", ""),
                plan=context.get("plan", "starter")
            )
        elif action == "get_client":
            result = cm.get_client(tenant_id) or {"error": "Client not found"}
        elif action == "list_clients":
            result = {"clients": cm.list_clients()}
        elif action == "check_quota":
            result = cm.check_quota(tenant_id)
        elif action == "build_profile":
            profile = cm.build_client_profile(tenant_id, overrides)
            result = profile
        elif action == "update_profile":
            result = cm.update_client_profile(tenant_id, overrides)
        elif action == "get_usage":
            result = cm.get_usage_history(tenant_id, context.get("days", 30))
        elif action == "sanitize":
            # Sanitize an agent's raw output for client consumption
            raw = context.get("raw_output", {})
            priority = context.get("priority_tier", "MEDIUM")
            sharpness = context.get("sharpness", "standard")
            result = ma.sanitize_output(raw, priority, sharpness)
        elif action == "multi_client_eval":
            # Evaluate multiple clients for one tender
            profiles = context.get("client_profiles", [])
            evaluations = ma.evaluate_clients(tender_id, profiles)
            result = {"tender_id": tender_id, "evaluations": evaluations}
        elif action == "full_client_pipeline":
            # Full pipeline for one client: check quota → build profile → run agents → sanitize
            result = await self._full_pipeline(tenant_id, tender_id, overrides, cm, ma)
        else:
            # Default: client overview
            client = cm.get_client(tenant_id)
            quota = cm.check_quota(tenant_id)
            profile = cm.build_client_profile(tenant_id, overrides)
            result = {"client": client, "quota": quota, "profile": {
                k: v for k, v in profile.items() if k not in ["tenant_id"]
            }}

        return AgentResult(status=AgentStatus.SUCCESS, output=result)

    async def _full_pipeline(self, tenant_id: str, tender_id: str, 
                              overrides: Dict, cm, ma) -> Dict:
        """Run client-aware full pipeline with sanitized output."""
        # 1. Check quota
        quota = cm.check_quota(tenant_id)
        if not quota.get("has_quota"):
            return {"error": "Quota exhausted", "quota": quota}

        # 2. Build client profile
        profile = cm.build_client_profile(tenant_id, overrides)
        company_name = profile.get("company_name", "Client")

        # 3. Evaluate priority
        eval_result = ma.evaluate_clients(tender_id, [profile])
        client_eval = eval_result[0] if eval_result else {"priority_tier": "MEDIUM", "recommendation_sharpness": "standard"}

        # 4. Run downstream agents
        results = {}
        agents_to_run = ["agent-016-win-probability", "agent-017-bid-position-optimizer", 
                         "agent-039-bid-no-bid", "agent-022-executive-decision"]
        ctx = {"tender_id": tender_id, "company_profile": profile, "agency": overrides.get("agency", "")}

        for agent_id in agents_to_run:
            try:
                agent = self.brain.get_agent(agent_id) if self.brain else None
                if agent:
                    r = await agent.run(ctx)
                    results[agent_id] = r.output if hasattr(r, 'output') else {}
            except Exception as e:
                logger.warning(f"Agent {agent_id} failed in pipeline: {e}")

        # 5. Sanitize outputs
        combined_output = {}
        for r in results.values():
            if isinstance(r, dict):
                combined_output.update(r)

        sanitized = ma.sanitize_output(
            combined_output,
            client_eval.get("priority_tier", "MEDIUM"),
            client_eval.get("recommendation_sharpness", "standard")
        )

        # 6. Consume quota
        cm.consume_quota(tenant_id, tender_id)

        return {
            "status": "complete",
            "company": company_name,
            "priority": client_eval.get("priority_tier", "MEDIUM"),
            "quota_remaining": quota.get("remaining", 0),
            "sanitized_advice": sanitized,
            "pipeline_run": [aid for aid in agents_to_run if aid in results],
        }
