"""
Intelligence models — PostgreSQL-backed procurement intelligence layer.
Replaces JSON file reads with SQLAlchemy ORM queries.
"""
from sqlalchemy import String, Integer, Float, DateTime, Text, Boolean, JSON, BigInteger, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid

from .base import Base, TimestampMixin, UUIDMixin


def func_lower(column):
    """Return a SQL expression for LOWER(column)."""
    from sqlalchemy import func
    return func.lower(column)


class Agency(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "agencies"

    agency_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    agency_name: Mapped[str] = mapped_column(String(300), nullable=False)
    ministry: Mapped[str] = mapped_column(String(300), nullable=False)
    keyword: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    def __repr__(self) -> str:
        return f"<Agency {self.agency_code}>"


class Zone(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "zones"

    zone_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    zone_type: Mapped[str] = mapped_column(String(20), nullable=False, default="district")
    parent_zone_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    def __repr__(self) -> str:
        return f"<Zone {self.zone_name}>"


class ProcurementTender(Base, TimestampMixin, UUIDMixin):
    """Core tender table — package_no is the unique identifier."""
    __tablename__ = "procurement_tenders"

    package_no: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    agency_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    zone_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    pe_office: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    procurement_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    match_type: Mapped[str] = mapped_column(String(20), nullable=False, default="unmatched_app")

    __table_args__ = (
        Index("ix_pt_package_lower", func_lower("package_no")),
        UniqueConstraint("package_no", name="uq_pt_package"),
    )


class APPRecord(Base, TimestampMixin, UUIDMixin):
    """APP planned procurement record (1:1 with ProcurementTender)."""
    __tablename__ = "app_records"

    procurement_tender_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_tender_id: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estimated_cost_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    published_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    deadline: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    financial_year: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    app_code: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class LiveTenderSource(Base, TimestampMixin, UUIDMixin):
    """Current/live tender source separate from historical APP records."""
    __tablename__ = "live_tender_sources"

    procurement_tender_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_tender_id: Mapped[str] = mapped_column(String(500), nullable=False, unique=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    procuring_entity: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    published_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    deadline: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    financial_year: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    estimated_value_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    source_file: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    raw_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)


class AwardRecordV2(Base, TimestampMixin, UUIDMixin):
    """eContracts award record (many:1 with ProcurementTender)."""
    __tablename__ = "award_records_v2"

    procurement_tender_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_tender_id: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    package_no: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contractor_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True, index=True)
    amount_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    procurement_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    award_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    detail_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    agency_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pe_office: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    __table_args__ = (
        Index("ix_arv2_tender", "procurement_tender_id"),
        Index("ix_arv2_contractor", "contractor_name"),
        Index("ix_arv2_date", "award_date"),
    )


class Contractor(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "contractors"

    contractor_name: Mapped[str] = mapped_column(String(300), unique=True, nullable=False, index=True)
    total_contracts: Mapped[int] = mapped_column(Integer, default=0)
    total_amount_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    agencies_worked: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=list)
    districts_worked: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=list)
    avg_npp: Mapped[float] = mapped_column(Float, default=0.0)
    first_award_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    last_award_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    def __repr__(self) -> str:
        return f"<Contractor {self.contractor_name}>"


class ContractorDNA(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "contractor_dna"

    contractor_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    total_contracts: Mapped[int] = mapped_column(Integer, default=0)
    total_amount_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    avg_award_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    agencies_worked: Mapped[int] = mapped_column(Integer, default=0)
    districts_worked: Mapped[int] = mapped_column(Integer, default=0)
    preferred_agency: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    preferred_zone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    avg_npp: Mapped[float] = mapped_column(Float, default=0.0)
    npp_volatility: Mapped[float] = mapped_column(Float, default=0.0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_discount_pct: Mapped[float] = mapped_column(Float, default=0.0)
    first_award_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    last_award_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    completion_rate: Mapped[float] = mapped_column(Float, default=0.0)
    on_time_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_delay_days: Mapped[float] = mapped_column(Float, default=0.0)
    total_experience_contracts: Mapped[int] = mapped_column(Integer, default=0)
    total_experience_value_bdt: Mapped[float] = mapped_column(Float, default=0.0)

    health_score: Mapped[float] = mapped_column(Float, default=0.0)


class ProcurementLifecycle(Base, TimestampMixin, UUIDMixin):
    """Unified view for ML/AI agents."""
    __tablename__ = "procurement_lifecycle"
    __table_args__ = (
        UniqueConstraint("package_no", "winner", "award_date", name="uq_lifecycle_pkg_winner_date"),
    )

    package_no: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    agency_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    zone_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estimated_cost_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    award_amount_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    npp_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    winner: Mapped[Optional[str]] = mapped_column(String(300), nullable=True, index=True)
    award_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    procurement_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pe_office: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    match_type: Mapped[str] = mapped_column(String(20), nullable=False, default="unmatched_app")
    data_source: Mapped[str] = mapped_column(String(10), nullable=False, default="app_only")
    tender_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)


class AgencyIntelligence(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "agency_intelligence"

    agency_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    total_contracts: Mapped[int] = mapped_column(Integer, default=0)
    total_amount_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    avg_npp: Mapped[float] = mapped_column(Float, default=0.0)
    npp_trend: Mapped[str] = mapped_column(String(20), default="stable")
    preferred_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class ZoneIntelligence(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "zone_intelligence"

    zone_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    total_contracts: Mapped[int] = mapped_column(Integer, default=0)
    total_amount_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    active_agencies: Mapped[int] = mapped_column(Integer, default=0)
    avg_npp: Mapped[float] = mapped_column(Float, default=0.0)


class DiscountPattern(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "discount_patterns"

    agency_code: Mapped[str] = mapped_column(String(20), nullable=False)
    zone_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    procurement_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    avg_npp: Mapped[float] = mapped_column(Float, default=0.0)
    min_npp: Mapped[float] = mapped_column(Float, default=0.0)
    max_npp: Mapped[float] = mapped_column(Float, default=0.0)
    median_npp: Mapped[float] = mapped_column(Float, default=0.0)
    stddev_npp: Mapped[float] = mapped_column(Float, default=0.0)
    total_amount_bdt: Mapped[float] = mapped_column(Float, default=0.0)


class AwardIntelligence(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "award_intelligence"

    agency_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    fiscal_year: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    quarter: Mapped[int] = mapped_column(Integer, default=1)
    total_contracts: Mapped[int] = mapped_column(Integer, default=0)
    total_amount_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    avg_npp: Mapped[float] = mapped_column(Float, default=0.0)
    avg_contract_amount: Mapped[float] = mapped_column(Float, default=0.0)


class EExperienceCompleted(Base, TimestampMixin, UUIDMixin):
    """eExperience completed works — eTenders tab (data_source=EEXPERIENCE_ALL)."""
    __tablename__ = "eexperience_completed"

    tender_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    package_no: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pe_office: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    agency_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    procurement_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    contractor_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True, index=True)
    company_unique_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    experience_certificate_no: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    contract_value_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    completed_value_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    contract_start_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    contract_end_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    planned_completion_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    actual_completion_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    published_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    award_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    completion_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    work_status: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)
    completed_on_time: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    procurement_tender_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    data_source: Mapped[str] = mapped_column(String(50), nullable=False, default="EEXPERIENCE_ALL")
    raw_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)


class ECMSongoing(Base, TimestampMixin, UUIDMixin):
    """eCMS ongoing packages — data_source=ECMS_ONGOING."""
    __tablename__ = "ecms_ongoing"

    tender_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    package_no: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pe_office: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    agency_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    procurement_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    contractor_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True, index=True)
    company_unique_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    experience_certificate_no: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    contract_value_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    completed_value_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    contract_start_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    contract_end_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    planned_completion_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    actual_completion_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    published_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    award_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    completion_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    work_status: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)
    completed_on_time: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    procurement_tender_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    data_source: Mapped[str] = mapped_column(String(50), nullable=False, default="ECMS_ONGOING")
    raw_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)


class EContractExecution(Base, TimestampMixin, UUIDMixin):
    """eExperience contract execution data — start/end dates, separate from eContracts."""
    __tablename__ = "econtract_execution"

    package_no: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    procurement_tender_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    data_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True, default="EEXPERIENCE")
    agency_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    agency_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    pe_office: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    contractor_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True, index=True)
    contract_value_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    completed_value_bdt: Mapped[float] = mapped_column(Float, default=0.0)
    contract_start_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    contract_end_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    planned_completion_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    actual_completion_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    award_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    completion_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    work_status: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)
    delay_days: Mapped[int] = mapped_column(Integer, default=0)
    extension_days: Mapped[int] = mapped_column(Integer, default=0)
    completed_on_time: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    performance_rating: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    completion_certificate_no: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    bill_no: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    fiscal_year: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    tender_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)


class PPREvaluation(Base, TimestampMixin, UUIDMixin):
    """Saves PPR 2025 evaluations to DB."""
    __tablename__ = "ppr_evaluations"

    evaluation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    tender_id: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    input_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class KnowledgeEntry(Base, TimestampMixin, UUIDMixin):
    """Stores Knowledge Lake entries for Agent 25."""
    __tablename__ = "knowledge_entries"

    entry_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    tender_id: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    stored_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)


class LearningOutcome(Base, TimestampMixin, UUIDMixin):
    """Stores bid outcome records for Agent 26."""
    __tablename__ = "learning_outcomes"

    tender_id: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    submitted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    won: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    our_bid_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    lert_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    our_discount_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    predicted_win_probability: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    actual_outcome: Mapped[str] = mapped_column(String(50), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class EPW3FormRecord(Base, TimestampMixin, UUIDMixin):
    """Stores generated EPW3 forms in PostgreSQL."""
    __tablename__ = "epw3_forms"

    tender_id: Mapped[str] = mapped_column(String(300), unique=True, nullable=False, index=True)
    generated_at: Mapped[str] = mapped_column(String(50), nullable=False)
    forms: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    total_forms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    form_ids: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)


class BWDBAlertRecord(Base, TimestampMixin, UUIDMixin):
    """Stores alert history for BWDB monitor."""
    __tablename__ = "bwdb_alerts"

    tender_id: Mapped[str] = mapped_column(String(300), unique=True, nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    entity: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    deadline: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sent_at: Mapped[str] = mapped_column(String(50), nullable=False)
    recipient: Mapped[str] = mapped_column(String(300), nullable=False)


