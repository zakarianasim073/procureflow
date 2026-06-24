"""
Agent 27 — Workflow Orchestrator (Master Agent)
Central control system that coordinates all 47 agents in the Procurement Flow Specialist BD pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from .base import BaseAgent, AgentResult, AgentStatus
from .registry import AgentRegistry

logger = logging.getLogger(__name__)


class PipelinePhase(Enum):
    """Major phases of the tender processing pipeline."""
    DISCOVERY = "discovery"
    INTELLIGENCE = "intelligence"
    EVALUATION = "evaluation"
    PRICING = "pricing"
    COMPETITOR = "competitor"
    DECISION = "decision"
    EXECUTION = "execution"
    REPORTING = "reporting"
    LEARNING = "learning"
    POST_AWARD = "post_award"
    ALERTING = "alerting"
    PRE_SCREEN = "pre_screen"
    FORECAST = "forecast"
    KNOWLEDGE = "knowledge"


PIPELINE_DEFINITION: Dict[PipelinePhase, List[str]] = {
    PipelinePhase.DISCOVERY: [
        "agent-001-tender-radar",
        "agent-002-tender-acquisition",
        "agent-003-corrigendum-watchdog",
    ],
    PipelinePhase.PRE_SCREEN: [
        "agent-038-tender-pre-screener",
    ],
    PipelinePhase.INTELLIGENCE: [
        "agent-004-document-ai",
        "agent-005-boq-intelligence",
        "agent-006-spec-intelligence",
        "agent-042-app-forecast",
    ],
    PipelinePhase.EVALUATION: [
        "agent-007-eligibility-compliance",
        "agent-008-risk-intelligence",
        "agent-009-ppr-evaluation",
        "agent-010-lert-prediction",
        "agent-010-ppr2025-compliance",
        "agent-037-ppr2025-dashboard",
    ],
    PipelinePhase.PRICING: [
        "agent-011-rate-analysis",
        "agent-012-market-rate-intelligence",
        "agent-044-sor-zone-matcher",
        "agent-033-vat-tax-calculator",
    ],
    PipelinePhase.COMPETITOR: [
        "agent-013-competitor-intelligence",
        "agent-014-award-intelligence",
        "agent-015-competitor-pricing-predictor",
        "agent-016-win-probability",
        "agent-017-bid-position-optimizer",
        "agent-028-syndicate-radar",
        "agent-036-moat-slt-analyzer",
    ],
    PipelinePhase.DECISION: [
        "agent-018-ai-bid-assistant",
        "agent-019-resource-capacity",
        "agent-021-financial-intelligence",
        "agent-022-executive-decision",
        "agent-039-bid-no-bid",
        "agent-043-client-intelligence",
    ],
    PipelinePhase.EXECUTION: [
        "agent-020-egp-rate-fill",
        "agent-024-submission-validation",
        "agent-034-tender-document",
        "agent-032-document-preparation",
        "agent-031-tender-preparation",
        "agent-035-tender-dashboard",
    ],
    PipelinePhase.REPORTING: [
        "agent-023-report-generation",
        "agent-045-opening-report",
    ],
    PipelinePhase.LEARNING: [
        "agent-025-knowledge-lake",
        "agent-026-learning",
    ],
    PipelinePhase.KNOWLEDGE: [
        "agent-040-company-brain",
        "agent-041-market-brain",
    ],
    PipelinePhase.FORECAST: [
        "agent-030-ra-bill-predictor",
        "agent-029-vision-intelligence",
        "agent-042-app-forecast",
    ],
    PipelinePhase.POST_AWARD: [
        "agent-030-ra-bill-predictor",
        "agent-029-vision-intelligence",
    ],
    PipelinePhase.ALERTING: [
        "agent-031-whatsapp-automation",
    ],
}


class WorkflowOrchestrator(BaseAgent):
    """
    Master Agent that orchestrates the entire Procurement Flow Specialist BD pipeline.
    
    Coordinates agent execution across all phases:
    Tender Radar → Acquisition → Document AI → BOQ Intelligence → 
    Rate Analysis → PPR Evaluation → LERT Prediction → Bid Decision →
    Submission Validation → Knowledge Lake
    """

    agent_id = "agent-027-orchestrator"
    agent_name = "Workflow Orchestrator"
    description = "Master orchestrator controlling all 47 agents across the complete tender processing pipeline."
    dependencies: List[str] = []
    version = "2.0.0"

    def __init__(self) -> None:
        super().__init__()
        self._registry = AgentRegistry()
        self._pipeline_run_id: str = ""
        self._phase_results: Dict[str, Any] = {}

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        """
        Execute the full pipeline or a subset based on context.
        
        Context options:
        - mode: "full" | "phase" | "agents"
        - phase: PipelinePhase value (if mode="phase")
        - agent_ids: List[str] (if mode="agents")
        - tender_id: specific tender to process
        """
        mode = context.get("mode", "full")
        self._pipeline_run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

        logger.info(f"[Orchestrator] Starting pipeline run {self._pipeline_run_id} (mode={mode})")

        try:
            if mode == "full":
                result = await self._run_full_pipeline(context)
            elif mode == "phase":
                result = await self._run_phase(context)
            elif mode == "agents":
                result = await self._run_agents(context)
            else:
                result = {"error": f"Unknown mode: {mode}"}

            output = {
                "pipeline_run_id": self._pipeline_run_id,
                "mode": mode,
                "status": "Procurement Flow Specialist BD Operating System",
                **result,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            return AgentResult(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                status=AgentStatus.SUCCESS,
                output=output,
            )

        except Exception as exc:
            logger.error(f"[Orchestrator] Pipeline failed: {exc}")
            return AgentResult(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                output={"pipeline_run_id": self._pipeline_run_id, "error": str(exc)},
            )

    # ------------------------------------------------------------------
    # Full Pipeline
    # ------------------------------------------------------------------

    async def _run_full_pipeline(self, context: Dict[str, Any]) -> Dict:
        """Run all phases in sequence with data passing between them."""
        all_results: Dict[str, Any] = {}
        pipeline_context = dict(context)

        phases = list(PipelinePhase)
        total = len(phases)

        for idx, phase in enumerate(phases, 1):
            logger.info(f"[Orchestrator] Phase {idx}/{total}: {phase.value}")
            phase_result = await self._execute_phase(phase, pipeline_context)
            all_results[phase.value] = phase_result
            pipeline_context[f"phase_{phase.value}"] = phase_result

        return {
            "phases_completed": total,
            "phases": self._summarize_phases(all_results),
            "pipeline_complete": True,
        }

    # ------------------------------------------------------------------
    # Phase Execution
    # ------------------------------------------------------------------

    async def _run_phase(self, context: Dict[str, Any]) -> Dict:
        phase_name = context.get("phase", "discovery")
        try:
            phase = PipelinePhase(phase_name)
        except ValueError:
            return {"error": f"Unknown phase: {phase_name}. Available: {[p.value for p in PipelinePhase]}"}

        result = await self._execute_phase(phase, context)
        return {phase.value: result}

    async def _execute_phase(self, phase: PipelinePhase, context: Dict) -> Dict:
        agent_ids = PIPELINE_DEFINITION.get(phase, [])
        if not agent_ids:
            return {"agents_run": 0, "message": f"No agents defined for phase {phase.value}"}

        results = await self._registry.run_pipeline(agent_ids, context, stop_on_failure=True)

        return {
            "phase": phase.value,
            "agents_run": len(results),
            "agent_results": {
                aid: {
                    "status": r.status.value,
                    "agent_name": r.agent_name,
                    "error": r.error,
                    "execution_time_ms": r.execution_time_ms,
                    "agent_id": r.agent_id,
                    "output": r.output,
                }
                for aid, r in results.items()
            },
            "all_succeeded": all(r.status == AgentStatus.SUCCESS for r in results.values()),
            "failed_agents": [aid for aid, r in results.items() if r.status == AgentStatus.FAILED],
        }

    # ------------------------------------------------------------------
    # Custom Agent Execution
    # ------------------------------------------------------------------

    async def _run_agents(self, context: Dict[str, Any]) -> Dict:
        agent_ids = context.get("agent_ids", [])
        if not agent_ids:
            return {"error": "No agent_ids provided"}

        results = await self._registry.run_pipeline(agent_ids, context, stop_on_failure=False)

        return {
            "agents_run": len(results),
            "agent_results": {
                aid: {
                    "status": r.status.value,
                    "agent_name": r.agent_name,
                    "error": r.error,
                }
                for aid, r in results.items()
            },
        }

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _summarize_phases(self, results: Dict[str, Any]) -> Dict[str, str]:
        summary = {}
        for phase, data in results.items():
            if isinstance(data, dict):
                status = "✅" if data.get("all_succeeded", False) else "⚠️"
                count = data.get("agents_run", 0)
                summary[phase] = f"{status} {count} agents"
        return summary

    # ------------------------------------------------------------------
    # System Status & Health
    # ------------------------------------------------------------------

    async def system_status(self) -> Dict[str, Any]:
        """Return the current status of all registered agents."""
        agents = self._registry.list_agents()
        return {
            "orchestrator_version": self.version,
            "total_agents": len(agents),
            "agents": agents,
            "phases": {
                p.value: len(PIPELINE_DEFINITION[p]) for p in PipelinePhase
            },
            "system_ready": self._check_system_ready(agents),
        }

    def _check_system_ready(self, agents: List[Dict]) -> bool:
        """Check all required agents are registered and idle."""
        required_ids = set()
        for phase_agents in PIPELINE_DEFINITION.values():
            required_ids.update(phase_agents)
        required_ids.add(self.agent_id)

        registered_ids = {a["agent_id"] for a in agents}
        return required_ids.issubset(registered_ids)
