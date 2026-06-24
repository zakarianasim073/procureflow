"""SOR Rate model — PostgreSQL-backed Schedule of Rates"""

from sqlalchemy import String, Float, Integer, Index, Enum as SQLEnum, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
import enum

from .base import Base, TimestampMixin, UUIDMixin


class SorAgency(str, enum.Enum):
    BWDB = "BWDB"
    PWD = "PWD"
    LGED = "LGED"
    RHD = "RHD"
    CUSTOM = "CUSTOM"


class SorRate(Base, TimestampMixin, UUIDMixin):
    """Single SOR rate entry with zone-based pricing."""
    __tablename__ = "sor_rates"

    agency: Mapped[SorAgency] = mapped_column(
        SQLEnum(SorAgency), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    normalized_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Zone-based rates
    zone_a: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    zone_b: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    zone_c: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    zone_d: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    
    # Metadata
    edition_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source_file: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    __table_args__ = (
        Index("ix_sor_agency_code", "agency", "code"),
        Index("ix_sor_normalized", "agency", "normalized_code"),
        Index("ix_sor_active", "agency", "is_active"),
    )

    def get_rate(self, zone: Optional[str] = "A") -> float:
        z = (zone or "A").upper()
        return {
            "A": self.zone_a, "B": self.zone_b,
            "C": self.zone_c, "D": self.zone_d,
        }.get(z, self.zone_a)

    def __repr__(self) -> str:
        return f"<SorRate {self.agency} {self.code}: ৳{self.zone_a}>"
