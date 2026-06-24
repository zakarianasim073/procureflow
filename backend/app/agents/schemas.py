"""
Shared data schemas for agent communication.
All agents use these typed payloads for input/output.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
from decimal import Decimal

# Re-export from agent_schemas.py for backward compatibility
from app.agent_schemas import *

# Add new schemas for enhanced agents

@dataclass
class OpeningReportSchema:
    """Opening report data structure."""
    tender_id: str = ""
    package_no: str = ""
    work_name: str = ""
    pe_office: str = ""
    zone: str = ""
    opening_date: str = ""
    estimated_amount: float = 0.0
    bidders: List[Dict] = field(default_factory=list)
    winner: Optional[Dict] = None
    has_slt: bool = False
    has_alt: bool = False


@dataclass
class TenderPreparationSchema:
    """Tender preparation workflow data."""
    tender_id: str = ""
    forms_required: List[str] = field(default_factory=list)
    forms_completed: List[str] = field(default_factory=list)
    forms_missing: List[str] = field(default_factory=list)
    document_map: Dict[str, str] = field(default_factory=dict)
    completeness_pct: float = 0.0
    status: str = "not_started"
    critical_alerts: List[str] = field(default_factory=list)


@dataclass
class ComplianceFindingSchema:
    """Compliance finding with evidence."""
    check_name: str = ""
    passed: bool = False
    score: float = 0.0
    max_score: float = 1.0
    severity: str = "info"
    evidence: List[str] = field(default_factory=list)
    recommendation: str = ""
    is_critical: bool = False


__all__ = [
    "OpeningReportSchema", "TenderPreparationSchema", "ComplianceFindingSchema",
]
