"""
Procurement Flow Specialist BD — Agent Pipeline Celery Tasks
Background wrappers for the 27-agent system.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from pathlib import Path

from app.celery_app import celery_app
from app.agents import AgentRegistry

logger = logging.getLogger("procureflow.tasks")


def get_registry() -> AgentRegistry:
    """Get or initialize the agent registry."""
    registry = AgentRegistry()
    # Register agents if not already done
    if registry.count == 0:
        from app.agents import (
            TenderRadarAgent, TenderAcquisitionAgent, CorrigendumWatchdogAgent,
            DocumentAIAgent, BOQIntelligenceAgent, SpecIntelligenceAgent,
            EligibilityComplianceAgent, RiskIntelligenceAgent, PPREvaluationAgent,
            LERTPredictionAgent, RateAnalysisAgent, MarketRateIntelligenceAgent,
            CompetitorIntelligenceAgent, AwardIntelligenceAgent, CompetitorPricingPredictorAgent,
            WinProbabilityAgent, BidPositionOptimizerAgent, AIBidAssistantAgent,
            ResourceCapacityAgent, FinancialIntelligenceAgent, ExecutiveDecisionAgent,
            EGPRateFillAgent, SubmissionValidationAgent, ReportGenerationAgent,
            KnowledgeLakeAgent, LearningAgent, WorkflowOrchestrator,
        )
        agents = [
            TenderRadarAgent(), TenderAcquisitionAgent(), CorrigendumWatchdogAgent(),
            DocumentAIAgent(), BOQIntelligenceAgent(), SpecIntelligenceAgent(),
            EligibilityComplianceAgent(), RiskIntelligenceAgent(), PPREvaluationAgent(),
            LERTPredictionAgent(), RateAnalysisAgent(), MarketRateIntelligenceAgent(),
            CompetitorIntelligenceAgent(), AwardIntelligenceAgent(), CompetitorPricingPredictorAgent(),
            WinProbabilityAgent(), BidPositionOptimizerAgent(), AIBidAssistantAgent(),
            ResourceCapacityAgent(), FinancialIntelligenceAgent(), ExecutiveDecisionAgent(),
            EGPRateFillAgent(), SubmissionValidationAgent(), ReportGenerationAgent(),
            KnowledgeLakeAgent(), LearningAgent(), WorkflowOrchestrator(),
        ]
        registry.register_many(*agents)
        logger.info(f"Registered {registry.count} agents in Celery worker")
    return registry


@celery_app.task(bind=True, max_retries=3, name="run_agent_task")
def run_agent_task(self, agent_id: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Run a single agent in the background.
    Returns the AgentResult as a dict.
    """
    import asyncio
    
    if context is None:
        context = {}
    
    try:
        registry = get_registry()
        agent = registry.get(agent_id)
        if not agent:
            return {"error": f"Agent {agent_id} not found", "status": "failed"}
        
        # Run async agent in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(agent.run(context))
            return result.to_dict()
        finally:
            loop.close()
            
    except Exception as exc:
        logger.error(f"Agent task {agent_id} failed: {exc}")
        self.retry(exc=exc, countdown=10)


@celery_app.task(bind=True, max_retries=2, name="run_pipeline_task")
def run_pipeline_task(self, mode: str = "full", phase: Optional[str] = None,
                      agent_ids: Optional[List[str]] = None,
                      context: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Run the full pipeline or a specific phase in the background.
    Returns aggregated results from all executed agents.
    """
    import asyncio
    
    if context is None:
        context = {}
    
    try:
        registry = get_registry()
        orch = registry.get("agent-027-orchestrator")
        if not orch:
            return {"error": "Orchestrator not available", "status": "failed"}
        
        ctx = dict(context)
        ctx["mode"] = mode
        if phase:
            ctx["phase"] = phase
        if agent_ids:
            ctx["agent_ids"] = agent_ids
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(orch.run(ctx))
            return result.to_dict()
        finally:
            loop.close()
            
    except Exception as exc:
        logger.error(f"Pipeline task failed: {exc}")
        self.retry(exc=exc, countdown=10)


@celery_app.task(bind=True, max_retries=3, name="process_tender_bundle_task")
def process_tender_bundle_task(self, tender_id: str, file_paths: Dict[str, str],
                                sor_agency: str = "BWDB", zone: Optional[str] = None) -> Dict[str, Any]:
    """
    Process a full tender bundle in the background.
    """
    import asyncio
    
    try:
        from app.services.tender_bundle import tender_bundle_processor
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                tender_bundle_processor.process_from_paths(
                    tender_id=tender_id,
                    file_paths=file_paths,
                    sor_agency=sor_agency,
                    zone=zone,
                )
            )
            return result
        finally:
            loop.close()
            
    except Exception as exc:
        logger.error(f"Bundle task {tender_id} failed: {exc}")
        self.retry(exc=exc, countdown=10)
