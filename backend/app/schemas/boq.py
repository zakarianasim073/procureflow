"""BOQ schemas"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class BOQItemBase(BaseModel):
    item_no: Optional[str] = None
    code: Optional[str] = None
    description: str
    unit: Optional[str] = None
    quantity: Optional[float] = None
    quoted_rate: Optional[float] = None
    sor_rate: Optional[float] = None
    sor_code: Optional[str] = None
    diff: Optional[float] = None
    pct_diff: Optional[float] = None
    flag: Optional[str] = None
    work_type: Optional[str] = None
    section: Optional[str] = None
    agency: Optional[str] = None


class BOQItemRead(BOQItemBase):
    id: str
    tender_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class BOQComparisonCreate(BaseModel):
    boq_file_id: str
    sor_agency: str = "BWDB"
    zone: Optional[str] = None
    tender_info: Optional[Dict[str, Any]] = None


class BOQComparisonRead(BaseModel):
    id: str
    user_id: str
    tender_id: Optional[str]
    boq_file_id: str
    sor_agency: str
    zone: Optional[str]
    total_items: int
    matches: int
    variances: int
    mismatches: int
    below_sor: int
    total_sor_amount: Optional[float]
    total_quoted_amount: Optional[float]
    discount_pct: Optional[float]
    summary_by_work_type: Dict[str, Any]
    excel_path: Optional[str]
    docx_path: Optional[str]
    tenderai_dir: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
