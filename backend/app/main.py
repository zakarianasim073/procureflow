"""
Procurement Flow Specialist BD — Unified API Server
Combines BOQ/SOR comparison engine with 30-Agent Enterprise Operating System.
"""

import json
import logging
import os
import socket
import sys
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import Request, FastAPI, HTTPException, Depends
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

# ── Agent System ──────────────────────────────────────────────────────────
# ── Ollama ─────────────────────────────────────────────────────────────────
from app.core.ollama_client import OllamaClient

from app.agents import (
    AgentRegistry,
    AgentBrain, BrainMessage, AgentCapability,
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
    WhatsAppAutomationAgent,
    PPR2025ComplianceAgent,
    VatTaxCalculatorAgent,
    TenderDocumentAgent,
    TenderPreparationAgent,
    # New agents from bidbrain2025 adaptation
    TenderPreScreenerAgent,
    DocumentPreparationAgent,
    TenderDashboardAgent,
    OpeningReportAgent,
    SORZoneMatcherAgent,
    BidNoBidAgent,
    ClientIntelligenceAgent,
    MoatSLTAnalyzerAgent,
    APPForecastAgent,
    PPR2025DashboardAgent,
    CompanyBrainAgent,
    MarketBrainAgent,
)

# ── v1 API Routers ────────────────────────────────────────────────────────
from app.api.v1 import auth, tenders, boq, sor, awards, competitors, dashboard, chat, epw3, escalation, market_index, intelligence, ppr2025, analytics, deptree, predictions, executive

# ── Core ──────────────────────────────────────────────────────────────────
from app.core.config import settings as boq_settings
from app.db.base import get_async_session
from app.core.helpers import ensure_dir
from app.core.security import get_current_user, get_optional_user

# ── SOR Service ───────────────────────────────────────────────────────────
from app.sor.sor_service import sor_service

logger = logging.getLogger("procureflow")


def _redis_broker_available() -> bool:
    broker_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        host_port = broker_url.split("://", 1)[-1].split("/", 1)[0]
        host, port_text = host_port.split(":", 1)
        with socket.create_connection((host, int(port_text)), timeout=1):
            return True
    except Exception:
        return False


async def _run_legacy_json_sync(app: FastAPI) -> None:
    from app.db.base import get_session_factory
    from app.services.intelligence_data_service import IntelligenceDataService, ImportProgress

    progress = ImportProgress()
    app.state.intelligence_import_status = progress

    try:
        sf = get_session_factory()
        async with sf() as session:
            svc = IntelligenceDataService(session)
            existing = await svc.get_import_counts()
            if existing.get("app_records", 0) > 0 and existing.get("awards", 0) > 0:
                progress.state = "completed"
                progress.started = True
                progress.current_phase = "skipped_existing_data"
                progress.summary = {"skipped": 1, **existing}
                regime_summary = await svc.backfill_tender_regimes()
                progress.summary["regime_backfill"] = regime_summary
                logger.info("✅ Legacy JSON sync skipped: PostgreSQL already populated (%s)", existing)
                return

            summary = await svc.import_existing_json_data(progress=progress)
            regime_summary = await svc.backfill_tender_regimes()
            summary["regime_backfill"] = regime_summary
        logger.info("✅ Legacy JSON sync complete: %s", summary)
    except asyncio.CancelledError:
        progress.state = "cancelled"
        progress.error = "cancelled"
        raise
    except Exception as e:
        progress.state = "failed"
        progress.error = str(e)
        logger.exception("❌ Legacy JSON sync failed")


async def _load_tender_snapshot(tender_id: str) -> Optional[Dict[str, Any]]:
    """Load a tender summary from PostgreSQL for endpoints that used JSON snapshots."""
    from sqlalchemy import select
    from app.db.base import get_session_factory
    from app.models.intelligence import ProcurementLifecycle, ProcurementTender, APPRecord
    from app.services.intelligence_data_service import IntelligenceDataService

    package_no = IntelligenceDataService.normalize_package_no(tender_id)
    sf = get_session_factory()
    async with sf() as session:
        lifecycle_result = await session.execute(
            select(ProcurementLifecycle)
            .where(ProcurementLifecycle.package_no == package_no)
            .order_by(ProcurementLifecycle.award_date.desc().nullslast())
        )
        lifecycle = lifecycle_result.scalars().first()
        if lifecycle:
            return {
                "tender_id": lifecycle.package_no,
                "title": lifecycle.title or "",
                "procuring_entity": lifecycle.pe_office or "",
                "deadline": lifecycle.award_date or "",
                "estimated_value_bdt": lifecycle.estimated_cost_bdt or 0,
                "detected_nature": lifecycle.procurement_method or "",
                "status": lifecycle.match_type or "",
            }

        app_result = await session.execute(
            select(ProcurementTender, APPRecord)
            .join(APPRecord, APPRecord.procurement_tender_id == ProcurementTender.id)
            .where(ProcurementTender.package_no == package_no)
        )
        row = app_result.first()
        if row:
            tender, app_record = row
            return {
                "tender_id": tender.package_no,
                "title": app_record.title or tender.title or "",
                "procuring_entity": tender.pe_office or "",
                "deadline": app_record.deadline or "",
                "estimated_value_bdt": app_record.estimated_cost_bdt or 0,
                "detected_nature": tender.procurement_method or "",
                "status": app_record.status or tender.match_type or "",
            }
    return None


async def _load_tender_overview(limit: int = 5000) -> List[Dict[str, Any]]:
    from app.db.base import get_session_factory
    from app.services.intelligence_data_service import IntelligenceDataService

    sf = get_session_factory()
    async with sf() as session:
        svc = IntelligenceDataService(session)
        result = await svc.query_lifecycle(limit=limit)
        return result["records"]


# ── Agent Registration ────────────────────────────────────────────────────

def register_all_agents(registry: AgentRegistry) -> AgentRegistry:
    """Register all 47 agents."""
    agents = [
        TenderRadarAgent(), TenderAcquisitionAgent(), CorrigendumWatchdogAgent(),
        TenderPreScreenerAgent(),
        DocumentAIAgent(), DocumentPreparationAgent(),
        BOQIntelligenceAgent(), SpecIntelligenceAgent(),
        EligibilityComplianceAgent(), RiskIntelligenceAgent(), PPREvaluationAgent(),
        LERTPredictionAgent(), PPR2025DashboardAgent(),
        RateAnalysisAgent(), MarketRateIntelligenceAgent(), SORZoneMatcherAgent(),
        CompetitorIntelligenceAgent(), AwardIntelligenceAgent(), CompetitorPricingPredictorAgent(),
        SyndicateRadarAgent(), MoatSLTAnalyzerAgent(), RABillPredictorAgent(),
        WinProbabilityAgent(), BidPositionOptimizerAgent(),
        APPForecastAgent(), ResourceCapacityAgent(),
        AIBidAssistantAgent(), FinancialIntelligenceAgent(), ExecutiveDecisionAgent(),
        BidNoBidAgent(), ClientIntelligenceAgent(),
        EGPRateFillAgent(), VatTaxCalculatorAgent(),
        SubmissionValidationAgent(),
        TenderDocumentAgent(), TenderPreparationAgent(), TenderDashboardAgent(), OpeningReportAgent(),
        ReportGenerationAgent(),
        KnowledgeLakeAgent(), CompanyBrainAgent(), MarketBrainAgent(),
        LearningAgent(),
        VisionIntelligenceAgent(),
        WhatsAppAutomationAgent(),
        PPR2025ComplianceAgent(),
        WorkflowOrchestrator(),
    ]
    registry.register_many(*agents)
    logger.info(f"Registered {registry.count} agents")
    return registry


def get_registry() -> AgentRegistry:
    return AgentRegistry()


# ── App Lifespan ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    logger.info(f"🚀 Starting {boq_settings.APP_NAME} v{boq_settings.VERSION}")
    
    # Ensure directories
    for d in ['uploads', 'outputs', 'data', 'tenders']:
        ensure_dir(f"{boq_settings.BASE_DIR}/{d}")
    
    # Initialize database
    try:
        from app.db.base import init_db
        await init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database init failed: {e}")
        raise

    # Load SOR service data (from PostgreSQL if available, else CSV)
    sor_service.load_all(prefer_db=True)

    # Register agents
    registry = AgentRegistry()
    register_all_agents(registry)

    yield
    
    # Shutdown
    try:
        from app.db.base import close_db
        await close_db()
    except Exception:
        pass


# ── Create App ────────────────────────────────────────────────────────────

app = FastAPI(
    title="Procurement Flow Specialist BD API",
    version=boq_settings.VERSION,
    description="AI Tender Operating System — BOQ/SOR Engine + registry-backed agent orchestration",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=boq_settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Include v1 Routers (under /api) ──────────────────────────────────────

from fastapi import APIRouter as _APIRouter
_api_router = _APIRouter(prefix="/api")
_api_router.include_router(auth.router)
_api_router.include_router(tenders.router)
_api_router.include_router(boq.router)
_api_router.include_router(sor.router)
_api_router.include_router(awards.router)
_api_router.include_router(competitors.router)
_api_router.include_router(dashboard.router)
_api_router.include_router(chat.router)
_api_router.include_router(epw3.router)
_api_router.include_router(escalation.router)
_api_router.include_router(market_index.router)
_api_router.include_router(intelligence.router)   # PostgreSQL-backed intelligence API
_api_router.include_router(ppr2025.router)          # PPR 2025 Evaluation Dashboard
_api_router.include_router(analytics.router)        # Advanced Analytics Suite
_api_router.include_router(deptree.router)           # Department Tree Browser
_api_router.include_router(predictions.router)       # Bid Prediction & NPP
_api_router.include_router(executive.router)         # Executive Dashboard
app.include_router(_api_router)


# ── Static File Serving (SPA Frontend) ────────────────────────────────────

from fastapi.staticfiles import StaticFiles
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir, html=True), name="static")

# ── Root Endpoints ────────────────────────────────────────────────────────

@app.get("/")
async def root():
    import os
    static_file = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(static_file):
        from fastapi.responses import HTMLResponse
        with open(static_file, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return {
        "app": boq_settings.APP_NAME,
        "version": boq_settings.VERSION,
        "status": "running",
    }
    raise HTTPException(status_code=404)


# ── SLT Dashboard ───────────────────────────────────────────────────────────

@app.get("/api/slt/dashboard")
async def slt_dashboard():
    """Senior Leadership Team dashboard — aggregated executive view."""
    registry = AgentRegistry()
    agents = registry.list_agents()

    from app.services.bwdb_monitor import bwdb_monitor
    from app.services.monitor_config import monitor_config_service

    monitor_stats = {}
    try:
        ms = await bwdb_monitor.get_stats()
        if isinstance(ms, dict):
            monitor_stats = ms
    except Exception:
        pass

    embed_stats = {"available": False, "reason": "embedding dependencies unavailable"}
    try:
        from app.services.tender_embedding import tender_embedding_service

        es = tender_embedding_service.get_stats()
        if isinstance(es, dict):
            embed_stats = {"available": True, **es}
    except Exception:
        pass

    config = {}
    try:
        config = monitor_config_service.get_config()
    except Exception:
        pass

    alert_history = []
    try:
        alert_history = await bwdb_monitor.get_alert_history(limit=10)
    except Exception:
        pass

    pipeline_phases = {}
    from .agents.orchestrator import PipelinePhase, PIPELINE_DEFINITION
    for phase_name, phase in PipelinePhase.__members__.items():
        agent_ids = PIPELINE_DEFINITION.get(phase, [])
        registered = [a for a in agents if a["agent_id"] in agent_ids]
        pipeline_phases[phase.value] = {
            "total": len(agent_ids),
            "registered": len(registered),
            "agents": agent_ids,
        }

    return {
        "success": True,
        "slt": {
            "system": {
                "app": boq_settings.APP_NAME,
                "version": boq_settings.VERSION,
                "agents_total": len(agents),
                "agents_active": sum(1 for a in agents if a.get("status") in ("idle", "success", "ready")),
                "agents_idle": sum(1 for a in agents if a.get("status") in ("idle", "success", "ready")),
            },
            "pipeline_phases": pipeline_phases,
            "monitor": {
                "config": config,
                "stats": monitor_stats,
                "recent_alerts": alert_history[:5] if alert_history else [],
            },
            "embeddings": embed_stats,
            "total_tenders_monitored": monitor_stats.get("total_scanned", 0) or embed_stats.get("total_indexed", 0) or 0,
            "alerts_sent": len(alert_history) if alert_history else 0,
            "pipeline_ready": all(
                p["registered"] == p["total"] for p in pipeline_phases.values()
            ) if pipeline_phases else False,
        },
    }


# ── Agent System Endpoints ────────────────────────────────────────────────

@app.get("/api/agents")
async def list_agents():
    """List all registered agents."""
    registry = AgentRegistry()
    return {"total": registry.count, "agents": registry.list_agents()}


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get detailed info about a specific agent."""
    registry = AgentRegistry()
    agent = registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return agent.info()


@app.get("/api/agent-results/recent")
async def recent_agent_results(limit: int = 12, db=Depends(get_async_session)):
    """Return the most recent persisted agent runs for the UI."""
    from sqlalchemy import select
    from app.db import AgentResult as AgentResultModel

    rows = (
        await db.execute(
            select(AgentResultModel)
            .order_by(AgentResultModel.created_at.desc())
            .limit(max(1, min(limit, 50)))
        )
    ).scalars().all()

    return {
        "total": len(rows),
        "results": [
            {
                "run_id": row.id,
                "source": "database",
                "timestamp": row.created_at.isoformat() if row.created_at else "",
                "tender_id": row.tender_id or "",
                "agent_id": row.agent_id,
                "agent_name": row.agent_name or row.agent_id,
                "status": row.status,
                "output": row.output or {},
                "error": row.error or "",
                "execution_time_ms": row.execution_time_ms or 0,
            }
            for row in rows
        ],
    }


class WhatsAppAgentRunRequest(BaseModel):
    action: str = "send_summary"
    phone: str = ""
    message: str = ""
    tender_id: str = ""
    language: str = "bn"
    tenders: List[Dict[str, Any]] = []


class BrowserBridgeArtifact(BaseModel):
    name: str = ""
    url: str = ""
    type: str = ""
    mime_type: str = ""
    base64: str = ""
    text: str = ""


class TenderBrowserBridgeRequest(BaseModel):
    tender_id: str
    browser_capture: Dict[str, Any] = {}
    artifacts: List[BrowserBridgeArtifact] = []

@app.post("/api/agents/whatsapp-automation/run")
async def run_whatsapp_agent(req: WhatsAppAgentRunRequest, user: dict = Depends(get_current_user)):
    """Run WhatsApp Automation Agent (agent-031-whatsapp-automation)."""
    from app.agents.whatsapp_agent import WhatsAppAutomationAgent
    agent = WhatsAppAutomationAgent()
    context = {
        "action": req.action,
        "phone": req.phone,
        "message": req.message,
        "tender_id": req.tender_id,
        "language": req.language,
        "tenders": req.tenders,
    }
    result = await agent.run(context)
    return {"success": result.status.value == "success", "result": result.to_dict()}


@app.post("/api/agents/{agent_id}/run")
async def run_agent(agent_id: str, context: Dict[str, Any] = {}, user: dict = Depends(get_current_user)):
    """Execute a specific agent with context."""
    registry = AgentRegistry()
    result = await registry.run_agent(agent_id, context)
    if result.status.value == "failed":
        raise HTTPException(status_code=500, detail=result.to_dict())
    return result.to_dict()


@app.post("/api/agents/tender-acquisition/browser-bridge")
async def import_tender_acquisition_browser_bridge(req: TenderBrowserBridgeRequest, user: dict = Depends(get_current_user)):
    """Persist browser-captured authenticated tender artifacts into runtime storage."""
    from app.agents.discovery.tender_acquisition import TenderAcquisitionAgent

    agent = TenderAcquisitionAgent()
    result = agent.import_browser_bridge_artifacts(
        {
            "tender_id": req.tender_id,
            "browser_capture": req.browser_capture,
            "artifacts": [artifact.model_dump() for artifact in req.artifacts],
        }
    )
    return {"success": True, **result}


@app.get("/api/pipeline/phases")
async def list_pipeline_phases():
    """List all pipeline phases and their agents."""
    from app.agents.orchestrator import PIPELINE_DEFINITION, PipelinePhase
    return {
        "phases": {
            p.value: {
                "agents": PIPELINE_DEFINITION[p],
                "count": len(PIPELINE_DEFINITION[p]),
            }
            for p in PipelinePhase
        }
    }


@app.get("/api/system/status")
async def system_status():
    """Get full system status including orchestrator state."""
    registry = AgentRegistry()
    orch = registry.get("agent-027-orchestrator")
    if not isinstance(orch, WorkflowOrchestrator):
        raise HTTPException(status_code=500, detail="Orchestrator not available")
    return await orch.system_status()


@app.get("/api/repo/facts")
async def repo_facts():
    """Get live repository facts derived from config and runtime state."""
    from app.services.repo_facts import get_repo_facts
    return get_repo_facts()


# ── Tender Radar Endpoint ─────────────────────────────────────────────────

@app.get("/api/tender-radar")
async def get_tender_radar():
    """Get latest tender radar results (Agent 1)."""
    registry = AgentRegistry()
    radar = registry.get("agent-001-tender-radar")
    if not radar:
        raise HTTPException(status_code=404, detail="Tender Radar agent not found")
    
    # Run radar with default context
    result = await radar.run({})
    return result.to_dict()


# ── eGP Endpoints ─────────────────────────────────────────────────────────

@app.post("/api/agents/egp/login")
async def egp_login(credentials: Dict[str, str] = {}, user: dict = Depends(get_current_user)):
    """Test eGP portal login credentials."""
    from app.agents.egp_client import eGPClient
    
    email = credentials.get("email", os.getenv("EGP_EMAIL", ""))
    password = credentials.get("password", os.getenv("EGP_PASSWORD", ""))
    
    if not email or not password:
        raise HTTPException(status_code=400, detail="eGP credentials required")
    
    client = eGPClient(email=email, password=password)
    success = client.login()
    return {
        "success": success,
        "message": "Login successful" if success else "Login failed",
        "session_active": client.session.is_authenticated if success else False,
    }


@app.post("/api/agents/egp/search")
async def egp_search(query: Dict[str, Any] = {}, user: dict = Depends(get_current_user)):
    """Search tenders on eGP portal."""
    from app.agents.egp_client import eGPClient
    
    email = os.getenv("EGP_EMAIL", "")
    password = os.getenv("EGP_PASSWORD", "")
    tender_id = query.get("tender_id", "")
    
    if not email or not password:
        raise HTTPException(status_code=400, detail="eGP credentials not configured")
    
    client = eGPClient(email=email, password=password)
    
    # Login first
    if not client.login():
        raise HTTPException(status_code=401, detail="eGP login failed")
    
    # Search
    results = client.search_tenders(tender_id=tender_id)
    return {"success": True, "results": results}


# ── Ollama Agent Runner ───────────────────────────────────────────────────

ollama_client = OllamaClient()


@app.post("/api/agents/ollama-run")
async def ollama_agent_run(request: Dict[str, Any], user: dict = Depends(get_current_user)):
    """Run agents via natural language using Ollama for intent parsing."""
    prompt = request.get("prompt", "")
    language = request.get("language", "en")

    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    registry = AgentRegistry()
    ollama_available = await ollama_client.is_available()

    # If Ollama is available, use it to interpret the prompt and map to agent(s)
    if ollama_available:
        agent_list = registry.list_agents()
        agent_map = {a["agent_id"]: a for a in agent_list}
        agent_descriptions = "\n".join(
            [f"- {a['agent_id']}: {a['agent_name']} — {a['description']}" for a in agent_list]
        )

        system_prompt = (
            f"You are an agent orchestrator for Procurement Flow Specialist BD.\n"
            f"Available agents:\n{agent_descriptions}\n\n"
            f"Given the user's natural language request, determine the single most relevant agent_id to run. "
            f"If multiple agents are needed, pick the primary one. "
            f"Respond with ONLY a JSON object: {{\"agent_id\": \"...\", \"context\": {{key: value}}}}. "
            f"Do NOT include any other text. The context should include relevant parameters inferred from the prompt."
        )

        interpretation = await ollama_client.chat(
            messages=[{"role": "user", "content": prompt}],
            lang=language,
            system_override=system_prompt,
        )

        if interpretation.get("success"):
            import json as _json
            content = interpretation["content"]
            try:
                parsed = _json.loads(content.strip().strip("`").replace("json", "").strip())
                agent_id = parsed.get("agent_id", "")
                agent_context = parsed.get("context", {})
            except Exception:
                agent_id = ""
                agent_context = {}
        else:
            agent_id = ""
            agent_context = {}
    else:
        # No Ollama: do a simple keyword-to-agent mapping
        prompt_lower = prompt.lower()
        agent_map_simple = {
            "tender": "agent-001-tender-radar",
            "tender acquisition": "agent-002-tender-acquisition",
            "corrigendum": "agent-003-corrigendum-watchdog",
            "pre screen": "agent-038-tender-pre-screener",
            "pre-screen": "agent-038-tender-pre-screener",
            "tender pre": "agent-038-tender-pre-screener",
            "document": "agent-004-document-ai",
            "document prep": "agent-032-document-preparation",
            "boq": "agent-005-boq-intelligence",
            "spec": "agent-006-spec-intelligence",
            "eligibility": "agent-007-eligibility-compliance",
            "risk": "agent-008-risk-intelligence",
            "ppr": "agent-009-ppr-evaluation",
            "ppr dashboard": "agent-037-ppr2025-dashboard",
            "lert": "agent-010-lert-prediction",
            "rate analysis": "agent-011-rate-analysis",
            "rate": "agent-011-rate-analysis",
            "market rate": "agent-012-market-rate-intelligence",
            "sor zone": "agent-044-sor-zone-matcher",
            "zone matcher": "agent-044-sor-zone-matcher",
            "competitor": "agent-013-competitor-intelligence",
            "award": "agent-014-award-intelligence",
            "pricing": "agent-015-competitor-pricing-predictor",
            "moat": "agent-036-moat-slt-analyzer",
            "slt": "agent-036-moat-slt-analyzer",
            "win": "agent-016-win-probability",
            "bid position": "agent-017-bid-position-optimizer",
            "bid assistant": "agent-018-ai-bid-assistant",
            "resource": "agent-019-resource-capacity",
            "app forecast": "agent-042-app-forecast",
            "financial": "agent-021-financial-intelligence",
            "decision": "agent-022-executive-decision",
            "executive": "agent-022-executive-decision",
            "bid no bid": "agent-039-bid-no-bid",
            "no bid": "agent-039-bid-no-bid",
            "client intelligence": "agent-043-client-intelligence",
            "client intel": "agent-043-client-intelligence",
            "egp fill": "agent-020-egp-rate-fill",
            "rate fill": "agent-020-egp-rate-fill",
            "vat": "agent-033-vat-tax-calculator",
            "tax": "agent-033-vat-tax-calculator",
            "submission": "agent-024-submission-validation",
            "tender dashboard": "agent-035-tender-dashboard",
            "report": "agent-023-report-generation",
            "knowledge": "agent-025-knowledge-lake",
            "company brain": "agent-040-company-brain",
            "market brain": "agent-041-market-brain",
            "learn": "agent-026-learning",
            "orchestrator": "agent-027-orchestrator",
            "pipeline": "agent-027-orchestrator",
            "syndicate": "agent-028-syndicate-radar",
            "ra bill": "agent-030-ra-bill-predictor",
            "bill": "agent-030-ra-bill-predictor",
            "vision": "agent-029-vision-intelligence",
        }
        agent_id = ""
        for keyword, aid in agent_map_simple.items():
            if keyword in prompt_lower:
                agent_id = aid
                break
        if not agent_id:
            agent_id = "agent-027-orchestrator"
        agent_context = {"prompt": prompt}

    # Run the identified agent
    if not agent_id:
        return {
            "success": True,
            "prompt": prompt,
            "agent_id": None,
            "agent_name": None,
            "language": language,
            "ollama_available": False,
            "message": "Could not determine which agent to run. Try a more specific request.",
            "result": None,
        }

    agent = registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    agent_context["language"] = language
    agent_context["ollama_available"] = ollama_available
    result = await agent.run(agent_context)

    return {
        "success": True,
        "prompt": prompt,
        "agent_id": agent_id,
        "agent_name": agent.agent_name,
        "language": language,
        "ollama_available": ollama_available,
        "result": result.to_dict(),
        "interpretation": agent_context if not ollama_available else None,
    }


# ── SOR Legacy Endpoint ───────────────────────────────────────────────────

@app.get("/api/sor/legacy/stats")
async def sor_stats():
    """Get SOR loading statistics for all agencies."""
    agencies = {}
    for a in ['BWDB', 'PWD', 'LGED']:
        agencies[a] = sor_service.get_stats(a)
    return {"success": True, "agencies": agencies}


# ── Run ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    
    logging.basicConfig(
        level=logging.DEBUG if boq_settings.ENVIRONMENT == "development" else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    
    host = os.getenv("PROCUREFLOW_HOST", "0.0.0.0")
    port = int(os.getenv("PROCUREFLOW_PORT", "8000"))
    reload_enabled = os.getenv("PROCUREFLOW_RELOAD", "").strip().lower() in {"1", "true", "yes", "on"}
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload_enabled,
        log_level="info",
    )

# ── Celery Task Status Endpoints ─────────────────────────────────────────

@app.get("/api/pipeline/status/{task_id}")
async def get_task_status(task_id: str):
    """Poll Celery task status and result."""
    try:
        from app.celery_app import celery_app as celery
        result = celery.AsyncResult(task_id)
        
        response = {
            "task_id": task_id,
            "status": result.state,
            "ready": result.ready(),
        }
        
        if result.ready():
            if result.successful():
                response["result"] = result.get()
            else:
                response["error"] = str(result.result) if result.result else "Task failed"
        
        return response
        
    except Exception as e:
        return {"task_id": task_id, "status": "UNKNOWN", "error": str(e)}


@app.post("/api/pipeline/run-async")
async def run_pipeline_async(request: Dict[str, Any], user: dict = Depends(get_current_user)):
    """
    Run pipeline in the background via Celery.
    Returns task_id immediately — poll /api/pipeline/status/{task_id} for result.
    """
    from app.workers.tasks import run_pipeline_task

    if not _redis_broker_available():
        raise HTTPException(status_code=503, detail="Redis/Celery broker is unavailable")
    
    mode = request.get("mode", "full")
    phase = request.get("phase")
    agent_ids = request.get("agent_ids")
    context = request.get("context", {})
    
    task = run_pipeline_task.delay(mode=mode, phase=phase,
                                    agent_ids=agent_ids, context=context)
    
    return {
        "success": True,
        "task_id": task.id,
        "status_url": f"/api/pipeline/status/{task.id}",
        "message": "Pipeline started in background",
    }


@app.post("/api/pipeline/run")
async def run_pipeline(request: Dict[str, Any] = {}, user: dict = Depends(get_current_user)):
    mode = request.get("mode", "full")
    phase = request.get("phase")
    agent_ids = request.get("agent_ids")
    context = request.get("context", {})
    if _redis_broker_available():
        from app.workers.tasks import run_pipeline_task

        task = run_pipeline_task.delay(mode=mode, phase=phase, agent_ids=agent_ids, context=context)
        return {
            "success": True,
            "task_id": task.id,
            "status": "queued",
            "mode": mode,
            "status_url": f"/api/pipeline/status/{task.id}",
            "message": "Pipeline started in background",
        }

    registry = AgentRegistry()
    orch = registry.get("agent-027-orchestrator")
    if not orch:
        raise HTTPException(status_code=500, detail="Orchestrator not available")

    sync_context = dict(context)
    sync_context["mode"] = mode
    if phase:
        sync_context["phase"] = phase
    if agent_ids:
        sync_context["agent_ids"] = agent_ids

    result = await orch.run(sync_context)
    return {
        "success": True,
        "status": "completed_sync",
        "mode": mode,
        "message": "Pipeline executed synchronously because Redis/Celery is unavailable",
        "result": result.to_dict() if hasattr(result, "to_dict") else result,
    }


@app.post("/api/agents/{agent_id}/run-async")
async def run_agent_async(agent_id: str, context: Dict[str, Any] = {}, user: dict = Depends(get_current_user)):
    """
    Run a single agent in the background via Celery.
    Returns task_id immediately.
    """
    from app.workers.tasks import run_agent_task

    if not _redis_broker_available():
        raise HTTPException(status_code=503, detail="Redis/Celery broker is unavailable")
    
    task = run_agent_task.delay(agent_id=agent_id, context=context)
    
    return {
        "success": True,
        "task_id": task.id,
        "status_url": f"/api/pipeline/status/{task.id}",
        "message": f"Agent {agent_id} started in background",
    }


@app.get("/api/opening-reports")
async def list_opening_reports(limit: int = 50):
    """Return a lightweight list of opening reports for the live UI."""
    from sqlalchemy import select
    from app.db.base import get_session_factory
    from app.db.models import OpeningReport

    sf = get_session_factory()
    async with sf() as session:
        rows = (
            await session.execute(
                select(OpeningReport)
                .order_by(OpeningReport.opening_date.desc().nullslast(), OpeningReport.created_at.desc())
                .limit(max(1, min(limit, 200)))
            )
        ).scalars().all()

    return {
        "success": True,
        "total": len(rows),
        "items": [
            {
                "id": row.id,
                "tender_id": row.tender_id,
                "opening_date": row.opening_date.isoformat() if row.opening_date else None,
                "pe_office": row.pe_office,
                "agency": row.agency,
                "zone": row.zone,
                "winner_name": row.winner_name,
                "winner_amount": float(row.winner_amount or 0),
                "has_slt": bool(row.has_slt),
                "has_alt": bool(row.has_alt),
                "bidders_count": len(row.bidders or []),
                "source_pdf": row.source_pdf,
            }
            for row in rows
        ],
    }


@app.post("/api/tender/{tender_id}/process-with-agents")
async def process_tender_with_agents(tender_id: str,
                                      sor_agency: str = "BWDB",
                                      zone: str = None):
    """
    Run the full agent pipeline for a tender, then generate documents.
    Works even without pre-uploaded documents (agents run in demo mode).
    """
    from app.services.tender_manager import tender_manager
    from app.services.tender_bundle import tender_bundle_processor

    # Gather any stored file paths (may be empty — ok)
    file_paths = {}
    for doc_type in ['notice', 'tds', 'tds_2', 'boq', 'sor']:
        try:
            path = tender_manager.get_document_path(tender_id, doc_type)
            if path and Path(path).exists():
                file_paths[doc_type] = path
        except Exception:
            pass

    # Also scan uploads directory for this tender
    upload_dir = Path(boq_settings.BASE_DIR) / "uploads"
    if upload_dir.exists():
        for f in upload_dir.iterdir():
            if tender_id in f.stem:
                for doc_type in ['notice', 'tds', 'tds_2', 'boq', 'sor']:
                    if doc_type.lower() in f.stem.lower() or f.suffix in ['.pdf', '.xlsx', '.xls']:
                        if doc_type not in file_paths:
                            file_paths[doc_type] = str(f)

    # Run agent pipeline
    registry = AgentRegistry()
    orch = registry.get("agent-027-orchestrator")
    if not orch:
        raise HTTPException(status_code=500, detail="Orchestrator not available")

    pipeline_result = await orch.run({
        "mode": "full",
        "tender_id": tender_id,
        "file_paths": file_paths,
    })

    # Collect agent outputs from pipeline result
    agent_outputs = {}
    if hasattr(orch, '_phase_results') and orch._phase_results:
        for phase_name, phase_data in orch._phase_results.items():
            agent_results = phase_data.get("agent_results", {})
            for aid, r in agent_results.items():
                output = getattr(r, 'output', None) if hasattr(r, 'output') else (r.get("output") if isinstance(r, dict) else None)
                if output:
                    agent_outputs[aid] = output

    # Generate documents if we have at least some files
    doc_result = None
    if file_paths:
        try:
            doc_result = await tender_bundle_processor.process_from_paths(
                tender_id=tender_id,
                file_paths=file_paths,
                sor_agency=sor_agency,
                zone=zone,
                agent_outputs=agent_outputs,
            )
        except Exception as e:
            logger.warning(f"Document generation skipped: {e}")
            doc_result = {"success": False, "error": str(e)}
    else:
        doc_result = {
            "success": False,
            "message": "No tender documents uploaded yet. Upload via /upload page first, then re-run.",
            "note": "Agents still ran with the tender ID for intelligence gathering.",
        }

    return {
        "success": True,
        "tender_id": tender_id,
        "pipeline_result": pipeline_result.to_dict(),
        "documents": doc_result,
        "agent_outputs": agent_outputs,
    }


@app.post("/api/tender/{tender_id}/process-async")
async def process_tender_async(tender_id: str,
                                sor_agency: str = "BWDB",
                                zone: str = None):
    """Process a tender bundle in the background via Celery."""
    from app.workers.tasks import process_tender_bundle_task
    
    # Gather file paths
    from app.services.tender_manager import tender_manager
    file_paths = {}
    for doc_type in ['notice', 'tds', 'tds_2', 'boq']:
        path = tender_manager.get_document_path(tender_id, doc_type)
        if path:
            file_paths[doc_type] = path
    
    if not file_paths:
        from fastapi import Request, HTTPException
        raise HTTPException(status_code=404, detail="No documents found for this tender")
    
    task = process_tender_bundle_task.delay(
        tender_id=tender_id,
        file_paths=file_paths,
        sor_agency=sor_agency,
        zone=zone,
    )
    
    return {
        "success": True,
        "task_id": task.id,
        "status_url": f"/api/pipeline/status/{task.id}",
    }

# ── Notification / Alert Endpoints ───────────────────────────────────────

from app.services.notification_service import notification_service, TenderAlert


@app.get("/api/alerts")
async def get_alerts(limit: int = 20, alert_type: str = None):
    """Get recent tender alerts."""
    alerts = notification_service.get_alerts(limit=limit, alert_type=alert_type)
    return {"success": True, "total": len(alerts), "alerts": alerts}


@app.delete("/api/alerts/clear")
async def clear_alerts(older_than_days: int = 30):
    """Clear old alerts."""
    cleared = notification_service.clear_alerts(older_than_days=older_than_days)
    return {"success": True, "cleared": cleared}


@app.post("/api/alerts/test-email")
async def test_email_alert(request: Dict[str, str]):
    """Send a test email alert."""
    email = request.get("email", "")
    if not email:
        from fastapi import Request, HTTPException
        raise HTTPException(status_code=400, detail="Email required")
    
    alert = TenderAlert(
        tender_id="TEST-001",
        title="Test Alert from Procurement Flow Specialist BD",
        procuring_entity="Test Entity",
        match_score=0.95,
        estimated_value=10_000_000,
        deadline="2026-07-01",
        alert_type="new_tender",
    )
    
    sent = notification_service.send_tender_alert_email(email, alert)
    return {"success": sent, "message": "Test email sent" if sent else "Email not configured"}


# ── SMTP / Email Settings Endpoints ─────────────────────────────────────

class SMTPSettings(BaseModel):
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_pass: Optional[str] = None
    smtp_from: Optional[str] = None
    alert_email: Optional[str] = None

@app.get("/api/settings/smtp")
async def get_smtp_settings():
    """Get current SMTP config (password masked)."""
    from app.services.notification_service import notification_service
    ns = notification_service
    return {
        "smtp_host": ns.smtp_host or os.getenv("SMTP_HOST", ""),
        "smtp_port": ns.smtp_port or int(os.getenv("SMTP_PORT", "587")),
        "smtp_user": ns.smtp_user or os.getenv("SMTP_USER", ""),
        "smtp_pass": "••••••••" if (ns.smtp_pass or os.getenv("SMTP_PASS", "")) else "",
        "smtp_from": ns.from_email or os.getenv("NOTIFICATION_FROM", "alerts@procureflow.ai"),
        "alert_email": os.getenv("ALERT_EMAIL", ""),
        "configured": bool(ns.smtp_host and ns.smtp_pass) or bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_PASS")),
    }

@app.post("/api/settings/smtp")
async def update_smtp_settings(settings: SMTPSettings):
    """Update SMTP configuration (in-memory for current session)."""
    from app.services.notification_service import notification_service
    ns = notification_service

    # Update notification_service instance
    if settings.smtp_host is not None:
        ns.smtp_host = settings.smtp_host
        os.environ["SMTP_HOST"] = settings.smtp_host
    if settings.smtp_port is not None:
        ns.smtp_port = settings.smtp_port
        os.environ["SMTP_PORT"] = str(settings.smtp_port)
    if settings.smtp_user is not None:
        ns.smtp_user = settings.smtp_user
        os.environ["SMTP_USER"] = settings.smtp_user
    if settings.smtp_pass is not None:
        ns.smtp_pass = settings.smtp_pass
        os.environ["SMTP_PASS"] = settings.smtp_pass
    if settings.smtp_from is not None:
        ns.from_email = settings.smtp_from
    if settings.alert_email is not None:
        os.environ["ALERT_EMAIL"] = settings.alert_email

    # Try to persist to backend/.env
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
            new_lines = []
            updated_keys = set()
            for line in lines:
                stripped = line.strip()
                key_updated = False
                for key, val in [
                    ("SMTP_HOST", settings.smtp_host),
                    ("SMTP_PORT", str(settings.smtp_port) if settings.smtp_port else None),
                    ("SMTP_USER", settings.smtp_user),
                    ("SMTP_PASS", settings.smtp_pass),
                ]:
                    if val is not None and stripped.startswith(f"{key}="):
                        new_lines.append(f"{key}={val}")
                        updated_keys.add(key)
                        key_updated = True
                        break
                if not key_updated:
                    new_lines.append(line)
            # Add any missing keys
            for key, val in [
                ("SMTP_HOST", settings.smtp_host),
                ("SMTP_PORT", str(settings.smtp_port) if settings.smtp_port else None),
                ("SMTP_USER", settings.smtp_user),
                ("SMTP_PASS", settings.smtp_pass),
                ("ALERT_EMAIL", settings.alert_email),
            ]:
                if val is not None and key not in updated_keys and key != "SMTP_PORT":
                    new_lines.append(f"{key}={val}")
                    updated_keys.add(key)
            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not persist .env: {e}")

    return {"success": True, "message": "SMTP settings updated"}


class TestEmailRequest(BaseModel):
    email: str

@app.post("/api/settings/smtp/test")
async def test_smtp_settings(req: TestEmailRequest):
    """Send a test email using current SMTP settings."""
    from app.services.notification_service import notification_service
    ns = notification_service

    if not ns.smtp_host:
        return {"success": False, "message": "SMTP not configured — set host and credentials first"}
    if not ns.smtp_pass:
        return {"success": False, "message": "SMTP password (App Password) not set"}

    import smtplib
    from email.mime.text import MIMEText
    try:
        msg = MIMEText(
            "<html><body><h2>Procurement Flow — Test Email</h2>"
            "<p>Your SMTP/Gmail App Password configuration is working!</p>"
            "<hr><p style='color:#666;font-size:12px'>Procurement Flow Specialist BD</p>"
            "</body></html>",
            "html",
        )
        msg["Subject"] = "Procurement Flow — SMTP Test Successful"
        msg["From"] = ns.from_email
        msg["To"] = req.email

        with smtplib.SMTP(ns.smtp_host, int(ns.smtp_port or 587)) as server:
            server.starttls()
            server.login(ns.smtp_user, ns.smtp_pass)
            server.send_message(msg)

        return {"success": True, "message": f"Test email sent to {req.email}"}
    except smtplib.SMTPAuthenticationError:
        return {"success": False, "message": "Authentication failed. Use a 16-char Gmail App Password (not your regular password). Generate one at https://myaccount.google.com/apppasswords"}
    except smtplib.SMTPException as e:
        return {"success": False, "message": f"SMTP error: {e}"}
    except Exception as e:
        return {"success": False, "message": f"Failed: {e}"}


# ── WhatsApp Notification Endpoints ────────────────────────────────────

@app.get("/api/whatsapp/settings")
async def get_whatsapp_settings():
    """Get WhatsApp configuration."""
    from app.services.whatsapp_service import whatsapp_service
    phone = os.getenv("WHATSAPP_PHONE", whatsapp_service.default_phone)
    return {
        "phone": phone,
        "configured": bool(phone),
    }

@app.post("/api/whatsapp/settings")
async def update_whatsapp_settings(req: Dict[str, str]):
    """Update WhatsApp phone number."""
    phone = req.get("phone", "")
    if phone:
        os.environ["WHATSAPP_PHONE"] = phone
        from app.services.whatsapp_service import whatsapp_service
        whatsapp_service.default_phone = phone
        # Persist to .env
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            try:
                lines = env_path.read_text(encoding="utf-8").splitlines()
                found = False
                new_lines = []
                for line in lines:
                    if line.strip().startswith("WHATSAPP_PHONE="):
                        new_lines.append(f"WHATSAPP_PHONE={phone}")
                        found = True
                    else:
                        new_lines.append(line)
                if not found:
                    new_lines.append(f"\n# WhatsApp\nWHATSAPP_PHONE={phone}")
                env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            except Exception as e:
                logger.warning(f"Could not persist WhatsApp phone: {e}")
    return {"success": True, "phone": phone}

class WhatsAppTenderRequest(BaseModel):
    tender_id: str = ""
    phone: str = ""
    language: str = "bn"

@app.post("/api/whatsapp/share-tender")
async def share_tender_via_whatsapp(req: WhatsAppTenderRequest):
    """Generate WhatsApp share link for a tender."""
    from app.services.whatsapp_service import whatsapp_service

    tender = await _load_tender_snapshot(req.tender_id) if req.tender_id else None

    if not tender:
        tender = {"tender_id": req.tender_id or "unknown", "title": "", "procuring_entity": ""}

    link = whatsapp_service.get_tender_wa_link(tender, phone=req.phone, lang=req.language)
    msg = whatsapp_service.format_tender_alert(tender, lang=req.language)
    return {
        "success": True,
        "wa_link": link,
        "message": msg,
        "phone": req.phone or whatsapp_service.default_phone,
    }

@app.post("/api/whatsapp/share-summary")
async def share_summary_via_whatsapp(req: Dict[str, Any]):
    """Generate WhatsApp share link for a summary of tenders."""
    from app.services.whatsapp_service import whatsapp_service
    tenders = req.get("tenders", [])
    phone = req.get("phone", "")
    lang = req.get("language", "bn")

    link = whatsapp_service.get_summary_wa_link(tenders, phone=phone, lang=lang)
    msg = whatsapp_service.format_summary(tenders, lang=lang)
    return {
        "success": True,
        "wa_link": link,
        "message": msg,
        "count": len(tenders),
    }

@app.get("/api/whatsapp/alerts")
async def get_whatsapp_alerts(limit: int = 20):
    """Get recent WhatsApp alerts."""
    from app.services.whatsapp_service import whatsapp_service
    alerts = whatsapp_service.get_recent_alerts(limit=limit)
    return {"success": True, "alerts": alerts}


# ── WhatsApp Automation with OpenClaw ─────────────────────────────────

class WhatsAppSendRequest(BaseModel):
    phone: str = ""
    message: str = ""
    tender_id: str = ""
    language: str = "bn"

@app.get("/api/whatsapp/automation/status")
async def whatsapp_automation_status():
    """Check WhatsApp automation status (OpenClaw + WhatsApp login)."""
    from app.services.whatsapp_automation import whatsapp_automation
    try:
        status = await asyncio.wait_for(whatsapp_automation.check_login_status(), timeout=5)
    except Exception:
        status = {"openclaw_available": False, "logged_in": False}
    return {
        "success": True,
        "openclaw_available": status.get("openclaw_available", False),
        "whatsapp_logged_in": status.get("logged_in", False),
        "phone": os.getenv("WHATSAPP_PHONE", ""),
    }

@app.post("/api/whatsapp/automation/send")
async def whatsapp_automation_send(req: WhatsAppSendRequest):
    """Send a WhatsApp message via OpenClaw browser automation."""
    from app.services.whatsapp_automation import whatsapp_automation
    from app.services.whatsapp_service import whatsapp_service

    if req.tender_id:
        try:
            tender = await _load_tender_snapshot(req.tender_id)
            if tender:
                result = await whatsapp_automation.send_tender_alert(tender, phone=req.phone, lang=req.language)
                return {"success": result["success"], "method": result.get("method", "wa_link"), "result": result}
        except Exception as e:
            logger.warning(f"Tender lookup failed: {e}")

    if req.message:
        phone = req.phone or os.getenv("WHATSAPP_PHONE", "")
        result = await whatsapp_automation.send_message(phone, req.message)
        return {"success": result["success"], "method": result.get("method", "wa_link"), "result": result}

    return {"success": False, "error": "Provide message or tender_id"}

@app.post("/api/whatsapp/automation/send-batch")
async def whatsapp_automation_send_batch(req: Dict[str, Any]):
    """Send batch tender alerts via OpenClaw."""
    from app.services.whatsapp_automation import whatsapp_automation
    tenders = req.get("tenders", [])
    phone = req.get("phone", "")
    lang = req.get("language", "bn")
    if not tenders:
        return {"success": False, "error": "No tenders provided"}
    result = await whatsapp_automation.send_batch_alerts(tenders, phone=phone, lang=lang)
    return {"success": True, "result": result}


# ── OpenClaw Browser Management Endpoints ─────────────────────────────

@app.get("/api/openclaw/status")
async def openclaw_status():
    """Check OpenClaw availability."""
    from app.services.openclaw_client import openclaw_client
    available = await openclaw_client.is_available()
    return {
        "success": True,
        "available": available,
        "base_url": os.getenv("OPENCLAW_BASE_URL", "http://localhost:18789"),
        "enabled": os.getenv("OPENCLAW_ENABLED", "true").lower() == "true",
    }

@app.post("/api/openclaw/browser/start")
async def openclaw_browser_start(headless: bool = False):
    """Start OpenClaw browser."""
    from app.services.openclaw_client import openclaw_client
    result = await openclaw_client.start(headless=headless)
    return {"success": result.get("success", False), "output": result.get("output", "")}

@app.post("/api/openclaw/browser/stop")
async def openclaw_browser_stop():
    """Stop OpenClaw browser."""
    from app.services.openclaw_client import openclaw_client
    result = await openclaw_client.stop()
    return {"success": result.get("success", False)}

@app.post("/api/openclaw/navigate")
async def openclaw_navigate(req: Dict[str, str]):
    """Navigate to a URL."""
    from app.services.openclaw_client import openclaw_client
    url = req.get("url", "")
    if not url:
        return {"success": False, "error": "url required"}
    result = await openclaw_client.navigate(url)
    return {"success": result.get("success", False)}

@app.get("/api/openclaw/snapshot")
async def openclaw_snapshot():
    """Get page snapshot from OpenClaw."""
    from app.services.openclaw_client import openclaw_client
    result = await openclaw_client.snapshot()
    return {"success": result.get("success", False), "output": result.get("output", "")}


# ── PPR 2025 SLT Analysis Endpoint ────────────────────────────────────

class SLTAnalysisRequest(BaseModel):
    boq_items: List[Dict[str, Any]] = []
    estimated_cost: float = 0
    bid_price: float = 0


@app.post("/api/ppr/slt-analysis")
async def ppr_slt_analysis(req: SLTAnalysisRequest):
    """Run PPR 2025 Rule 31 SLT/ALT analysis on BOQ data."""
    from app.agents.ppr_evaluation import _analyze_slt
    result = _analyze_slt(
        boq_items=req.boq_items,
        estimated_cost=req.estimated_cost,
        bid_price=req.bid_price,
    )
    return {"success": True, "analysis": result}


# ── Tender Embedding / Semantic Search Endpoints ───────────────────────

@app.post("/api/embeddings/index")
async def index_tenders_for_search(req: Dict[str, Any]):
    """Index tenders for semantic search using Ollama embeddings."""
    from app.services.tender_embedding import tender_embedding_service
    tenders = req.get("tenders", [])
    count = await tender_embedding_service.index_tenders(tenders)
    return {"success": True, "indexed": count}

@app.post("/api/embeddings/search")
async def search_tenders_semantic(req: Dict[str, Any]):
    """Semantic search for tenders using Ollama (nomic-embed-text)."""
    from app.services.tender_embedding import tender_embedding_service
    query = req.get("query", "")
    top_k = req.get("top_k", 10)
    if not query:
        return {"success": False, "message": "Query required", "results": []}
    results = await tender_embedding_service.search(query, top_k=top_k)
    return {"success": True, "query": query, "results": results}

@app.post("/api/embeddings/similar")
async def find_similar_tenders(req: Dict[str, str]):
    """Find tenders similar to a given tender by ID."""
    from app.services.tender_embedding import tender_embedding_service
    tender_id = req.get("tender_id", "")
    if not tender_id:
        return {"success": False, "message": "tender_id required", "results": []}
    results = await tender_embedding_service.find_similar(tender_id)
    return {"success": True, "tender_id": tender_id, "results": results}

@app.get("/api/embeddings/stats")
async def get_embedding_stats():
    """Get embedding index statistics."""
    try:
        from app.services.tender_embedding import tender_embedding_service

        stats = tender_embedding_service.get_stats()
        return {"success": True, "available": True, **stats}
    except Exception as exc:
        return {
            "success": True,
            "available": False,
            "reason": str(exc),
            "total_indexed": 0,
        }


# ── Ollama Tender Intelligence (Chat with Tender Context) ─────────────

class TenderIntelligenceRequest(BaseModel):
    query: str
    tender_id: str = ""
    language: str = "en"
    include_tender_data: bool = True

@app.post("/api/ollama/tender-intelligence")
async def tender_intelligence(req: TenderIntelligenceRequest):
    """Ask Ollama questions about tenders with context from scraped data."""
    from app.core.ollama_client import OllamaClient
    ollama = OllamaClient()

    if not await ollama.is_available():
        return {"success": False, "content": "Ollama not available. Start it with: ollama serve", "engine": "none"}

    context_parts = []
    if req.tender_id:
        tender = await _load_tender_snapshot(req.tender_id)
        if tender:
            context_parts.append(f"Tender ID: {tender.get('tender_id', '')}")
            context_parts.append(f"Title: {tender.get('title', '')}")
            context_parts.append(f"Entity: {tender.get('procuring_entity', '')}")
            context_parts.append(f"Deadline: {tender.get('deadline', '')}")
            context_parts.append(f"Value: {tender.get('estimated_value_bdt', 0)} BDT")
            context_parts.append(f"Nature: {tender.get('detected_nature', '')}")
            context_parts.append(f"Status: {tender.get('status', '')}")

    if not context_parts:
        all_t = await _load_tender_overview(limit=5000)
        entity_counts = {}
        for t in all_t:
            e = (t.get("pe_office", "") or t.get("procuring_entity", "") or "")[:60]
            entity_counts[e] = entity_counts.get(e, 0) + 1
        top_entities = sorted(entity_counts.items(), key=lambda x: -x[1])[:10]
        context_parts.append(f"Total BWDB tenders monitored: {len(all_t)}")
        context_parts.append("Top procuring entities:")
        for e, c in top_entities:
            context_parts.append(f"  - {e}: {c} tenders")
        upcoming = [t for t in all_t if t.get("award_date", "")]
        upcoming.sort(key=lambda x: x.get("award_date", ""))
        context_parts.append("\nUpcoming deadlines:")
        for t in upcoming[:5]:
            context_parts.append(f"  - {t.get('package_no','')}: {t.get('award_date','')} — {str(t.get('title',''))[:60]}")

    context = "\n".join(context_parts) if context_parts else "No tender data loaded."

    lang_instruction = ""
    if req.language == "bn":
        lang_instruction = "বাংলায় উত্তর দিন। টেন্ডার সংক্রান্ত তথ্য ব্যবহার করে উত্তর দিন।"

    system_prompt = (
        "You are a Tender Intelligence Assistant for Procurement Flow Specialist BD. "
        "You have access to scraped BWDB tender data from the Bangladesh eGP portal. "
        "Answer questions about tenders, deadlines, procuring entities, and tender analysis. "
        "Be precise, reference tender IDs when relevant, and provide actionable insights. "
        f"{lang_instruction}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Tender Context:\n{context}\n\nUser Query: {req.query}"},
    ]

    result = await ollama.chat(messages, lang=req.language)
    result["context_used"] = bool(context_parts)
    result["tender_id"] = req.tender_id
    return result


# ── Monitoring Dashboard Endpoints ──────────────────────────────────────

@app.get("/api/monitor/config")
async def get_monitor_config():
    """Get current monitor configuration."""
    from app.services.monitor_config import monitor_config_service
    return monitor_config_service.get_config()

@app.post("/api/monitor/config")
async def update_monitor_config(req: Dict[str, Any]):
    """Update monitor configuration."""
    from app.services.monitor_config import monitor_config_service
    config = monitor_config_service.update_config(req)
    return {"success": True, "config": config}

@app.post("/api/monitor/config/reset")
async def reset_monitor_config():
    """Reset monitor config to defaults."""
    from app.services.monitor_config import monitor_config_service
    config = monitor_config_service.reset_config()
    return {"success": True, "config": config}

@app.post("/api/monitor/toggle")
async def toggle_monitor(req: Dict[str, Any]):
    """Enable/disable monitor."""
    from app.services.monitor_config import monitor_config_service
    enabled = req.get("enabled")
    state = monitor_config_service.toggle(enabled)
    return {"success": True, "enabled": state}

@app.post("/api/monitor/scan")
async def run_monitor_scan():
    """Run a manual monitoring scan against collected tender data."""
    from app.services.monitor_config import monitor_config_service
    results = monitor_config_service.run_scan()
    return {"success": True, "results": results}

@app.get("/api/monitor/alerts")
async def get_monitor_alerts(limit: int = 50):
    """Get recent monitor alerts."""
    from app.services.monitor_config import monitor_config_service
    alerts = monitor_config_service.get_alerts(limit=limit)
    return {"success": True, "alerts": alerts, "total": len(alerts)}

@app.get("/api/monitor/stats")
async def get_monitor_stats():
    """Get monitor statistics."""
    from app.services.monitor_config import monitor_config_service
    stats = monitor_config_service.get_stats()
    all_t = await _load_tender_overview(limit=5000)
    tender_count = len(all_t)
    entity_count = len(set((t.get("pe_office", "") or t.get("procuring_entity", "") or "") for t in all_t))
    stats["tender_count"] = tender_count
    stats["entity_count"] = entity_count
    return {"success": True, **stats}


# ── Pricing / Subscription Endpoints (Stripe) ────────────────────────────

@app.get("/api/payments/plans")
async def get_pricing_plans():
    """Get available subscription plans."""
    return {
        "success": True,
        "plans": [
            {
                "name": "Free",
                "price": "৳0",
                "period": "/month",
                "description": "For evaluating the platform",
                "features": ["5 Tender Analyses / month", "Basic SOR Comparison", "PDF Export"],
                "plan_name": "free",
            },
            {
                "name": "Professional",
                "price": "৳15,000",
                "period": "/month",
                "description": "For active contractors bidding weekly",
                "features": [
                    "Unlimited Tender Analyses",
                    "PPR 2025 SLT/LERT Engine",
                    "eGP Radar & Alerts",
                    "Competitor Intelligence",
                    "Priority AI Processing",
                ],
                "plan_name": "pro",
                "popular": True,
            },
            {
                "name": "Enterprise",
                "price": "৳45,000",
                "period": "/month",
                "description": "For large firms with multiple estimators",
                "features": [
                    "Everything in Pro",
                    "5 User Seats",
                    "Custom SOR Database",
                    "API Access",
                    "Dedicated Account Manager",
                ],
                "plan_name": "enterprise",
            },
        ],
    }


@app.post("/api/payments/create-checkout-session")
async def create_checkout_session(
    request: Dict[str, str],
    user: dict = Depends(get_optional_user),
):
    """Create Stripe Checkout Session for subscription."""
    from app.services.payment_service import payment_service
    
    price_id = request.get("price_id", "")
    plan_name = request.get("plan_name", "")
    
    if not price_id or not plan_name:
        raise HTTPException(status_code=400, detail="price_id and plan_name required")
    
    result = await payment_service.create_checkout_session(
        price_id=price_id,
        plan_name=plan_name,
        user_id=user["id"],
        user_email=user.get("email", f"{user['id']}@procureflow.ai"),
    )
    return result


@app.post("/api/payments/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events for subscription lifecycle."""
    from app.services.payment_service import payment_service
    
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    
    result = await payment_service.handle_webhook(payload, sig_header)
    return result


@app.post("/api/payments/portal")
async def customer_portal(
    user: dict = Depends(get_current_user),
):
    """Create Stripe Customer Portal session for managing subscription."""
    return {
        "success": True,
        "url": "/settings?plan=manage",
        "message": "Stripe Customer Portal URL (configure in production)",
    }


# ── Team Management Endpoints ──────────────────────────────────────────────
import uuid as _uuid_mod
from datetime import datetime, timezone as _tz
from pathlib import Path as _P
_TEAM_DATA_DIR = _P(os.getenv("BOQ_BASE_DIR", str(_P.home() / ".procurementflow-system"))) / "team"
_TEAM_DATA_DIR.mkdir(parents=True, exist_ok=True)

def _read_json(name: str) -> list:
    p = _TEAM_DATA_DIR / name
    if p.exists():
        try: return json.loads(p.read_text(encoding="utf-8"))
        except: pass
    return []

def _write_json(name: str, data: list):
    (_TEAM_DATA_DIR / name).write_text(json.dumps(data, default=str, indent=2), encoding="utf-8")

@app.get("/api/team/organizations")
async def list_organizations(user: dict = Depends(get_optional_user)):
    from app.db.models import Organization, Tenant
    from app.db.database import get_sync_session
    session = get_sync_session()
    try:
        orgs = session.query(Organization).all()
        return {"organizations": [{
            "id": o.id, "name": o.name, "slug": getattr(o, "slug", o.name.lower().replace(" ", "-")),
            "plan": getattr(o.tenant, "plan", "free") if o.tenant else "free",
            "created_at": str(o.created_at)[:19] if o.created_at else "",
            "member_count": 0,
        } for o in orgs]}
    finally:
        session.close()

@app.post("/api/team/organizations")
async def create_organization(data: Dict[str, Any], user: dict = Depends(get_optional_user)):
    from app.db.models import Organization, Tenant
    from app.db.database import get_sync_session
    session = get_sync_session()
    try:
        tenant_id = user.get("tenant_id", "") if user else ""
        if not tenant_id:
            tenant = Tenant(name=data.get("name", "New Org"), slug=data.get("name", "new-org").lower().replace(" ", "-"), plan="free")
            session.add(tenant); session.flush()
            tenant_id = tenant.id
        org = Organization(tenant_id=tenant_id, name=data.get("name", "New Org"), contact_email=user.get("email", "") if user else "")
        session.add(org); session.flush()
        return {"organization": {
            "id": org.id, "name": org.name, "slug": org.name.lower().replace(" ", "-"),
            "plan": "free", "created_at": str(org.created_at)[:19] if org.created_at else "", "member_count": 1,
        }}
    except Exception as e:
        session.rollback()
        raise HTTPException(400, str(e))
    finally:
        session.close()

@app.get("/api/team/organizations/{org_id}/members")
async def list_members(org_id: str, user: dict = Depends(get_optional_user)):
    from app.db.models import User
    from app.db.database import get_sync_session
    session = get_sync_session()
    try:
        users = session.query(User).filter(User.tenant_id == org_id).all() or []
        return {"members": [{
            "user_id": u.id, "email": u.email or "", "name": u.name or u.email or "",
            "role": u.role or "viewer", "status": "active" if u.is_active else "inactive",
            "joined_at": str(u.created_at)[:19] if u.created_at else "",
        } for u in users]}
    finally:
        session.close()

@app.get("/api/team/invitations")
async def list_invitations(user: dict = Depends(get_optional_user)):
    return {"invitations": _read_json("invitations.json")}

@app.get("/api/team/activity")
async def list_activity(org_id: str = "", limit: int = 30, user: dict = Depends(get_optional_user)):
    acts = _read_json("activity.json")
    if org_id:
        acts = [a for a in acts if a.get("org_id") == org_id]
    return {"activity": acts[:limit]}

@app.post("/api/team/organizations/{org_id}/invite")
async def invite_member(org_id: str, data: Dict[str, Any], user: dict = Depends(get_optional_user)):
    inv = {
        "id": str(_uuid_mod.uuid4()), "org_id": org_id, "email": data.get("email", ""),
        "role": data.get("role", "viewer"), "token": str(_uuid_mod.uuid4()),
        "status": "pending", "invited_by": user.get("email", "") if user else "",
        "created_at": datetime.now(_tz.utc).isoformat(),
        "expires_at": datetime.now(_tz.utc).isoformat().split(".")[0],
    }
    invitations = _read_json("invitations.json")
    invitations.append(inv)
    _write_json("invitations.json", invitations)
    acts = _read_json("activity.json")
    acts.insert(0, {"id": str(_uuid_mod.uuid4()), "org_id": org_id, "action": "invited", "entity_type": "user", "created_at": datetime.now(_tz.utc).isoformat(), "metadata": {"email": data.get("email")}})
    _write_json("activity.json", acts[:200])
    return {"invitation": inv, "invite_link": f"{os.getenv('FRONTEND_URL', 'http://localhost:5173')}/join?token={inv['token']}"}

@app.delete("/api/team/organizations/{org_id}/members/{user_id}")
async def remove_member(org_id: str, user_id: str, user: dict = Depends(get_optional_user)):
    from app.db.models import User as UserModel
    from app.db.database import get_sync_session
    session = get_sync_session()
    try:
        u = session.query(UserModel).filter_by(id=user_id).first()
        if u: session.delete(u); session.commit()
        return {"success": True}
    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e)}
    finally:
        session.close()

# ── EGP Alert Filters Endpoints ────────────────────────────────────────────
_EGP_ALERT_DIR = _P(os.getenv("BOQ_BASE_DIR", str(_P.home() / ".procurementflow-system"))) / "egp_alerts"
_EGP_ALERT_DIR.mkdir(parents=True, exist_ok=True)

@app.get("/api/egp-alerts/filters")
async def get_egp_alert_filters(user: dict = Depends(get_optional_user)):
    fp = _EGP_ALERT_DIR / "filters.json"
    filters = []
    if fp.exists():
        try: filters = json.loads(fp.read_text(encoding="utf-8"))
        except: pass
    return {"filters": filters}

@app.post("/api/egp-alerts/filters")
async def save_egp_alert_filter(data: Dict[str, Any], user: dict = Depends(get_optional_user)):
    fp = _EGP_ALERT_DIR / "filters.json"
    filters = []
    if fp.exists():
        try: filters = json.loads(fp.read_text(encoding="utf-8"))
        except: pass
    if not data.get("id"):
        data["id"] = str(_uuid_mod.uuid4())
    filters = [f for f in filters if f.get("id") != data.get("id")]
    filters.append(data)
    fp.write_text(json.dumps(filters, indent=2), encoding="utf-8")
    return {"filters": filters}

@app.delete("/api/egp-alerts/filters/{filter_id}")
async def delete_egp_alert_filter(filter_id: str, user: dict = Depends(get_optional_user)):
    fp = _EGP_ALERT_DIR / "filters.json"
    filters = []
    if fp.exists():
        try: filters = json.loads(fp.read_text(encoding="utf-8"))
        except: pass
    filters = [f for f in filters if f.get("id") != filter_id]
    fp.write_text(json.dumps(filters, indent=2), encoding="utf-8")
    return {"success": True}

@app.post("/api/egp-alerts/poll")
async def poll_egp_alerts(user: dict = Depends(get_optional_user)):
    """Poll for tenders matching saved alert filters."""
    from app.db.models import Tender as TenderModel
    from app.db.database import get_sync_session
    fp = _EGP_ALERT_DIR / "filters.json"
    filters = []
    if fp.exists():
        try: filters = json.loads(fp.read_text(encoding="utf-8"))
        except: pass
    matches = []
    session = get_sync_session()
    try:
        all_tenders = session.query(TenderModel).filter(TenderModel.status.in_(["Live", "live", ""])).limit(200).all()
        for t in all_tenders:
            title = (t.title or "").lower()
            for f in filters:
                if not f.get("active", True): continue
                kw = (f.get("keywords", "") or "").lower()
                if kw and kw not in title: continue
                val = float(t.estimated_value_bdt or 0) if hasattr(t, "estimated_value_bdt") else 0
                if f.get("min_value") and val < float(f["min_value"]): continue
                if f.get("max_value") and val > float(f["max_value"]): continue
                matches.append({
                    "tender_id": t.tender_id or str(t.id),
                    "title": t.title or "",
                    "department": t.agency or "",
                    "deadline": str(t.submission_deadline)[:10] if hasattr(t, "submission_deadline") and t.submission_deadline else "",
                    "estimated_value": val,
                    "matched_keywords": [kw] if kw else [],
                })
                break
    finally:
        session.close()
    return {"matches": matches}

# ── Brain Router (consolidated agent orchestration API) ────────────────────
from app.api.brain_router import router as brain_router
app.include_router(brain_router)

# ── SPA Catch-all (must be LAST) ──────────────────────────────────────────

@app.get("/{full_path:path}", include_in_schema=False)
async def catch_all_frontend(full_path: str):
    """Serve SPA for non-API routes."""
    if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("openapi"):
        from fastapi import HTTPException
        raise HTTPException(status_code=404)
    import os
    static_file = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(static_file):
        from fastapi.responses import HTMLResponse
        with open(static_file, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    from fastapi import HTTPException
    raise HTTPException(status_code=404)
