"""
Procurement Flow Specialist BD — Pipeline Celery Tasks
Dedicated background tasks for running the 27-agent pipeline phases.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from pathlib import Path

from app.celery_app import celery_app
from app.agents import AgentRegistry

logger = logging.getLogger("procureflow.tasks.pipeline")


def ensure_registry():
    """Ensure agents are registered in the worker process."""
    registry = AgentRegistry()
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
    return registry


@celery_app.task(bind=True, max_retries=2, name="pipeline_discovery")
def pipeline_discovery(self, context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Run Discovery phase: Agents 1-3 (Tender Radar, Acquisition, Corrigendum)."""
    if context is None:
        context = {}
    results = []
    registry = ensure_registry()
    
    for agent_id in ["agent-001-tender-radar", "agent-002-tender-acquisition", "agent-003-corrigendum-watchdog"]:
        try:
            agent = registry.get(agent_id)
            if agent:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(agent.run(context))
                    results.append(result.to_dict())
                finally:
                    loop.close()
        except Exception as e:
            results.append({"agent_id": agent_id, "error": str(e), "status": "failed"})
    
    return results


@celery_app.task(bind=True, max_retries=2, name="pipeline_intelligence")
def pipeline_intelligence(self, context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Run Intelligence phase: Agents 4-6."""
    if context is None:
        context = {}
    results = []
    registry = ensure_registry()
    
    for agent_id in ["agent-004-document-ai", "agent-005-boq-intelligence", "agent-006-spec-intelligence"]:
        try:
            agent = registry.get(agent_id)
            if agent:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(agent.run(context))
                    results.append(result.to_dict())
                finally:
                    loop.close()
        except Exception as e:
            results.append({"agent_id": agent_id, "error": str(e), "status": "failed"})
    
    return results


@celery_app.task(bind=True, max_retries=2, name="pipeline_evaluation")
def pipeline_evaluation(self, context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Run Evaluation phase: Agents 7-10."""
    if context is None:
        context = {}
    results = []
    registry = ensure_registry()
    
    for agent_id in ["agent-007-eligibility-compliance", "agent-008-risk-intelligence",
                      "agent-009-ppr-evaluation", "agent-010-lert-prediction"]:
        try:
            agent = registry.get(agent_id)
            if agent:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(agent.run(context))
                    results.append(result.to_dict())
                finally:
                    loop.close()
        except Exception as e:
            results.append({"agent_id": agent_id, "error": str(e), "status": "failed"})
    
    return results


@celery_app.task(bind=True, max_retries=2, name="pipeline_pricing")
def pipeline_pricing(self, context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Run Pricing phase: Agents 11-12."""
    if context is None:
        context = {}
    results = []
    registry = ensure_registry()
    
    for agent_id in ["agent-011-rate-analysis", "agent-012-market-rate-intelligence"]:
        try:
            agent = registry.get(agent_id)
            if agent:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(agent.run(context))
                    results.append(result.to_dict())
                finally:
                    loop.close()
        except Exception as e:
            results.append({"agent_id": agent_id, "error": str(e), "status": "failed"})
    
    return results


@celery_app.task(bind=True, max_retries=2, name="pipeline_competitor")
def pipeline_competitor(self, context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Run Competitor phase: Agents 13-17."""
    if context is None:
        context = {}
    results = []
    registry = ensure_registry()
    
    for agent_id in ["agent-013-competitor-intelligence", "agent-014-award-intelligence",
                      "agent-015-competitor-pricing-predictor", "agent-016-win-probability",
                      "agent-017-bid-position-optimizer"]:
        try:
            agent = registry.get(agent_id)
            if agent:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(agent.run(context))
                    results.append(result.to_dict())
                finally:
                    loop.close()
        except Exception as e:
            results.append({"agent_id": agent_id, "error": str(e), "status": "failed"})
    
    return results


@celery_app.task(bind=True, max_retries=2, name="pipeline_decision")
def pipeline_decision(self, context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Run Decision phase: Agents 18-21."""
    if context is None:
        context = {}
    results = []
    registry = ensure_registry()
    
    for agent_id in ["agent-018-ai-bid-assistant", "agent-019-resource-capacity",
                      "agent-021-financial-intelligence", "agent-022-executive-decision"]:
        try:
            agent = registry.get(agent_id)
            if agent:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(agent.run(context))
                    results.append(result.to_dict())
                finally:
                    loop.close()
        except Exception as e:
            results.append({"agent_id": agent_id, "error": str(e), "status": "failed"})
    
    return results


@celery_app.task(bind=True, max_retries=2, name="pipeline_reporting")
def pipeline_reporting(self, context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Run Reporting phase: Agent 24."""
    if context is None:
        context = {}
    results = []
    registry = ensure_registry()
    
    agent = registry.get("agent-023-report-generation")
    if agent:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(agent.run(context))
            results.append(result.to_dict())
        finally:
            loop.close()
    
    return results
