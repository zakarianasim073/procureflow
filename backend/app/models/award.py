"""Award Intelligence models"""

from sqlalchemy import String, ForeignKey, JSON, Float, Integer, DateTime, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, Dict, Any
from datetime import datetime

from .base import Base, TimestampMixin, UUIDMixin


class AwardRecord(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "award_records"

    # Source info
    source: Mapped[str] = mapped_column(String(50), default="egp", nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    tender_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # Award details
    award_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    award_notice_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Procuring entity
    procuring_entity: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ministry: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Work details
    work_name: Mapped[str] = mapped_column(String(500), nullable=False)
    work_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    division: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Financial
    estimated_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    awarded_amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="BDT", nullable=False)
    
    # Contractor
    contractor_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    contractor_license: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    contractor_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Timeline
    contract_period_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    work_start_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    work_completion_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Additional data
    raw_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    boq_items: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    
    # Analysis fields
    discount_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)
    unit_rates: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    
    # Indexes
    __table_args__ = (
        Index("ix_award_entity_date", "procuring_entity", "award_date"),
        Index("ix_award_contractor_date", "contractor_name", "award_date"),
        Index("ix_award_district_type", "district", "work_type"),
    )

    def __repr__(self) -> str:
        return f"<AwardRecord {self.award_notice_no}: {self.contractor_name}>"
