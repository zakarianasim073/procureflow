"""
Procurement Flow Specialist BD — Server Entry Point
FastAPI server exposing the agent system as a REST API.
"""

import logging
import sys
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import (
    AgentRegistry,
    WorkflowOrchestrator,
    TenderRadarAgent,
    TenderAcquisitionAgent,
    CorrigendumWatchdogAgent,
    DocumentAIAgent,
    BOQIntelligenceAgent,
    SpecIntelligenceAgent,
    EligibilityComplianceAgent,
    RiskIntelligenceAgent,
    PPREvaluationAgent,
    LERTPredictionAgent,
    RateAnalysisAgent,
    MarketRateIntelligenceAgent,
    CompetitorIntelligenceAgent,
    AwardIntelligenceAgent,
    SyndicateRadarAgent,
    RABillPredictorAgent,
    CompetitorPricingPredictorAgent,
    WinProbabilityAgent,
    BidPositionOptimizerAgent,
    AIBidAssistantAgent,
    ResourceCapacityAgent,
    FinancialIntelligenceAgent,
    ExecutiveDecisionAgent,
    EGPRateFillAgent,
    SubmissionValidationAgent,
    ReportGenerationAgent,
    KnowledgeLakeAgent,
    LearningAgent,
    VisionIntelligenceAgent,
)
from ..config import config

logger = logging.getLogger("procureflow.server")

registry = AgentRegistry()

def register_all_agents():
    if registry.count:
        return
    agents = [
        TenderRadarAgent(), TenderAcquisitionAgent(), CorrigendumWatchdogAgent(),
        DocumentAIAgent(), BOQIntelligenceAgent(), SpecIntelligenceAgent(),
        EligibilityComplianceAgent(), RiskIntelligenceAgent(), PPREvaluationAgent(),
        LERTPredictionAgent(), RateAnalysisAgent(), MarketRateIntelligenceAgent(),
        CompetitorIntelligenceAgent(), AwardIntelligenceAgent(), CompetitorPricingPredictorAgent(),
        WinProbabilityAgent(), BidPositionOptimizerAgent(), AIBidAssistantAgent(),
        ResourceCapacityAgent(), FinancialIntelligenceAgent(), ExecutiveDecisionAgent(),
        EGPRateFillAgent(), SubmissionValidationAgent(), ReportGenerationAgent(),
        KnowledgeLakeAgent(), LearningAgent(), SyndicateRadarAgent(), RABillPredictorAgent(),
        VisionIntelligenceAgent(), WorkflowOrchestrator(),
    ]
    registry.register_many(*agents)
    logger.info(f"Registered {len(agents)} agents")

app = FastAPI(
    title="Procurement Flow Specialist BD API",
    version=config.version,
    description="AI Tender Operating System — 30 Agent Registry & Orchestration",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup_register_agents():
    register_all_agents()

@app.get("/")
async def root():
    return {"app": config.app_name, "version": config.version, "environment": config.environment}

@app.get("/api/health")
async def health():
    return {"status": "healthy", "app": config.app_name, "version": config.version, "agents_registered": registry.count}

@app.get("/api/agents")
async def list_agents():
    return {"total": registry.count, "agents": registry.list_agents()}

@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    agent = registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return agent.info()

@app.post("/api/agents/{agent_id}/run")
async def run_agent(agent_id: str, context: Dict[str, Any] = {}):
    result = await registry.run_agent(agent_id, context)
    if result.status.value == "failed":
        raise HTTPException(status_code=500, detail=result.to_dict())
    return result.to_dict()

@app.post("/api/pipeline/run")
async def run_pipeline(request: Dict[str, Any]):
    orch = registry.get("agent-027-orchestrator")
    if not orch:
        raise HTTPException(status_code=500, detail="Orchestrator not found")
    ctx = request.get("context", {})
    ctx["mode"] = request.get("mode", "full")
    if request.get("phase"): ctx["phase"] = request["phase"]
    if request.get("agent_ids"): ctx["agent_ids"] = request["agent_ids"]
    result = await orch.run(ctx)
    return result.to_dict()

@app.get("/api/system/status")
async def system_status():
    orch = registry.get("agent-027-orchestrator")
    if not isinstance(orch, WorkflowOrchestrator):
        raise HTTPException(status_code=500, detail="Orchestrator not available")
    return await orch.system_status()

@app.get("/api/pipeline/phases")
async def list_phases():
    from .orchestrator import PIPELINE_DEFINITION, PipelinePhase
    return {
        "phases": {
            p.value: {"agents": PIPELINE_DEFINITION[p], "count": len(PIPELINE_DEFINITION[p])}
            for p in PipelinePhase
        }
    }

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG if config.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    uvicorn.run("app.agents.server:app", host=config.host, port=config.port, reload=config.debug)
