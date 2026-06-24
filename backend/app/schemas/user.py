"""User schemas"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    plan: Optional[str] = None
    is_active: Optional[bool] = None


class UserRead(UserBase):
    id: str
    plan: str
    is_active: bool
    is_superuser: bool
    gpt_quota_used: int
    gpt_quota_limit: int
    created_at: datetime

    class Config:
        from_attributes = True
