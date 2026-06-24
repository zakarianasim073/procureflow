"""
Legacy agent schemas for backward compatibility.
Contains all original typed payloads exchanged between agents.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
from decimal import Decimal

# Agent 1 — Tender Radar
@dataclass
class TenderAlert:
    tender_id: str = ""
    title: str = ""
    procuring_entity: str = ""
    source: str = "egp"
    match_score: float = 0.0
    estimated_value_bdt: float = 0.0
    deadline: str = ""
    url: str = ""
    category: str = ""
    location: str = ""

# Agent 2 — Tender Acquisition
@dataclass
class TenderDocument:
    tender_id: str = ""
    documents: Dict[str, str] = field(default_factory=dict)
    nit_path: str = ""
    boq_path: str = ""
    drawings_path: str = ""
    corrigendum_path: str = ""
    specifications_path: str = ""

# Agent 3 — Corrigendum Watchdog
@dataclass
class CorrigendumChange:
    tender_id: str = ""
    field_changed: str = ""
    old_value: str = ""
    new_value: str = ""
    detected_at: str = ""

# Agent 4 — Document AI
@dataclass
class TenderProfile:
    tender_id: str = ""
    eligibility_requirements: Dict[str, Any] = field(default_factory=dict)
    experience_required: str = ""
    turnover_required: float = 0.0
    emd_amount: float = 0.0
    completion_period_days: int = 0
    special_conditions: List[str] = field(default_factory=list)
    sections: Dict[str, str] = field(default_factory=dict)

# Agent 5 — BOQ Intelligence
@dataclass
class BOQItem:
    item_no: int = 0
    description: str = ""
    unit: str = ""
    quantity: float = 0.0
    rate: float = 0.0
    amount: float = 0.0
    sor_code: str = ""
    category: str = ""
    is_valid: bool = True
    validation_notes: str = ""

# Agent 9 — PPR Evaluation
@dataclass
class PPREvaluation:
    responsive: bool = False
    arithmetic_errors: List[str] = field(default_factory=list)
    qualification_met: bool = False
    ppr_rules_validated: bool = False
    slt_analysis: str = ""
    evaluation_notes: str = ""

# Agent 10 — LERT Prediction
@dataclass
class LERTPrediction:
    lert_probability: float = 0.0
    estimated_lert_amount: float = 0.0
    ranked_bidders: List[Dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 0.0
    factors: List[str] = field(default_factory=list)

# Agent 16 — Win Probability
@dataclass
class WinProbability:
    probability: float = 0.0
    key_factors: List[str] = field(default_factory=list)
    strength_score: float = 0.0
    weakness_score: float = 0.0
    recommendation: str = ""

# Agent 25 — Knowledge Lake
@dataclass
class KnowledgeEntry:
    entry_type: str = ""
    tender_id: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    stored_at: str = ""
    checksum: str = ""

__all__ = [
    "TenderAlert", "TenderDocument", "CorrigendumChange",
    "TenderProfile", "BOQItem", "PPREvaluation",
    "LERTPrediction", "WinProbability", "KnowledgeEntry",
]

# Agent 7 — Eligibility & Compliance
@dataclass
class EligibilityCriteria:
    required_experience_years: int = 0
    required_turnover_bdt: float = 0.0
    required_equipment: List[str] = field(default_factory=list)
    required_personnel: List[str] = field(default_factory=list)
    required_licenses: List[str] = field(default_factory=list)
    similar_works_required: int = 0
    special_conditions: List[str] = field(default_factory=list)
    meets_criteria: bool = False
    missing_requirements: List[str] = field(default_factory=list)
    missing_items: List[str] = field(default_factory=list)

# Agent 8 — Risk Intelligence
@dataclass
class RiskProfile:
    tender_id: str = ""
    ld_rate: float = 0.0
    ld_max_percent: float = 10.0
    requires_performance_guarantee: bool = True
    pg_percent: float = 5.0
    retention_percent: float = 0.0
    insurance_required: bool = False
    warranty_period_months: int = 0
    risk_score: float = 0.0
    risk_level: str = "low"
    risks: List[str] = field(default_factory=list)
    mitigations: List[str] = field(default_factory=list)

# Agent 11 — Rate Analysis
@dataclass
class RateAnalysis:
    tender_id: str = ""
    item_code: str = ""
    description: str = ""
    sor_rate: float = 0.0
    market_rate: float = 0.0
    variance_percent: float = 0.0
    analysis_date: str = ""

# Agent 12 — Market Rate Intelligence
@dataclass
class MarketRate:
    item_code: str = ""
    item_name: str = ""
    unit: str = ""
    current_rate: float = 0.0
    previous_rate: float = 0.0
    change_percent: float = 0.0
    source: str = ""
    updated_at: str = ""

# Agent 13 — Competitor Intelligence
@dataclass
class CompetitorProfile:
    name: str = ""
    registration_no: str = ""
    total_tenders: int = 0
    total_wins: int = 0
    win_rate: float = 0.0
    preferred_agencies: List[str] = field(default_factory=list)
    average_discount: float = 0.0
    average_bid_amount: float = 0.0
    zones: List[str] = field(default_factory=list)

# Agent 15 — Competitor Pricing Predictor
@dataclass
class PricingPrediction:
    tender_id: str = ""
    predicted_lowest_bid: float = 0.0
    predicted_winning_discount: float = 0.0
    confidence: float = 0.0
    competitors_expected: int = 0

# Agent 17 — Bid Position Optimizer
@dataclass
class BidPosition:
    tender_id: str = ""
    recommended_discount: float = 0.0
    conservative_range: tuple = (0.0, 0.0)
    balanced_range: tuple = (0.0, 0.0)
    aggressive_range: tuple = (0.0, 0.0)
    expected_margin: float = 0.0
    winning_probability: float = 0.0

# Agent 19 — Resource Capacity
@dataclass
class ResourceAvailability:
    equipment_available: Dict[str, int] = field(default_factory=dict)
    personnel_available: Dict[str, int] = field(default_factory=dict)
    ongoing_projects: int = 0
    available_capacity_percent: float = 100.0

# Agent 22 — Executive Decision
@dataclass
class ExecutiveRecommendation:
    decision: str = ""  # BID / NO_BID / CAUTION
    confidence_score: float = 0.0
    reasoning: List[str] = field(default_factory=list)
    factors: Dict[str, float] = field(default_factory=dict)

# Agent 28 — Syndicate Radar
@dataclass
class SyndicatePattern:
    tender_id: str = ""
    bidders: List[str] = field(default_factory=list)
    pattern_type: str = ""
    confidence: float = 0.0
    recommendation: str = ""
