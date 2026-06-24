"""User model"""

from sqlalchemy import String, Boolean, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
import enum

from .base import Base, TimestampMixin, UUIDMixin


class UserPlan(str, enum.Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class User(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    plan: Mapped[UserPlan] = mapped_column(
        SQLEnum(UserPlan), default=UserPlan.FREE, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    gpt_quota_used: Mapped[int] = mapped_column(default=0, nullable=False)
    gpt_quota_limit: Mapped[int] = mapped_column(default=50000, nullable=False)

    # Relationships
    tenders: Mapped[List["Tender"]] = relationship("Tender", back_populates="owner", lazy="selectin")
    boq_comparisons: Mapped[List["BOQComparison"]] = relationship("BOQComparison", back_populates="user", lazy="selectin")

    def __repr__(self) -> str:
        return f"<User {self.email}>"
