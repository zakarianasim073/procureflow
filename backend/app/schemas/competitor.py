"""Competitor schemas"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class CompetitorProfileBase(BaseModel):
    name: str
    license_number: Optional[str] = None
    address: Optional[str] = None
    district: Optional[str] = None
    division: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    entity_type: Optional[str] = None
    category: Optional[str] = None
    specializations: Dict[str, Any] = {}


class CompetitorProfileCreate(CompetitorProfileBase):
    pass


class CompetitorProfileRead(CompetitorProfileBase):
    id: str
    normalized_name: str
    total_awards: int
    total_awarded_amount: float
    avg_discount_pct: Optional[float]
    avg_project_size: Optional[float]
    first_award_date: Optional[datetime]
    last_award_date: Optional[datetime]
    active_districts: Dict[str, Any]
    work_types: Dict[str, Any]
    predicted_win_probability: Optional[float]
    predicted_price_range: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
