"""Database layer: models, connection, ETL pipeline."""
# Legacy exports (from old base.py)
from .base import get_async_session, get_db

# New exports (from new database.py + models.py)
from .database import (
    get_engine, get_session, init_db, close_db, get_sync_session,
    get_sync_engine, get_database_backend, get_database_summary, session_scope,
)
from .models import (
    Base,
    RateAnalysis,
    Tenant, User, Organization,
    Tender, Award, APPRecord, Contractor, Lifecycle,
    AgentResult, AgentLog, AgentJob, AgentBrainMessage,
    KnowledgeEntry, OpeningReport, Document,
    Ruleset, PPRSchedule, ComplianceCheck,
    FeedbackLabel, TenderPreparation,
    TenderDataPool, TenderDocument, TenderReport,
    AgentThought, PreComputedIntelligence,
    ClientSubscription, SubscriptionPlan, ClientPriorityState,
    TenderUsageLog, NPPRecord, PPREvaluation,
)

__all__ = [
    "get_engine", "get_session", "init_db", "close_db", "get_sync_session",
    "get_sync_engine", "get_database_backend", "get_database_summary", "session_scope",
    "Base",
    "get_async_session", "get_db",
    "Tenant", "User", "Organization",
    "Tender", "Award", "APPRecord", "Contractor", "Lifecycle",
    "AgentResult", "AgentLog", "AgentJob", "AgentBrainMessage",
    "KnowledgeEntry", "OpeningReport", "Document",
    "Ruleset", "PPRSchedule", "ComplianceCheck",
    "FeedbackLabel", "TenderPreparation",
    "RateAnalysis",
    "TenderDataPool", "TenderDocument", "TenderReport",
    "AgentThought", "PreComputedIntelligence",
    "ClientSubscription", "SubscriptionPlan", "ClientPriorityState",
    "TenderUsageLog", "NPPRecord", "PPREvaluation",
]
