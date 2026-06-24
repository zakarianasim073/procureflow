"""Award schemas"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class AwardRecordBase(BaseModel):
    source: str = "egp"
    source_id: str
    tender_id: Optional[str] = None
    award_date: Optional[datetime] = None
    award_notice_no: Optional[str] = None
    procuring_entity: str
    entity_type: Optional[str] = None
    ministry: Optional[str] = None
    work_name: str
    work_type: Optional[str] = None
    district: Optional[str] = None
    division: Optional[str] = None
    estimated_cost: Optional[float] = None
    awarded_amount: float
    currency: str = "BDT"
    contractor_name: str
    contractor_license: Optional[str] = None
    contractor_address: Optional[str] = None
    contract_period_days: Optional[int] = None
    work_start_date: Optional[datetime] = None
    work_completion_date: Optional[datetime] = None
    raw_data: Dict[str, Any] = {}
    boq_items: Dict[str, Any] = {}


class AwardRecordCreate(AwardRecordBase):
    pass


class AwardRecordRead(AwardRecordBase):
    id: str
    discount_pct: Optional[float]
    unit_rates: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
