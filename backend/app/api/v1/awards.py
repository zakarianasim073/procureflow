"""Award Intelligence API routes"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.db.base import get_async_session
from app.models.award import AwardRecord
from app.schemas.award import AwardRecordCreate, AwardRecordRead
from app.core.security import get_optional_user, get_current_user

router = APIRouter(prefix="/awards", tags=["awards"])


@router.post("/", response_model=AwardRecordRead)
async def create_award(
    award: AwardRecordCreate,
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_current_user),
):
    """Create a new award record"""
    db_award = AwardRecord(**award.model_dump())
    db.add(db_award)
    await db.commit()
    await db.refresh(db_award)
    return db_award


@router.get("/", response_model=List[AwardRecordRead])
async def list_awards(
    procuring_entity: Optional[str] = Query(None),
    contractor_name: Optional[str] = Query(None),
    district: Optional[str] = Query(None),
    work_type: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_optional_user),
):
    """List award records with filters"""
    stmt = select(AwardRecord)
    
    if procuring_entity:
        stmt = stmt.where(AwardRecord.procuring_entity.ilike(f"%{procuring_entity}%"))
    if contractor_name:
        stmt = stmt.where(AwardRecord.contractor_name.ilike(f"%{contractor_name}%"))
    if district:
        stmt = stmt.where(AwardRecord.district.ilike(f"%{district}%"))
    if work_type:
        stmt = stmt.where(AwardRecord.work_type.ilike(f"%{work_type}%"))
    if date_from:
        stmt = stmt.where(AwardRecord.award_date >= date_from)
    if date_to:
        stmt = stmt.where(AwardRecord.award_date <= date_to)
    
    stmt = stmt.order_by(desc(AwardRecord.award_date)).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/stats")
async def get_award_stats(
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_optional_user),
):
    """Get award statistics"""
    total = await db.scalar(select(func.count(AwardRecord.id)))
    total_amount = await db.scalar(select(func.sum(AwardRecord.awarded_amount)))
    avg_discount = await db.scalar(select(func.avg(AwardRecord.discount_pct)))
    
    # Top entities
    top_entities = await db.execute(
        select(AwardRecord.procuring_entity, func.count(AwardRecord.id), func.sum(AwardRecord.awarded_amount))
        .group_by(AwardRecord.procuring_entity)
        .order_by(func.sum(AwardRecord.awarded_amount).desc())
        .limit(10)
    )
    
    # Top contractors
    top_contractors = await db.execute(
        select(AwardRecord.contractor_name, func.count(AwardRecord.id), func.sum(AwardRecord.awarded_amount))
        .group_by(AwardRecord.contractor_name)
        .order_by(func.sum(AwardRecord.awarded_amount).desc())
        .limit(10)
    )
    
    return {
        "total_awards": total or 0,
        "total_awarded_amount": total_amount or 0,
        "avg_discount_pct": float(avg_discount) if avg_discount else 0,
        "top_entities": [
            {"name": r[0], "count": r[1], "total_amount": float(r[2])}
            for r in top_entities
        ],
        "top_contractors": [
            {"name": r[0], "count": r[1], "total_amount": float(r[2])}
            for r in top_contractors
        ],
    }


@router.get("/{award_id}", response_model=AwardRecordRead)
async def get_award(
    award_id: str,
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_optional_user),
):
    """Get award by ID"""
    stmt = select(AwardRecord).where(AwardRecord.id == award_id)
    result = await db.execute(stmt)
    award = result.scalar_one_or_none()
    if not award:
        raise HTTPException(status_code=404, detail="Award not found")
    return award
