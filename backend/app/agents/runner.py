#!/usr/bin/env python3
"""
Procurement Flow Specialist BD — CLI Runner
"""
import argparse
import asyncio
import json
import logging
import sys

from . import AgentRegistry, AgentStatus
from .tender_radar import TenderRadarAgent
from .tender_acquisition import TenderAcquisitionAgent
from .corrigendum_watchdog import CorrigendumWatchdogAgent
from .document_ai import DocumentAIAgent
from .boq_intelligence import BOQIntelligenceAgent
from .spec_intelligence import SpecIntelligenceAgent
from .eligibility_compliance import EligibilityComplianceAgent
from .risk_intelligence import RiskIntelligenceAgent
from .ppr_evaluation import PPREvaluationAgent
from .lert_prediction import LERTPredictionAgent
from .rate_analysis import RateAnalysisAgent
from .market_rate_intelligence import MarketRateIntelligenceAgent
from .competitor_intelligence import CompetitorIntelligenceAgent
from .award_intelligence import AwardIntelligenceAgent
from .competitor_pricing_predictor import CompetitorPricingPredictorAgent
from .win_probability import WinProbabilityAgent
from .bid_position_optimizer import BidPositionOptimizerAgent
from .ai_bid_assistant import AIBidAssistantAgent
from .resource_capacity import ResourceCapacityAgent
from .financial_intelligence import FinancialIntelligenceAgent
from .executive_decision import ExecutiveDecisionAgent
from .egp_rate_fill import EGPRateFillAgent
from .submission_validation import SubmissionValidationAgent
from .report_generation import ReportGenerationAgent
from .knowledge_lake import KnowledgeLakeAgent
from .learning_agent import LearningAgent
from .syndicate_radar import SyndicateRadarAgent
from .ra_bill_predictor import RABillPredictorAgent
from .vision_intelligence import VisionIntelligenceAgent
from .orchestrator import WorkflowOrchestrator
from .whatsapp_agent import WhatsAppAutomationAgent
from .ppr2025_compliance import PPR2025ComplianceAgent
from .vat_tax_agent import VatTaxCalculatorAgent
from .tender_document_agent import TenderDocumentAgent
from .tender_preparation import TenderPreparationAgent
from ..config import config

logger = logging.getLogger("procureflow.runner")

AGENT_CLASSES = [
    TenderRadarAgent, TenderAcquisitionAgent, CorrigendumWatchdogAgent,
    DocumentAIAgent, BOQIntelligenceAgent, SpecIntelligenceAgent,
    EligibilityComplianceAgent, RiskIntelligenceAgent, PPREvaluationAgent,
    LERTPredictionAgent, RateAnalysisAgent, MarketRateIntelligenceAgent,
    CompetitorIntelligenceAgent, AwardIntelligenceAgent, CompetitorPricingPredictorAgent,
    WinProbabilityAgent, BidPositionOptimizerAgent, AIBidAssistantAgent,
    ResourceCapacityAgent, FinancialIntelligenceAgent, ExecutiveDecisionAgent,
    EGPRateFillAgent, SubmissionValidationAgent, ReportGenerationAgent,
    KnowledgeLakeAgent, LearningAgent,
    SyndicateRadarAgent, RABillPredictorAgent, VisionIntelligenceAgent,
    WorkflowOrchestrator,
    WhatsAppAutomationAgent, PPR2025ComplianceAgent, VatTaxCalculatorAgent,
    TenderDocumentAgent, TenderPreparationAgent,
]


def setup_logging(verbose: bool = False):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def get_registry() -> AgentRegistry:
    registry = AgentRegistry()
    for cls in AGENT_CLASSES:
        registry.register(cls())
    return registry


async def cmd_list(args):
    registry = get_registry()
    agents = registry.list_agents()
    print(f"\n{'Agent ID':35s} {'Name':30s} {'Status':12s} {'Version':8s}")
    print("-" * 85)
    for a in agents:
        print(f"{a['agent_id']:35s} {a['agent_name']:30s} {a['status']:12s} {a['version']:8s}")
    print(f"\nTotal: {len(agents)} agents registered\n")


async def cmd_info(args):
    registry = get_registry()
    agent = registry.get(args.agent_id)
    if not agent:
        print(f"Error: Agent '{args.agent_id}' not found")
        sys.exit(1)
    info = agent.info()
    print(f"\n{'Key':25s} Value")
    print("-" * 60)
    for k, v in info.items():
        if isinstance(v, list):
            print(f"{k:25s} {', '.join(v)}")
        else:
            print(f"{k:25s} {v}")
    print()


async def cmd_run(args):
    registry = get_registry()
    context = json.loads(args.context) if args.context else {}
    result = await registry.run_agent(args.agent_id, context)
    print(json.dumps(result.to_dict(), indent=2, default=str))


async def cmd_pipeline(args):
    registry = get_registry()
    orch = registry.get("agent-027-orchestrator")
    if not orch:
        print("Error: Orchestrator not found")
        sys.exit(1)
    context = {"mode": args.mode}
    if args.phase:
        context["phase"] = args.phase
    if args.agents:
        context["agent_ids"] = args.agents.split(",")
    if args.context:
        context.update(json.loads(args.context))
    result = await orch.run(context)
    print(json.dumps(result.to_dict(), indent=2, default=str))


async def cmd_phases(args):
    from .orchestrator import PIPELINE_DEFINITION, PipelinePhase
    print(f"\n{'Phase':20s} {'Agents':10s} {'Agent IDs'}")
    print("-" * 70)
    for phase in PipelinePhase:
        agents = PIPELINE_DEFINITION[phase]
        names = ", ".join(a.split("-")[-1] for a in agents)
        print(f"{phase.value:20s} {len(agents):<10d} {names}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Procurement Flow Specialist BD — AI Tender Operating System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m app.agents.runner list
  python -m app.agents.runner info agent-001-tender-radar
  python -m app.agents.runner run agent-001-tender-radar --context '{"tender_id":"eGP-001"}'
  python -m app.agents.runner pipeline --mode full
  python -m app.agents.runner pipeline --mode phase --phase discovery
  python -m app.agents.runner phases
        """,
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Debug logging")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List all agents")
    info_p = sub.add_parser("info", help="Show agent details")
    info_p.add_argument("agent_id", help="Agent ID")
    run_p = sub.add_parser("run", help="Run a single agent")
    run_p.add_argument("agent_id", help="Agent ID")
    run_p.add_argument("--context", "-c", default="{}", help="JSON context")
    pipe_p = sub.add_parser("pipeline", help="Run pipeline")
    pipe_p.add_argument("--mode", "-m", default="full", choices=["full","phase","agents"])
    pipe_p.add_argument("--phase", "-p", help="Phase name")
    pipe_p.add_argument("--agents", "-a", help="Comma-separated agent IDs")
    pipe_p.add_argument("--context", "-c", default="{}", help="JSON context")
    sub.add_parser("phases", help="List pipeline phases")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    setup_logging(args.verbose)

    cmds = {
        "list": cmd_list, "info": cmd_info, "run": cmd_run,
        "pipeline": cmd_pipeline, "phases": cmd_phases,
    }
    asyncio.run(cmds[args.command](args))


if __name__ == "__main__":
    main()
