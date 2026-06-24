"""Procurement Flow Specialist BD — Agent System
47 specialized agents organized by capability domain.
"""
from .core.base import BaseAgent, AgentResult, AgentStatus
from .core.brain import AgentBrain, BrainMessage, AgentCapability

# Discovery
from .discovery import TenderRadarAgent, TenderAcquisitionAgent, CorrigendumWatchdogAgent, VisionIntelligenceAgent

# Intelligence
from .intelligence import BOQIntelligenceAgent, SpecIntelligenceAgent, AwardIntelligenceAgent, ResourceCapacityAgent, APPForecastAgent

# Evaluation
from .evaluation import PPREvaluationAgent, PPR2025ComplianceAgent, LERTPredictionAgent, EligibilityComplianceAgent, RiskIntelligenceAgent

# Pricing
from .pricing import MarketRateIntelligenceAgent, RateAnalysisAgent, RABillPredictorAgent, VatTaxCalculatorAgent, EGPRateFillAgent, SORZoneMatcherAgent

# Competitor
from .competitor import WinProbabilityAgent, BidPositionOptimizerAgent, CompetitorIntelligenceAgent, CompetitorPricingPredictorAgent, SyndicateRadarAgent

# Decision
from .decision import FinancialIntelligenceAgent, ExecutiveDecisionAgent, AIBidAssistantAgent, BidNoBidAgent, ClientIntelligenceAgent

# Acquisition
from .acquisition import DocumentPreparationAgent, DocumentAIAgent, TenderDocumentAgent, SubmissionValidationAgent, TenderPreparationAgent, TenderDashboardAgent, OpeningReportAgent

# Knowledge & Learning
from .knowledge import KnowledgeLakeAgent, ReportGenerationAgent, CompanyBrainAgent, MarketBrainAgent
from .learning import LearningAgent

# Pre-emptive Intelligence (New)
from .competitor import MoatSLTAnalyzerAgent
from .evaluation import PPR2025DashboardAgent
from .discovery import TenderPreScreenerAgent
from .knowledge.company_brain import CompanyBrainAgent
from .knowledge.market_brain import MarketBrainAgent
from .intelligence.app_forecast import APPForecastAgent
from .decision.bid_decision import BidNoBidAgent
from .decision.client_intelligence import ClientIntelligenceAgent

# Legacy agents (still needed)
from .registry import AgentRegistry
from .orchestrator import WorkflowOrchestrator
from .portal_explorer import PortalExplorer
from .whatsapp_agent import WhatsAppAutomationAgent

__all__ = [
    "BaseAgent", "AgentResult", "AgentStatus", "AgentBrain", "BrainMessage", "AgentCapability",
    "TenderRadarAgent", "TenderAcquisitionAgent", "CorrigendumWatchdogAgent", "VisionIntelligenceAgent",
    "BOQIntelligenceAgent", "SpecIntelligenceAgent", "AwardIntelligenceAgent", "ResourceCapacityAgent",
    "PPREvaluationAgent", "PPR2025ComplianceAgent", "LERTPredictionAgent", "EligibilityComplianceAgent", "RiskIntelligenceAgent",
    "MarketRateIntelligenceAgent", "RateAnalysisAgent", "RABillPredictorAgent", "VatTaxCalculatorAgent", "EGPRateFillAgent",
    "WinProbabilityAgent", "BidPositionOptimizerAgent", "CompetitorIntelligenceAgent", "CompetitorPricingPredictorAgent", "SyndicateRadarAgent",
    "FinancialIntelligenceAgent", "ExecutiveDecisionAgent", "AIBidAssistantAgent",
    "DocumentPreparationAgent", "DocumentAIAgent", "TenderDocumentAgent", "SubmissionValidationAgent", "TenderPreparationAgent", "TenderDashboardAgent", "OpeningReportAgent",
    "KnowledgeLakeAgent", "ReportGenerationAgent", "LearningAgent",
    "MoatSLTAnalyzerAgent", "PPR2025DashboardAgent", "TenderPreScreenerAgent", "SORZoneMatcherAgent", "BidNoBidAgent", "ClientIntelligenceAgent", "CompanyBrainAgent", "MarketBrainAgent", "APPForecastAgent",
    "AgentRegistry", "WorkflowOrchestrator", "PortalExplorer", "WhatsAppAutomationAgent",
]

# Watchdog & Error Intelligence
from app.agents.core.watchdog import AgentWatchdog, get_watchdog

# Intelligence Engineer
from app.agents.core.engineer import IntelligenceEngineer, get_engineer
