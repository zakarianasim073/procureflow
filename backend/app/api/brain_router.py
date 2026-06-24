"""
ProcureFlow Brain Router — Consolidated Agent Orchestration API
Adapted from procureflow source for our project's DB schema.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from app.core.security import get_current_user

from app.agents.core.pipeline import IntelligencePipeline, KnowledgeFeedbackLoop
from app.agents.core.thought_engine import ThoughtEngine, ThoughtSignature
from app.agents.core.knowledge_graph import KnowledgeGraph
from app.agents import (
    AgentBrain,
    TenderRadarAgent, TenderAcquisitionAgent, CorrigendumWatchdogAgent, VisionIntelligenceAgent,
    BOQIntelligenceAgent, SpecIntelligenceAgent, AwardIntelligenceAgent, ResourceCapacityAgent,
    PPREvaluationAgent, PPR2025ComplianceAgent, LERTPredictionAgent, EligibilityComplianceAgent, RiskIntelligenceAgent,
    MarketRateIntelligenceAgent, RateAnalysisAgent, RABillPredictorAgent, VatTaxCalculatorAgent, EGPRateFillAgent,
    SORZoneMatcherAgent,
    WinProbabilityAgent, BidPositionOptimizerAgent, CompetitorIntelligenceAgent, CompetitorPricingPredictorAgent, SyndicateRadarAgent,
    FinancialIntelligenceAgent, ExecutiveDecisionAgent, AIBidAssistantAgent,
    DocumentPreparationAgent, DocumentAIAgent, TenderDocumentAgent, SubmissionValidationAgent, TenderPreparationAgent, TenderDashboardAgent, OpeningReportAgent,
    MoatSLTAnalyzerAgent, PPR2025DashboardAgent, TenderPreScreenerAgent,
    BidNoBidAgent, ClientIntelligenceAgent,
    CompanyBrainAgent, MarketBrainAgent,
    APPForecastAgent,
    KnowledgeLakeAgent, ReportGenerationAgent, LearningAgent,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["ProcureFlow Brain API"])
_RUNTIME_LOG_ROOT = Path(__file__).resolve().parent.parent / "runtime" / "logs"
_UI_AUDIT_LOG = _RUNTIME_LOG_ROOT / "ui_feature_checks.jsonl"


def _log_ui_event(feature: str, action: str, payload: Dict[str, Any]) -> None:
    _RUNTIME_LOG_ROOT.mkdir(parents=True, exist_ok=True)
    _UI_AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "feature": feature,
        "action": action,
        **payload,
    }
    try:
        with open(_UI_AUDIT_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("Could not write UI audit log: %s", exc)


@router.post("/ui-log")
async def ui_log(payload: Dict[str, Any]):
    """Persist a UI test snapshot for later review."""
    feature = str(payload.get("feature", "ui"))
    action = str(payload.get("action", "snapshot"))
    data = payload.get("data", {})
    _log_ui_event(feature, action, {"data": data})
    return {"success": True, "feature": feature, "action": action}

def _decode_jsonish(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{":
        return value
    try:
        return json.loads(text)
    except Exception:
        return value

# ── Agent Registry ──────────────────────────────────────────────────────

_brain: AgentBrain = None

def get_brain() -> AgentBrain:
    global _brain
    if _brain is None:
        _brain = AgentBrain()
        _brain.register_agent("agent-001-tender-radar", TenderRadarAgent(_brain),
            "Tender Radar", "Tender discovery & matching", version="1.0.0")
        _brain.register_agent("agent-002-tender-acquisition", TenderAcquisitionAgent(_brain),
            "Tender Acquisition", "Downloads tender documents", version="1.0.0")
        _brain.register_agent("agent-003-corrigendum-watchdog", CorrigendumWatchdogAgent(_brain),
            "Corrigendum Watchdog", "Tender amendment tracker", version="1.0.0")
        _brain.register_agent("agent-004-document-ai", DocumentAIAgent(_brain),
            "Document AI", "Structured data extraction from documents", version="1.0.0")
        _brain.register_agent("agent-005-boq-intelligence", BOQIntelligenceAgent(_brain),
            "BOQ Intelligence", "Bill of quantities analysis", version="1.0.0")
        _brain.register_agent("agent-006-spec-intelligence", SpecIntelligenceAgent(_brain),
            "Spec Intelligence", "Technical specification analysis", version="1.0.0")
        _brain.register_agent("agent-007-eligibility-compliance", EligibilityComplianceAgent(_brain),
            "Eligibility Compliance", "Qualification requirements check", version="1.0.0")
        _brain.register_agent("agent-008-risk-intelligence", RiskIntelligenceAgent(_brain),
            "Risk Intelligence", "Contractual risk analysis", version="1.0.0")
        _brain.register_agent("agent-009-ppr-evaluation", PPREvaluationAgent(_brain),
            "PPR Evaluation", "CPTU-compliant TEC evaluation", version="3.0.0")
        _brain.register_agent("agent-010-ppr-compliance", PPR2025ComplianceAgent(_brain),
            "PPR Compliance", "Schedule 4/5/6 compliance", version="2.0.0")
        _brain.register_agent("agent-010-lert-prediction", LERTPredictionAgent(_brain),
            "LERT Prediction", "Lowest evaluated responsive tender prediction", version="1.0.0")
        _brain.register_agent("agent-011-rate-analysis", RateAnalysisAgent(_brain),
            "Rate Analysis", "SOR vs market rate analysis", version="1.0.0")
        _brain.register_agent("agent-012-market-rate", MarketRateIntelligenceAgent(_brain),
            "Market Rate Intelligence", "Current market rate analysis", version="1.0.0")
        _brain.register_agent("agent-013-competitor-intelligence", CompetitorIntelligenceAgent(_brain),
            "Competitor Intelligence", "Bidding behavior analysis", version="1.0.0")
        _brain.register_agent("agent-014-award-intelligence", AwardIntelligenceAgent(_brain),
            "Award Intelligence", "Award data analysis", version="1.0.0")
        _brain.register_agent("agent-015-competitor-pricing", CompetitorPricingPredictorAgent(_brain),
            "Competitor Pricing Predictor", "Predicts competitor pricing", version="1.0.0")
        _brain.register_agent("agent-016-win-probability", WinProbabilityAgent(_brain),
            "Win Probability", "Win likelihood prediction", version="1.0.0")
        _brain.register_agent("agent-017-bid-position-optimizer", BidPositionOptimizerAgent(_brain),
            "Bid Position Optimizer", "Discount range recommendation", version="1.0.0")
        _brain.register_agent("agent-018-ai-bid-assistant", AIBidAssistantAgent(_brain),
            "AI Bid Assistant", "AI bid preparation guidance", version="1.0.0")
        _brain.register_agent("agent-019-resource-capacity", ResourceCapacityAgent(_brain),
            "Resource Capacity", "Company resource evaluation", version="1.0.0")
        _brain.register_agent("agent-020-egp-rate-fill", EGPRateFillAgent(_brain),
            "EGP Rate Fill", "Auto-fills rate schedules", version="1.0.0")
        _brain.register_agent("agent-044-sor-zone-matcher", SORZoneMatcherAgent(_brain),
            "SOR Zone Matcher", "Maps districts to correct SOR zones per agency", version="1.0.0")
        _brain.register_agent("agent-021-financial-intelligence", FinancialIntelligenceAgent(_brain),
            "Financial Intelligence", "Financial capacity analysis", version="1.0.0")
        _brain.register_agent("agent-022-executive-decision", ExecutiveDecisionAgent(_brain),
            "Executive Decision", "Bid/no-bid recommendation", version="1.0.0")
        _brain.register_agent("agent-023-report-generation", ReportGenerationAgent(_brain),
            "Report Generation", "Intelligence report generation", version="1.0.0")
        _brain.register_agent("agent-024-submission-validation", SubmissionValidationAgent(_brain),
            "Submission Validation", "Submission completeness check", version="1.0.0")
        _brain.register_agent("agent-036-moat-slt-analyzer", MoatSLTAnalyzerAgent(_brain),
            "MOAT & SLT Analyzer", "Pre-emptive competitive intelligence & threshold analysis", version="1.0.0")
        _brain.register_agent("agent-037-ppr2025-dashboard", PPR2025DashboardAgent(_brain),
            "PPR 2025 Dashboard", "PPR 2025 aligned compliance & bid dashboard", version="1.0.0")
        _brain.register_agent("agent-038-tender-pre-screener", TenderPreScreenerAgent(_brain),
            "Tender Pre-Screener", "Idle-time narrowing engine", version="1.0.0")
        _brain.register_agent("agent-039-bid-no-bid", BidNoBidAgent(_brain),
            "Bid/No-Bid Engine", "Decision intelligence: BID or NO-BID with confidence", version="1.0.0")
        _brain.register_agent("agent-040-company-brain", CompanyBrainAgent(_brain),
            "Company Brain", "Strategic insights from company + market data", version="1.0.0")
        _brain.register_agent("agent-041-market-brain", MarketBrainAgent(_brain),
            "Market Brain", "Syndicated market intelligence & trends", version="1.0.0")
        _brain.register_agent("agent-042-app-forecast", APPForecastAgent(_brain),
            "APP Forecast Engine", "Predicts upcoming opportunities from APP records", version="1.0.0")
        _brain.register_agent("agent-043-client-intelligence", ClientIntelligenceAgent(_brain),
            "Client Intelligence", "Multi-tenant client manager", version="1.0.0")
        _brain.register_agent("agent-025-knowledge-lake", KnowledgeLakeAgent(_brain),
            "Knowledge Lake", "Central knowledge repository", version="2.0.0")
        _brain.register_agent("agent-026-learning", LearningAgent(_brain),
            "Learning", "Outcome learning & tracking", version="2.0.0")
        _brain.register_agent("agent-028-syndicate-radar", SyndicateRadarAgent(_brain),
            "Syndicate Radar", "Collusion pattern detection", version="1.0.0")
        _brain.register_agent("agent-029-vision-intelligence", VisionIntelligenceAgent(_brain),
            "Vision Intelligence", "OCR and document imaging", version="1.0.0")
        _brain.register_agent("agent-030-ra-bill-predictor", RABillPredictorAgent(_brain),
            "RA Bill Predictor", "Running account bill prediction", version="1.0.0")
        _brain.register_agent("agent-031-tender-preparation", TenderPreparationAgent(_brain),
            "Tender Preparation", "End-to-end tender prep", version="1.0.0")
        _brain.register_agent("agent-032-document-preparation", DocumentPreparationAgent(_brain),
            "Document Preparation", "Tender document workflow", version="1.0.0")
        _brain.register_agent("agent-033-vat-tax-calculator", VatTaxCalculatorAgent(_brain),
            "VAT Tax Calculator", "VAT and tax computation", version="1.0.0")
        _brain.register_agent("agent-034-tender-document", TenderDocumentAgent(_brain),
            "Tender Document Agent", "Document management", version="1.0.0")
        _brain.register_agent("agent-035-tender-dashboard", TenderDashboardAgent(_brain),
            "Tender Dashboard", "Full tender document extraction & reporting", version="1.0.0")
        _brain.register_agent("agent-045-opening-report", OpeningReportAgent(_brain),
            "Opening Report", "Archived tender opening report extraction via TOR2/TORR2", version="1.0.0")
    return _brain

# ── Health ──────────────────────────────────────────────────────────────

@router.get("/health")
async def health(request: Request):
    """Comprehensive health check with DB counts and import status."""
    from app.core.config import settings as boq_settings
    raw = getattr(request.app.state, "intelligence_import_status", None)
    if raw is None:
        import_status = {"state": "unknown", "started": False}
    elif hasattr(raw, "to_dict"):
        import_status = raw.to_dict()
    else:
        import_status = raw
    try:
        from app.db.base import get_session_factory
        from app.services.intelligence_data_service import IntelligenceDataService
        sf = get_session_factory()
        async with sf() as session:
            counts = await IntelligenceDataService(session).get_import_counts()
        if isinstance(import_status, dict):
            import_status["summary"] = counts
    except Exception:
        pass
    return {
        "status": "healthy",
        "app": boq_settings.APP_NAME,
        "version": boq_settings.VERSION,
        "intelligence_import": import_status,
    }

# ── Stats ───────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats():
    """Get database statistics from our schema."""
    from app.db.base import get_session_factory
    from sqlalchemy import text
    sf = get_session_factory()
    async with sf() as s:
        tables = ["award_records_v2", "procurement_tenders", "contractor_dna",
                   "procurement_lifecycle", "app_records"]
        stats = {}
        for table in tables:
            try:
                r = await s.execute(text(f"SELECT COUNT(*) FROM {table}"))
                stats[table] = r.scalar() or 0
            except Exception:
                stats[table] = 0
    return stats

# ── Agents ──────────────────────────────────────────────────────────────

@router.get("/agents")
async def list_agents():
    """List all registered agents — brain agents + registry agents."""
    from app.agents import AgentRegistry
    brain = get_brain()
    brain_agents = []
    for aid, cap in brain._agents.items():
        brain_agents.append({
            "id": aid,
            "name": cap.agent_name,
            "description": cap.description,
            "version": cap.version,
            "available": cap.is_available,
        })
    registry = AgentRegistry()
    return {
        "brain_agents": brain_agents,
        "brain_count": len(brain_agents),
        "registry_total": registry.count,
        "registry_agents": registry.list_agents(),
    }

@router.post("/agents/{agent_id}/execute")
async def execute_agent(agent_id: str, context: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """Execute a specific agent with context."""
    brain = get_brain()
    agent = brain.get_agent(agent_id)
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    result = await agent.run(context)
    return {
        "agent_id": result.agent_id,
        "status": result.status.value,
        "output": result.output,
        "error": result.error,
        "execution_time_ms": result.execution_time_ms,
    }

# ── Brain Messaging ─────────────────────────────────────────────────────

@router.post("/brain/message")
async def send_message(msg: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """Send a message via Agent Brain."""
    brain = get_brain()
    response = await brain.request(
        sender_id=msg.get("sender", "api"),
        recipient_id=msg.get("recipient", ""),
        subject=msg.get("subject", ""),
        body=msg.get("body", {}),
    )
    _log_ui_event("brain", "message", {
        "sender": msg.get("sender", "api"),
        "recipient": msg.get("recipient", ""),
        "subject": msg.get("subject", ""),
        "response_keys": list(response.keys()) if isinstance(response, dict) else [],
    })
    return response

@router.get("/brain/status")
async def brain_status():
    """Get Agent Brain status."""
    brain = get_brain()
    stats = brain.get_stats()
    result = {
        "agents_registered": stats.get("registered_agents", 0),
        "queue_size": stats.get("queue_size", 0),
        "knowledge_entries": stats.get("knowledge_entries", 0),
        "agents": stats.get("agents", []),
        "message_handlers": stats.get("active_handlers", 0),
    }
    _log_ui_event("brain", "status", {
        "agents_registered": result["agents_registered"],
        "queue_size": result["queue_size"],
        "knowledge_entries": result["knowledge_entries"],
    })
    return result

@router.post("/brain/broadcast")
async def brain_broadcast(msg: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """Broadcast a message to all agents."""
    brain = get_brain()
    asyncio.create_task(
        brain.broadcast(
            sender_id=msg.get("sender", "api"),
            subject=msg.get("subject", ""),
            body=msg.get("body", {}),
        )
    )
    _log_ui_event("brain", "broadcast", {
        "sender": msg.get("sender", "api"),
        "subject": msg.get("subject", ""),
    })
    return {"status": "broadcast_queued", "subject": msg.get("subject")}

@router.post("/brain/query")
async def brain_query(query: Dict[str, Any] = {}, user: Dict[str, Any] = Depends(get_current_user)):
    """Query the Agent Brain for knowledge."""
    brain = get_brain()
    results = await brain.query_knowledge(
        entry_type=query.get("entry_type"),
        tender_id=query.get("tender_id"),
        agent_id=query.get("agent_id"),
    )
    result = {"results": results, "count": len(results)}
    _log_ui_event("brain", "query", {
        "entry_type": query.get("entry_type"),
        "tender_id": query.get("tender_id"),
        "agent_id": query.get("agent_id"),
        "count": len(results),
    })
    return result

@router.post("/brain/store")
async def store_knowledge(data: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """Store knowledge in the Agent Brain."""
    brain = get_brain()
    entry_id = data.get("entry_id") or f"queued-{uuid4().hex[:12]}"
    asyncio.create_task(
        brain.store_knowledge(
            agent_id=data.get("agent_id", "api"),
            entry_type=data.get("entry_type", "note"),
            tender_id=data.get("tender_id", ""),
            data=data.get("data", {}),
            summary=data.get("summary", ""),
            tags=data.get("tags", []),
        )
    )
    _log_ui_event("brain", "store_knowledge", {
        "agent_id": data.get("agent_id", "api"),
        "entry_type": data.get("entry_type", "note"),
        "tender_id": data.get("tender_id", ""),
        "entry_id": entry_id,
    })
    return {"status": "queued", "entry_id": entry_id}

@router.get("/brain/memory")
async def brain_memory():
    """Get the brain's current system memory snapshot."""
    brain = get_brain()
    memory = await brain.get_system_memory()
    return memory

@router.post("/brain/workflow")
async def run_workflow(workflow: List[Dict[str, Any]], context: Dict[str, Any] = {}, user: Dict[str, Any] = Depends(get_current_user)):
    """Run a multi-agent workflow."""
    brain = get_brain()
    results = await brain.run_workflow(workflow, context)
    return {"workflow_results": results, "steps": len(workflow)}

@router.post("/brain/idle-cycle")
async def trigger_idle_cycle(user: Dict[str, Any] = Depends(get_current_user)):
    """Trigger one idle-time intelligence cycle."""
    brain = get_brain()
    agent = brain.get_agent("agent-038-tender-pre-screener")
    if agent:
        result = await agent.execute({"action": "idle_cycle"})
        return {"status": "triggered", "result": result}
    return {"status": "not_available"}

# ── Data Queries (adapted to our schema) ────────────────────────────────

@router.get("/tenders")
async def list_tenders(
    agency: str = None, status: str = None,
    limit: int = 100, offset: int = 0
):
    """List tenders from procurement_tenders."""
    from app.db.base import get_session_factory
    from sqlalchemy import text
    sf = get_session_factory()
    async with sf() as s:
        where = []
        params = {}
        if agency:
            where.append("agency_code = :a")
            params["a"] = agency
        wsql = " AND ".join(where) if where else "1=1"
        r = await s.execute(text(f"SELECT COUNT(*) FROM procurement_tenders WHERE {wsql}"), params)
        total = r.scalar() or 0
        r = await s.execute(
            text(f"SELECT id, title, agency_code, zone_id, procurement_method "
                 f"FROM procurement_tenders WHERE {wsql} ORDER BY created_at DESC LIMIT {int(limit)} OFFSET {int(offset)}"),
            params
        )
        rows = r.fetchall()
    tenders = []
    for row in rows:
        tenders.append({
            "tender_id": row[0],
            "title": row[1],
            "agency": row[2],
            "zone": row[3],
            "procurement_method": row[4],
        })
    return {"tenders": tenders, "total": total}

@router.get("/tenders/{tender_id}")
async def get_tender(tender_id: str):
    """Get detailed tender information."""
    from app.db.base import get_session_factory
    from sqlalchemy import text
    sf = get_session_factory()
    async with sf() as s:
        r = await s.execute(
            text("SELECT id, title, agency_code, zone_id, procurement_method, "
                 "pe_office, created_at, updated_at "
                 "FROM procurement_tenders WHERE id = :id"), {"id": tender_id}
        )
        row = r.fetchone()
        if not row:
            raise HTTPException(404, f"Tender '{tender_id}' not found")
        ar = await s.execute(
            text("SELECT contractor_name, amount_bdt FROM award_records_v2 WHERE procurement_tender_id = :id LIMIT 1"),
            {"id": tender_id}
        )
        award_row = ar.fetchone()
    return {
        "tender": {
            "tender_id": row[0],
            "title": row[1],
            "agency": row[2],
            "zone": row[3],
            "procurement_method": row[4],
            "pe_office": row[5],
            "created_at": str(row[6]) if row[6] else None,
        },
        "award": {
            "contractor_name": award_row[0],
            "award_amount": float(award_row[1] or 0),
        } if award_row else None,
    }

@router.get("/awards")
async def list_awards(limit: int = 100, offset: int = 0):
    """List awards from award_records_v2."""
    from app.db.base import get_session_factory
    from sqlalchemy import text
    sf = get_session_factory()
    async with sf() as s:
        r = await s.execute(text("SELECT COUNT(*) FROM award_records_v2"))
        total = r.scalar() or 0
        r = await s.execute(
            text("SELECT procurement_tender_id, contractor_name, amount_bdt FROM award_records_v2 "
                 "ORDER BY created_at DESC LIMIT :lim OFFSET :off"),
            {"lim": int(limit), "off": int(offset)}
        )
        awards = [{"tender_id": row[0], "contractor_name": row[1], "award_amount": float(row[2] or 0)}
                  for row in r.fetchall()]
    return {"awards": awards, "total": total}

@router.get("/contractors")
async def list_contractors(limit: int = 100, offset: int = 0):
    """List contractors from contractor_dna + contractors."""
    from app.db.base import get_session_factory
    from sqlalchemy import text
    sf = get_session_factory()
    async with sf() as s:
        r = await s.execute(text("SELECT COUNT(*) FROM contractor_dna"))
        total = r.scalar() or 0
        r = await s.execute(
            text("SELECT c.contractor_name, cd.total_contracts, cd.total_amount_bdt, cd.health_score "
                 "FROM contractor_dna cd "
                 "JOIN contractors c ON c.id = cd.contractor_id "
                 "ORDER BY cd.total_amount_bdt DESC LIMIT :lim OFFSET :off"),
            {"lim": int(limit), "off": int(offset)}
        )
        contractors = [{"name": row[0], "total_contracts": row[1],
                        "total_award_value": float(row[2] or 0), "health_score": float(row[3] or 0)}
                       for row in r.fetchall()]
    return {"contractors": contractors, "total": total}

# ── Multi-Client Management ─────────────────────────────────────────

@router.post("/clients/create")
async def create_client(data: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """Create a new client (tenant + subscription)."""
    from app.services.client_manager import get_client_manager
    cm = get_client_manager()
    return cm.create_client(
        name=data.get("name", ""), slug=data.get("slug", ""),
        email=data.get("email", ""), phone=data.get("phone", ""),
        plan=data.get("plan", "starter")
    )

@router.get("/clients")
async def list_clients():
    """List all clients."""
    from app.services.client_manager import get_client_manager
    cm = get_client_manager()
    return {"clients": cm.list_clients()}

@router.get("/clients/{tenant_id}")
async def get_client(tenant_id: str):
    """Get client details with subscription status."""
    from app.services.client_manager import get_client_manager
    cm = get_client_manager()
    client = cm.get_client(tenant_id)
    if not client:
        raise HTTPException(404, "Client not found")
    return client

@router.post("/clients/{tenant_id}/profile")
async def update_client_profile(tenant_id: str, profile: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """Update client profile/config."""
    from app.services.client_manager import get_client_manager
    cm = get_client_manager()
    return cm.update_client_profile(tenant_id, profile)

@router.get("/clients/{tenant_id}/quota")
async def check_client_quota(tenant_id: str):
    """Check client subscription quota status."""
    from app.services.client_manager import get_client_manager
    cm = get_client_manager()
    return cm.check_quota(tenant_id)

@router.get("/clients/{tenant_id}/usage")
async def get_client_usage(tenant_id: str, days: int = 30):
    """Get client tender usage history."""
    from app.services.client_manager import get_client_manager
    cm = get_client_manager()
    return cm.get_usage_history(tenant_id, days)

@router.post("/clients/{tenant_id}/pipeline")
async def run_client_pipeline(tenant_id: str, context: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """Run full client-aware pipeline."""
    brain = get_brain()
    agent = brain.get_agent("agent-043-client-intelligence")
    if not agent:
        raise HTTPException(404, "Client Intelligence agent not found")
    ctx = {"action": "full_client_pipeline", "tenant_id": tenant_id, **context}
    result = await agent.run(ctx)
    return result.output if hasattr(result, 'output') else result

@router.post("/multi-client/evaluate")
async def evaluate_multi_client(data: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """Evaluate multiple clients for conflict resolution."""
    from app.services.meta_allocator import get_meta_allocator
    ma = get_meta_allocator()
    evaluations = ma.evaluate_clients(
        tender_id=data.get("tender_id", ""),
        client_profiles=data.get("client_profiles", [])
    )
    return {"tender_id": data.get("tender_id", ""), "evaluations": evaluations}

# ── Thought Engine (Human-in-the-Loop) ─────────────────────────────────

_thought_engine: ThoughtEngine = None

def get_thought_engine() -> ThoughtEngine:
    global _thought_engine
    if _thought_engine is None:
        _thought_engine = ThoughtEngine(brain=get_brain())
    return _thought_engine

@router.get("/thoughts/pending")
async def pending_thoughts(agent_id: str = None):
    """Get all pending thoughts awaiting approval."""
    engine = get_thought_engine()
    thoughts = await engine.get_pending(agent_id)
    result = {"pending_thoughts": thoughts, "count": len(thoughts)}
    _log_ui_event("thoughts", "pending", {"agent_id": agent_id, "count": len(thoughts)})
    return result

@router.get("/thoughts/history")
async def thought_history(status: str = "approved", limit: int = 20):
    """Get thought history by status."""
    engine = get_thought_engine()
    thoughts = await engine.get_history(status, limit)
    result = {"thoughts": thoughts, "count": len(thoughts)}
    _log_ui_event("thoughts", "history", {"status": status, "count": len(thoughts), "limit": limit})
    return result

@router.post("/thoughts/{thought_id}/approve")
async def approve_thought(thought_id: str, comment: str = "", user: Dict[str, Any] = Depends(get_current_user)):
    """Approve a thought."""
    engine = get_thought_engine()
    result = await engine.approve(thought_id, comment)
    _log_ui_event("thoughts", "approve", {"thought_id": thought_id, "comment": comment})
    return result

@router.post("/thoughts/{thought_id}/reject")
async def reject_thought(thought_id: str, comment: str = "", user: Dict[str, Any] = Depends(get_current_user)):
    """Reject a thought."""
    engine = get_thought_engine()
    result = await engine.reject(thought_id, comment)
    _log_ui_event("thoughts", "reject", {"thought_id": thought_id, "comment": comment})
    return result

@router.post("/thoughts/propose")
async def propose_thought(thought: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """Agent proposes a new thought/insight."""
    engine = get_thought_engine()
    try:
        result = await asyncio.wait_for(
            engine.propose(
                agent_id=thought.get("agent_id", "api"),
                agent_name=thought.get("agent_name", "API User"),
                thought_type=thought.get("thought_type", "insight"),
                title=thought.get("title", ""),
                description=thought.get("description", ""),
                evidence=thought.get("evidence", {}),
                tender_id=thought.get("tender_id", ""),
                impact=thought.get("impact", "medium"),
                confidence=thought.get("confidence", 0.0),
                key_data=thought.get("key_data", {}),
            ),
            timeout=5.0,
        )
    except asyncio.TimeoutError:
        result = {
            "status": "queued",
            "message": "Thought accepted and queued for background processing",
            "thought_id": None,
        }
    _log_ui_event("thoughts", "propose", {
        "agent_id": thought.get("agent_id", "api"),
        "agent_name": thought.get("agent_name", "API User"),
        "thought_type": thought.get("thought_type", "insight"),
        "title": thought.get("title", ""),
        "status": result.get("status"),
        "thought_id": result.get("thought_id"),
    })
    return result

@router.get("/thoughts/stats")
async def thought_stats():
    """Get thought engine statistics."""
    engine = get_thought_engine()
    result = engine.get_stats()
    _log_ui_event("thoughts", "stats", {
        "pending_count": result.get("pending_count"),
        "approved_count": result.get("approved_count"),
        "rejected_count": result.get("rejected_count"),
    })
    return result

# ── Tender Dashboard ─────────────────────────────────────────────────

@router.get("/dashboard/{tender_id}")
async def get_tender_dashboard(tender_id: str):
    """Get complete tender dashboard."""
    brain = get_brain()
    agent = brain.get_agent("agent-035-tender-dashboard")
    if not agent:
        return {"error": "Dashboard agent not found"}
    result = await agent.run({"tender_id": tender_id, "action": "get_dashboard"})
    return result.output if hasattr(result, 'output') else result

@router.post("/dashboard/{tender_id}/extract")
async def extract_tender(tender_id: str, data: Dict[str, Any] = {}, user: Dict[str, Any] = Depends(get_current_user)):
    """Run full document extraction for a tender."""
    brain = get_brain()
    agent = brain.get_agent("agent-035-tender-dashboard")
    if not agent:
        return {"error": "Dashboard agent not found"}
    context = {"tender_id": tender_id, "action": "full_extraction", **data}
    result = await agent.run(context)
    return result.output if hasattr(result, 'output') else result

@router.post("/dashboard/{tender_id}/report")
async def generate_tender_report(tender_id: str, context: Dict[str, Any] = {}, user: Dict[str, Any] = Depends(get_current_user)):
    """Generate comprehensive tender readiness report."""
    brain = get_brain()
    agent = brain.get_agent("agent-035-tender-dashboard")
    if not agent:
        return {"error": "Dashboard agent not found"}
    result = await agent.run({"tender_id": tender_id, "action": "generate_report", **context})
    return result.output if hasattr(result, 'output') else result

@router.post("/dashboard/import-notice")
async def import_tender_notice(notice: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """Import a tender notice into the dashboard."""
    brain = get_brain()
    agent = brain.get_agent("agent-035-tender-dashboard")
    if not agent:
        return {"error": "Dashboard agent not found"}
    result = await agent.run({
        "tender_id": notice.get("tender_id", ""),
        "action": "full_extraction",
        "raw_data": notice,
        "source_format": "json",
    })
    return result.output if hasattr(result, 'output') else result

# ── Intelligence Pipeline ─────────────────────────────────────────────

@router.post("/pipeline/run")
async def run_pipeline(context: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """Run the full intelligence pipeline or orchestrator pipeline."""
    from app.agents import AgentRegistry
    mode = context.get("mode", "intelligence")
    if mode == "orchestrator":
        registry = AgentRegistry()
        orch = registry.get("agent-027-orchestrator")
        if not orch:
            raise HTTPException(status_code=500, detail="Orchestrator not available")
        ctx = context.get("context", {})
        ctx["mode"] = mode
        if context.get("phase"):
            ctx["phase"] = context["phase"]
        if context.get("agent_ids"):
            ctx["agent_ids"] = context["agent_ids"]
        result = await orch.execute(ctx)
        return result.to_dict() if hasattr(result, "to_dict") else result
    brain = get_brain()
    pipeline = IntelligencePipeline(brain)
    results = await pipeline.run(context)
    return results

@router.get("/pipeline/definition")
async def get_pipeline_definition():
    """Get the intelligence pipeline stage definitions."""
    stages = []
    for s in IntelligencePipeline.PIPELINE:
        stages.append({
            "agent_id": s.agent_id,
            "depends_on": s.depends_on,
            "output_keys": s.output_keys,
            "timeout": s.timeout,
        })
    return {"pipeline": stages, "total_stages": len(stages)}

@router.post("/feedback/outcome")
async def record_outcome(data: Dict[str, Any], user: Dict[str, Any] = Depends(get_current_user)):
    """Record actual outcome and trigger learning."""
    brain = get_brain()
    result = await KnowledgeFeedbackLoop.record_outcome(
        agent_id=data.get("agent_id", ""),
        tender_id=data.get("tender_id", ""),
        predicted=data.get("predicted", {}),
        actual=data.get("actual", {}),
        brain=brain,
    )
    return result

# ── Pre-emptive Intelligence ────────────────────────────────────────

@router.post("/intelligence/moat-slt")
async def moat_slt_analysis(request: Dict[str, Any]):
    """Get MOAT & SLT analysis for a tender."""
    brain = get_brain()
    agent = brain.get_agent("agent-036-moat-slt-analyzer")
    if not agent:
        raise HTTPException(status_code=404, detail="MOAT/SLT agent not found")
    result = await agent.execute({
        "action": request.get("action", "get_cached"),
        "tender_id": request.get("tender_id", ""),
    })
    return result

@router.get("/intelligence/moat-slt/slt/{agency}/{category}")
async def get_slt_by_category(agency: str, category: str):
    """Get SLT for agency+category."""
    brain = get_brain()
    agent = brain.get_agent("agent-036-moat-slt-analyzer")
    if agent:
        result = await agent.execute({"action": "compute_slt"})
        output = result.output if hasattr(result, 'output') else {}
        slts = output.get("slt_by_category", []) if isinstance(output, dict) else []
        filtered = [s for s in slts if s.get("agency") == agency]
        return {"agency": agency, "category": category, "slt_records": filtered}
    return {"status": "not_available"}

@router.get("/intelligence/moat-slt/nppi/{agency}/{category}")
async def get_nppi(agency: str, category: str):
    """Get NPPI value for agency+category."""
    brain = get_brain()
    agent = brain.get_agent("agent-036-moat-slt-analyzer")
    if agent:
        result = await agent.execute({"action": "compute_nppi"})
        output = result.output if hasattr(result, 'output') else {}
        nppis = output.get("nppi_values", []) if isinstance(output, dict) else []
        filtered = [n for n in nppis if n.get("agency") == agency]
        return {"agency": agency, "category": category, "nppi_records": filtered}
    return {"status": "not_available"}

@router.post("/intelligence/ppr-dashboard")
async def ppr2025_dashboard(request: Dict[str, Any]):
    """Get PPR 2025 dashboard for a tender."""
    brain = get_brain()
    agent = brain.get_agent("agent-037-ppr2025-dashboard")
    if not agent:
        raise HTTPException(status_code=404, detail="PPR2025 Dashboard agent not found")
    result = await agent.execute({
        "action": request.get("action", "dashboard"),
        "tender_id": request.get("tender_id", ""),
        "company_profile": request.get("company_profile", {}),
    })
    return result

@router.post("/intelligence/pre-screen")
async def pre_screen_tenders(request: Dict[str, Any]):
    """Pre-screen and narrow tenders."""
    brain = get_brain()
    agent = brain.get_agent("agent-038-tender-pre-screener")
    if not agent:
        raise HTTPException(status_code=404, detail="Pre-Screener agent not found")
    result = await agent.execute({
        "action": request.get("action", "pre_screen"),
        "company_profile": request.get("company_profile", {}),
        "limit": request.get("limit", 50),
    })
    return result

@router.get("/intelligence/pre-screen/narrowed")
async def get_narrowed_list():
    """Get cached narrowed tender list."""
    brain = get_brain()
    agent = brain.get_agent("agent-038-tender-pre-screener")
    if agent:
        result = await agent.execute({"action": "narrowed_list", "company_profile": {}})
        return result
    return {"status": "not_available"}

# ── Knowledge Graph ─────────────────────────────────────────────────

@router.get("/knowledge-graph/stats")
async def knowledge_graph_stats():
    """Knowledge Graph statistics adapted to our schema."""
    from app.db.base import get_session_factory
    from sqlalchemy import text
    sf = get_session_factory()
    async with sf() as s:
        try:
            stats = {}
            estimate_rows = await s.execute(
                text(
                    """
                    SELECT relname, GREATEST(reltuples::bigint, 0) AS est_count
                    FROM pg_class
                    WHERE relkind = 'r'
                      AND relname IN ('award_records_v2', 'procurement_tenders', 'contractor_dna')
                    """
                )
            )
            for row in estimate_rows.fetchall():
                stats[row[0]] = int(row[1] or 0)
            r = await s.execute(
                text(
                    "SELECT contractor_name, total_contracts, total_amount_bdt "
                    "FROM contractors "
                    "WHERE contractor_name IS NOT NULL AND contractor_name != '' "
                    "ORDER BY total_amount_bdt DESC NULLS LAST LIMIT 10"
                )
            )
            top = [{"name": row[0], "awards": int(row[1] or 0), "value": float(row[2] or 0)} for row in r.fetchall()]
            return {"status": "active", "stats": stats, "top_contractors": top}
        except Exception as e:
            return {"status": "error", "error": str(e)}

@router.get("/knowledge-graph/agency/{agency}")
async def agency_intelligence(agency: str):
    """Get agency intelligence profile."""
    from app.db.base import get_session_factory
    from sqlalchemy import text
    sf = get_session_factory()
    async with sf() as s:
        try:
            r = await s.execute(
                text("SELECT COUNT(*), COALESCE(SUM(amount_bdt),0) FROM award_records_v2 WHERE agency_code = :a"),
                {"a": agency}
            )
            row = r.fetchone()
            count = row[0] or 0
            total_val = float(row[1] or 0)
            r2 = await s.execute(
                text("SELECT contractor_name, COUNT(*) as c FROM award_records_v2 WHERE agency_code = :a "
                     "GROUP BY contractor_name ORDER BY c DESC LIMIT 10"),
                {"a": agency}
            )
            top = [{"name": row2[0], "awards": row2[1]} for row2 in r2.fetchall()]
            return {
                "agency": agency, "awards": count, "total_value": total_val,
                "avg_award": round(total_val / count, 2) if count else 0,
                "top_contractors": top,
            }
        except Exception as e:
            return {"agency": agency, "error": str(e)}

@router.get("/knowledge-graph/contractor/{name:path}")
async def contractor_dna(name: str):
    """Get contractor DNA profile."""
    kg = KnowledgeGraph()
    try:
        return kg.get_contractor_dna(name)
    except Exception as e:
        return {"name": name, "error": str(e)}

@router.get("/knowledge-graph/syndicate-patterns")
async def syndicate_patterns():
    """Detect bidder collusion patterns."""
    kg = KnowledgeGraph()
    return {"patterns": kg.find_syndicate_patterns()}

@router.get("/knowledge-graph/lifecycle/{tender_id}")
async def tender_lifecycle(tender_id: str):
    """Get full tender lifecycle."""
    kg = KnowledgeGraph()
    return kg.get_tender_lifecycle(tender_id)

# ── Watchdog Intelligence API ─────────────────────────────────────────

@router.get("/watchdog/health")
async def watchdog_health():
    """Get system health report."""
    from app.agents.core.watchdog import get_watchdog
    wd = get_watchdog(get_brain())
    report = await wd.generate_report()
    _log_ui_event("watchdog", "health", {
        "status": report.get("status"),
        "agent_down": report.get("agents", {}).get("down", 0),
        "error_count": report.get("error_count", 0),
    })
    return report

@router.get("/watchdog/dashboard")
async def watchdog_dashboard():
    """Get watchdog dashboard data."""
    from app.agents.core.watchdog import get_watchdog
    dashboard = get_watchdog().get_dashboard()
    _log_ui_event("watchdog", "dashboard", {
        "status": dashboard.get("status") if isinstance(dashboard, dict) else "ok",
    })
    return dashboard

@router.post("/watchdog/analyze")
async def watchdog_analyze(data: Dict[str, Any]):
    """Analyze an error and get solution."""
    from app.agents.core.watchdog import get_watchdog
    result = get_watchdog().analyze_error(
        source=data.get("source", "unknown"),
        error_msg=data.get("error_message", data.get("message", "")),
        error_type=data.get("error_type", "Unknown"),
    )
    _log_ui_event("watchdog", "analyze", {
        "source": data.get("source", "unknown"),
        "error_type": data.get("error_type", "Unknown"),
        "confidence": result.get("confidence"),
        "auto_fixable": result.get("auto_fixable"),
    })
    return result

@router.get("/watchdog/logs/{log_type}")
async def watchdog_logs(log_type: str, lines: int = 50):
    """Read log files. Types: errors, health, sessions."""
    import os, glob
    base = str(_RUNTIME_LOG_ROOT)
    if log_type == "sessions":
        sess_dir = os.path.join(base, "sessions")
        files = sorted(glob.glob(f"{sess_dir}/*.jsonl"), reverse=True)[:5]
        entries = []
        for f in files:
            with open(f) as fh:
                for l in fh.readlines()[-lines:]:
                    try:
                        entries.append(json.loads(l))
                    except Exception:
                        pass
        return {"entries": entries, "files": files}
    paths = {"errors": "system/errors.jsonl", "health": "system/health.jsonl"}
    log_path = os.path.join(base, paths.get(log_type, "system/health.jsonl"))
    if not os.path.exists(log_path):
        return {"entries": [], "error": "Log not found"}
    with open(log_path) as f:
        all_lines = f.readlines()
        entries = [json.loads(l) for l in all_lines[-lines:]]
    return {"entries": entries, "total": len(all_lines)}

@router.get("/watchdog/errors")
async def watchdog_errors(limit: int = Query(20)):
    """Get recent errors from watchdog."""
    from app.agents.core.watchdog import get_watchdog
    wd = get_watchdog()
    errors = wd._errors[-limit:] if wd._errors else []
    wd_errors = []
    for e in errors:
        try:
            wd_errors.append({
                "id": e.id, "source": e.source, "error_type": e.error_type,
                "error_message": e.error_message[:200],
                "severity": e.severity, "timestamp": e.timestamp,
                "resolved": e.resolved
            })
        except Exception:
            pass
    result = {"errors": wd_errors}
    _log_ui_event("watchdog", "errors", {"count": len(wd_errors), "limit": limit})
    return result

@router.get("/watchdog/sessions")
async def watchdog_sessions(limit: int = Query(10)):
    """Get recent session logs."""
    import os, glob, json
    sess_dir = _RUNTIME_LOG_ROOT / "sessions"
    sessions = []
    try:
        files = sorted(glob.glob(str(sess_dir / "*.jsonl")), reverse=True)[:limit]
        for f in files:
            try:
                with open(f) as fh:
                    lines = fh.readlines()
                    if lines:
                        last = json.loads(lines[-1])
                        sessions.append({"session_id": os.path.basename(f), "timestamp": last.get("ts", ""), "status": last.get("action", "ok")})
            except Exception:
                pass
    except Exception:
        pass
    result = {"sessions": sessions}
    _log_ui_event("watchdog", "sessions", {"count": len(sessions), "limit": limit})
    return result

# ── Intelligence Engineer API ────────────────────────────────────────

@router.get("/engineer/status")
async def engineer_status():
    """Get Intelligence Engineer system knowledge summary."""
    from app.agents.core.engineer import get_engineer
    eng = get_engineer()
    result = {
        "status": "active",
        "system_knowledge": eng.get_system_summary(),
        "component_map": eng.get_component_map(),
    }
    _log_ui_event("engineer", "status", {
        "total_components": result["system_knowledge"].get("total_components", 0),
        "agents": result["system_knowledge"].get("agents", 0),
    })
    return result

@router.post("/engineer/diagnose")
async def engineer_diagnose(data: Dict[str, Any]):
    """Diagnose an error with Intelligence Engineer."""
    from app.agents.core.engineer import get_engineer
    eng = get_engineer()
    result = eng.diagnose(
        source=data.get("source", "unknown"),
        error_msg=data.get("error_message", ""),
        error_type=data.get("error_type", "Unknown"),
        context=data.get("context", {}),
    )
    _log_ui_event("engineer", "diagnose", {
        "source": data.get("source", "unknown"),
        "error_type": data.get("error_type", "Unknown"),
        "confidence": result.get("confidence"),
    })
    return result

@router.get("/engineer/components/{component_type}")
async def engineer_components(component_type: str = None):
    """Get system components by type."""
    from app.agents.core.engineer import get_engineer
    eng = get_engineer()
    cmap = eng.get_component_map()
    if component_type:
        result = {"type": component_type, "components": cmap.get(component_type, [])}
        _log_ui_event("engineer", "components", {"type": component_type, "count": len(result["components"])})
        return result
    _log_ui_event("engineer", "components", {"type": "all", "count": sum(len(v) for v in cmap.values())})
    return cmap

@router.get("/engineer/fixes/{fix_type}")
async def engineer_fixes(fix_type: str = None):
    """Get available fix procedures."""
    from app.agents.core.engineer import get_engineer
    eng = get_engineer()
    fixes = eng._fix_library
    if fix_type:
        result = {"type": fix_type, "fixes": fixes.get(fix_type, [])}
        _log_ui_event("engineer", "fixes", {"type": fix_type, "count": len(result["fixes"])})
        return result
    result = {"fix_library": {k: [f["issue"] for f in v] for k, v in fixes.items()}}
    _log_ui_event("engineer", "fixes", {"type": "all", "count": len(result["fix_library"])})
    return result

# ── SOR API ──────────────────────────────────────────────────────────

@router.get("/sor/zones")
async def sor_zones(agency: str = Query("BWDB")):
    """Get zone definitions for an agency."""
    try:
        from app.agents.pricing.sor_zone_matcher import DISTRICT_ZONES, ZONE_LABELS
        zones = DISTRICT_ZONES.get(agency.upper(), {})
        labels = ZONE_LABELS.get(agency.upper(), {})
        return {
            "agency": agency.upper(),
            "zones": {z: {"districts": zones[z], "label": labels.get(z, f"Zone-{z}")} for z in zones}
        }
    except Exception as e:
        return {"agency": agency.upper(), "error": str(e)}

@router.get("/sor/status")
async def sor_status():
    """SOR system status."""
    try:
        from app.sor.sor_service import SORService
        svc = SORService()
        if not svc._loaded:
            svc.load_all()
        agencies = {}
        for ag in ["BWDB", "PWD", "LGED"]:
            agencies[ag] = {"items": len(svc._rates.get(ag, []))}
        import os, json
        sor_base = os.path.join(os.path.dirname(__file__), "..", "sor")
        bwdb_json = 0
        try:
            bwdb_json = len(json.loads(open(os.path.join(sor_base, "bwdb", "rates.json"), encoding="utf-8").read()))
        except Exception:
            pass
        return {"status": "active", "agencies": agencies, "bwdb_json_rates": bwdb_json}
    except Exception as e:
        return {"status": "error", "error": str(e)}

# ── Agencies ─────────────────────────────────────────────────────────

@router.get("/agencies")
async def list_agencies():
    """List all agencies with stats."""
    from app.db.base import get_session_factory
    from sqlalchemy import text
    sf = get_session_factory()
    async with sf() as s:
        try:
            r = await s.execute(
                text("SELECT pt.agency_code, COUNT(*) as cnt, COALESCE(SUM(ar.estimated_cost_bdt),0) as val "
                     "FROM app_records ar "
                     "JOIN procurement_tenders pt ON pt.id = ar.procurement_tender_id "
                     "WHERE pt.agency_code IS NOT NULL AND pt.agency_code != '' "
                     "GROUP BY pt.agency_code ORDER BY cnt DESC")
            )
            ag = {}
            for row in r.fetchall():
                ag[row[0]] = {"tenders": row[1], "total_value": float(row[2] or 0)}
            r2 = await s.execute(
                text("SELECT agency_code, COUNT(*) as cnt, COALESCE(SUM(amount_bdt),0) as val "
                     "FROM award_records_v2 WHERE agency_code IS NOT NULL AND agency_code != '' "
                     "GROUP BY agency_code ORDER BY cnt DESC")
            )
            for row in r2.fetchall():
                if row[0] in ag:
                    ag[row[0]].update({"awards": row[1], "awarded_value": float(row[2] or 0)})
                else:
                    ag[row[0]] = {"awards": row[1], "awarded_value": float(row[2] or 0)}
            return {
                "agencies": [{"name": k, **v} for k, v in sorted(ag.items(),
                              key=lambda x: x[1].get('tenders', 0), reverse=True)]
            }
        except Exception as e:
            return {"agencies": [], "error": str(e)}

# ── API Root ─────────────────────────────────────────────────────────

@router.get("/")
async def api_info():
    return {
        "name": "ProcureFlow API",
        "version": "3.0.0",
        "docs": "/docs",
    }

# ── Brain Knowledge ──────────────────────────────────────────────────

@router.get("/brain/knowledge")
async def brain_knowledge(
    type: str = Query(""),
    limit: int = Query(20),
    tender_id: str = Query("")
):
    """Query knowledge entries from brain."""
    brain = get_brain()
    entries = await brain.query_knowledge(
        entry_type=type if type else None,
        tender_id=tender_id if tender_id else None,
        limit=limit
    )
    for entry in entries:
        entry["data"] = _decode_jsonish(entry.get("data"))
        entry["tags"] = _decode_jsonish(entry.get("tags"))
    return {"entries": entries}
