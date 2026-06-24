"""BOQ models"""

from sqlalchemy import String, ForeignKey, JSON, Float, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List, Dict, Any

from .base import Base, TimestampMixin, UUIDMixin


class BOQItem(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "boq_items"

    tender_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenders.id"), nullable=False, index=True
    )
    item_no: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quoted_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sor_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sor_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    diff: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pct_diff: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    flag: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    work_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    section: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    agency: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    attributes: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    tender: Mapped["Tender"] = relationship("Tender", back_populates="boq_items")

    # Indexes
    __table_args__ = (
        Index("ix_boq_items_tender_flag", "tender_id", "flag"),
    )

    def __repr__(self) -> str:
        return f"<BOQItem {self.code}: {self.description[:50]}>"


class BOQComparison(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "boq_comparisons"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    tender_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("tenders.id"), nullable=True, index=True
    )
    boq_file_id: Mapped[str] = mapped_column(String(100), nullable=False)
    sor_agency: Mapped[str] = mapped_column(String(20), default="BWDB", nullable=False)
    zone: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    total_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    variances: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mismatches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    below_sor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_sor_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_quoted_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    discount_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    summary_by_work_type: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    excel_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    docx_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    tenderai_dir: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="boq_comparisons")
    tender: Mapped[Optional["Tender"]] = relationship("Tender")

    def __repr__(self) -> str:
        return f"<BOQComparison {self.boq_file_id}: {self.total_items} items>"
