"""Tender schemas"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class TenderBase(BaseModel):
    tender_id: str = Field(..., max_length=100)
    title: str = Field(..., max_length=500)
    procuring_entity: Optional[str] = None
    district: Optional[str] = None
    division: Optional[str] = None
    estimated_cost: Optional[float] = None
    tender_security: Optional[float] = None
    closing_date: Optional[datetime] = None
    opening_date: Optional[datetime] = None
    sor_agency: str = "BWDB"
    zone: Optional[str] = None


class TenderCreate(TenderBase):
    pass


class TenderUpdate(BaseModel):
    title: Optional[str] = None
    procuring_entity: Optional[str] = None
    district: Optional[str] = None
    division: Optional[str] = None
    estimated_cost: Optional[float] = None
    tender_security: Optional[float] = None
    closing_date: Optional[datetime] = None
    opening_date: Optional[datetime] = None
    status: Optional[str] = None
    sor_agency: Optional[str] = None
    zone: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None


class TenderRead(TenderBase):
    id: str
    owner_id: str
    status: str
    extracted_data: Dict[str, Any]
    comparison_results: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TenderDocumentRead(BaseModel):
    id: str
    tender_id: str
    doc_type: str
    filename: str
    file_path: str
    file_size: int
    mime_type: Optional[str]
    extracted_text: Optional[str]
    attributes: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True
