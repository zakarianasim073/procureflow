"""
Procurement Flow Specialist BD — Shared Data Schemas
Typed payloads exchanged between agents.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
from decimal import Decimal


# ---------------------------------------------------------------------------
# Agent 1 — Tender Radar
# ---------------------------------------------------------------------------

@dataclass
class TenderAlert:
    tender_id: str
    title: str
    procuring_entity: str
    source: str  # eGP, BPPA, agency website
    match_score: float
    estimated_value_bdt: float
    deadline: str
    url: str = ""
    category: str = ""
    location: str = ""


# ---------------------------------------------------------------------------
# Agent 2 — Tender Acquisition
# ---------------------------------------------------------------------------

@dataclass
class TenderDocument:
    tender_id: str
    documents: Dict[str, str] = field(default_factory=dict)  # type → path/url
    nit_path: str = ""
    boq_path: str = ""
    drawings_path: str = ""
    corrigendum_path: str = ""
    specifications_path: str = ""


# ---------------------------------------------------------------------------
# Agent 3 — Corrigendum Watchdog
# ---------------------------------------------------------------------------

@dataclass
class CorrigendumChange:
    tender_id: str
    field_changed: str
    old_value: str
    new_value: str
    detected_at: str = ""


# ---------------------------------------------------------------------------
# Agent 4 — Document AI
# ---------------------------------------------------------------------------

@dataclass
class TenderProfile:
    tender_id: str
    eligibility_requirements: Dict[str, Any] = field(default_factory=dict)
    experience_required: str = ""
    turnover_required: float = 0.0
    emd_amount: float = 0.0
    completion_period_days: int = 0
    special_conditions: List[str] = field(default_factory=list)
    sections: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Agent 5 — BOQ Intelligence
# ---------------------------------------------------------------------------

@dataclass
class BOQItem:
    item_no: int
    description: str
    unit: str
    quantity: float
    rate: float = 0.0
    amount: float = 0.0
    sor_code: str = ""
    category: str = ""
    is_valid: bool = True
    validation_notes: str = ""


# ---------------------------------------------------------------------------
# Agent 6 — Specification Intelligence
# ---------------------------------------------------------------------------

@dataclass
class Specification:
    spec_id: str = ""
    title: str = ""
    requirements: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    special_materials: List[str] = field(default_factory=list)
    standards: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent 7 — Eligibility & Compliance
# ---------------------------------------------------------------------------

@dataclass
class EligibilityCriteria:
    compliant: bool = False
    experience_met: bool = False
    turnover_met: bool = False
    equipment_met: bool = False
    personnel_met: bool = False
    licenses_met: bool = False
    missing_items: List[str] = field(default_factory=list)
    notes: str = ""


# ---------------------------------------------------------------------------
# Agent 8 — Risk Intelligence
# ---------------------------------------------------------------------------

@dataclass
class RiskProfile:
    risk_level: str = "Low"  # Low, Medium, High
    ld_rate: float = 0.0
    ld_risk: str = ""
    guarantee_required: float = 0.0
    guarantee_risk: str = ""
    retention_percent: float = 0.0
    retention_risk: str = ""
    insurance_requirements: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent 9 — PPR 2025 Evaluation
# ---------------------------------------------------------------------------

@dataclass
class PPREvaluation:
    responsive: bool = False
    arithmetic_errors: List[str] = field(default_factory=list)
    qualification_met: bool = False
    ppr_rules_validated: bool = False
    slt_analysis: str = ""
    evaluation_notes: str = ""


# ---------------------------------------------------------------------------
# Agent 10 — LERT Prediction
# ---------------------------------------------------------------------------

@dataclass
class LERTPrediction:
    lert_probability: float = 0.0
    estimated_lert_amount: float = 0.0
    ranked_bidders: List[Dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 0.0
    factors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent 11 — Rate Analysis
# ---------------------------------------------------------------------------

@dataclass
class RateAnalysis:
    item_no: int = 0
    description: str = ""
    material_cost: float = 0.0
    labor_cost: float = 0.0
    equipment_cost: float = 0.0
    overhead_percent: float = 0.0
    profit_percent: float = 0.0
    recommended_rate: float = 0.0
    sor_rate: float = 0.0
    notes: str = ""


# ---------------------------------------------------------------------------
# Agent 12 — Market Rate Intelligence
# ---------------------------------------------------------------------------

@dataclass
class MarketRate:
    material_name: str = ""
    current_price: float = 0.0
    unit: str = ""
    source: str = ""
    last_updated: str = ""
    price_trend: str = ""  # stable, rising, falling
    vendor: str = ""


# ---------------------------------------------------------------------------
# Agent 13 — Competitor Intelligence
# ---------------------------------------------------------------------------

@dataclass
class CompetitorProfile:
    company_name: str = ""
    win_rate: float = 0.0
    total_bids: int = 0
    total_wins: int = 0
    avg_discount: float = 0.0
    preferred_agencies: List[str] = field(default_factory=list)
    avg_bid_value: float = 0.0
    specializations: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent 14 — Award Intelligence
# ---------------------------------------------------------------------------

@dataclass
class AwardRecord:
    tender_id: str = ""
    title: str = ""
    procuring_entity: str = ""
    winner: str = ""
    award_amount: float = 0.0
    award_date: str = ""
    num_bidders: int = 0
    discount_percent: float = 0.0
    contract_period_days: int = 0


# ---------------------------------------------------------------------------
# Agent 15 — Competitor Pricing Predictor
# ---------------------------------------------------------------------------

@dataclass
class PricingPrediction:
    competitor_name: str = ""
    expected_discount_percent: float = 0.0
    expected_rate: float = 0.0
    confidence: float = 0.0
    historical_pattern: str = ""
    predicted_range: str = ""


# ---------------------------------------------------------------------------
# Agent 16 — Win Probability
# ---------------------------------------------------------------------------

@dataclass
class WinProbability:
    probability: float = 0.0
    key_factors: List[str] = field(default_factory=list)
    strength_score: float = 0.0
    weakness_score: float = 0.0
    recommendation: str = ""


# ---------------------------------------------------------------------------
# Agent 17 — Bid Position Optimizer
# ---------------------------------------------------------------------------

@dataclass
class BidRecommendation:
    recommended_amount: float = 0.0
    recommended_discount: float = 0.0
    margin_percent: float = 0.0
    slt_avoided: bool = False
    rank_prediction: int = 0
    confidence: str = ""
    breakdown: Dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Agent 18 — AI Bid Assistant
# ---------------------------------------------------------------------------

@dataclass
class AIAssistantOutput:
    should_bid: bool = False
    reason: str = ""
    resource_ok: bool = False
    margin_ok: bool = False
    risk_ok: bool = False
    competition_ok: bool = False
    recommendation: str = ""


# ---------------------------------------------------------------------------
# Agent 19 — Resource Capacity
# ---------------------------------------------------------------------------

@dataclass
class ResourceCapacity:
    capacity_percent: float = 0.0
    equipment_available: bool = False
    engineers_available: int = 0
    ongoing_projects: int = 0
    max_projects: int = 0
    can_take_project: bool = False
    constraints: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent 20 — Financial Intelligence
# ---------------------------------------------------------------------------

@dataclass
class FinancialForecast:
    expected_revenue: float = 0.0
    expected_cost: float = 0.0
    expected_profit: float = 0.0
    margin_percent: float = 0.0
    cash_flow_ok: bool = False
    working_capital_required: float = 0.0
    working_capital_available: float = 0.0
    risk_adjustment: float = 0.0


# ---------------------------------------------------------------------------
# Agent 21 — Executive Decision
# ---------------------------------------------------------------------------

@dataclass
class ExecutiveDecision:
    decision: str = ""  # BID, NO_BID, DEFER
    risk_level: str = "Medium"
    win_chance: float = 0.0
    expected_profit: float = 0.0
    expected_profit_bdt: str = ""
    confidence: str = "Medium"
    summary: str = ""
    agent_summaries: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Agent 22 — EGP Rate Fill
# ---------------------------------------------------------------------------

@dataclass
class EGPFillData:
    ready_for_fill: bool = False
    total_items: int = 0
    matched_items: int = 0
    unmatched_items: int = 0
    fill_data: List[Dict[str, Any]] = field(default_factory=list)
    notes: str = ""


# ---------------------------------------------------------------------------
# Agent 23 — Submission Validation
# ---------------------------------------------------------------------------

@dataclass
class SubmissionCheck:
    safe: bool = False
    item_count_match: bool = False
    rate_match: bool = False
    total_match: bool = False
    discrepancies: List[str] = field(default_factory=list)
    validation_score: float = 0.0


# ---------------------------------------------------------------------------
# Agent 24 — Report Generation
# ---------------------------------------------------------------------------

@dataclass
class Report:
    report_type: str = ""  # technical, commercial, executive
    title: str = ""
    content: str = ""
    file_path: str = ""
    generated_at: str = ""
    sections: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Agent 25 — Knowledge Lake
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeEntry:
    entry_type: str = ""  # tender, boq, award, competitor, rate, report
    tender_id: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    stored_at: str = ""
    checksum: str = ""
