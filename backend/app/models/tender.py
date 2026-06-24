"""Tender models"""

from sqlalchemy import String, Text, ForeignKey, JSON, Enum as SQLEnum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List, Dict, Any
import enum
from datetime import datetime

from .base import Base, TimestampMixin, UUIDMixin


class TenderStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class DocumentType(str, enum.Enum):
    NOTICE = "notice"
    TDS = "tds"
    TDS_2 = "tds_2"
    BOQ = "boq"
    SOR = "sor"
    TEMPLATE_DOCX = "template_docx"
    TEMPLATE_XLSX = "template_xlsx"
    OTHER = "other"


class Tender(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "tenders"

    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    tender_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    procuring_entity: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    division: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    estimated_cost: Mapped[Optional[float]] = mapped_column(nullable=True)
    tender_security: Mapped[Optional[float]] = mapped_column(nullable=True)
    closing_date: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    opening_date: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    status: Mapped[TenderStatus] = mapped_column(
        SQLEnum(TenderStatus), default=TenderStatus.DRAFT, nullable=False
    )
    sor_agency: Mapped[str] = mapped_column(String(20), default="BWDB", nullable=False)
    zone: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    extracted_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    comparison_results: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="tenders")
    documents: Mapped[List["TenderDocument"]] = relationship(
        "TenderDocument", back_populates="tender", lazy="selectin", cascade="all, delete-orphan"
    )
    boq_items: Mapped[List["BOQItem"]] = relationship(
        "BOQItem", back_populates="tender", lazy="selectin", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("ix_tenders_owner_status", "owner_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Tender {self.tender_id}: {self.title[:50]}>"


class TenderDocument(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "tender_documents"

    tender_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenders.id"), nullable=False, index=True
    )
    doc_type: Mapped[DocumentType] = mapped_column(
        SQLEnum(DocumentType), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(default=0, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attributes: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    tender: Mapped["Tender"] = relationship("Tender", back_populates="documents")

    # Indexes
    __table_args__ = (
        Index("ix_tender_docs_tender_type", "tender_id", "doc_type"),
    )

    def __repr__(self) -> str:
        return f"<TenderDocument {self.doc_type}: {self.filename}>"
