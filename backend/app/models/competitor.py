"""Competitor Intelligence models"""

from sqlalchemy import String, ForeignKey, JSON, Float, Integer, DateTime, Index, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, Dict, Any
from datetime import datetime

from .base import Base, TimestampMixin, UUIDMixin


class CompetitorProfile(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "competitor_profiles"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    license_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    division: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    contact_person: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Classification
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Company, JV, etc.
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # A, B, C, etc.
    specializations: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    
    # Stats (computed from awards)
    total_awards: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_awarded_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_discount_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_project_size: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    first_award_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_award_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    active_districts: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    work_types: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    
    # ML predictions
    predicted_win_probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    predicted_price_range: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    
    # Indexes
    __table_args__ = (
        Index("ix_competitor_district_category", "district", "category"),
        Index("ix_competitor_active_amount", "last_award_date", "total_awarded_amount"),
    )

    def __repr__(self) -> str:
        return f"<CompetitorProfile {self.name}>"


class CompetitorAward(Base, TimestampMixin, UUIDMixin):
    """Link table for competitor-award relationships with additional analytics"""
    __tablename__ = "competitor_awards"

    competitor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("competitor_profiles.id"), nullable=False, index=True
    )
    award_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("award_records.id"), nullable=False, index=True
    )
    
    # Role in this award
    role: Mapped[str] = mapped_column(String(50), default="prime", nullable=False)  # prime, sub, jv_partner
    is_jv: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    jv_partners: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    
    # Financial
    bid_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    share_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Indexes
    __table_args__ = (
        Index("ix_competitor_award_unique", "competitor_id", "award_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<CompetitorAward competitor={self.competitor_id} award={self.award_id}>"
