"""Competitor Intelligence API routes"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from typing import Optional, List, Dict, Any

from app.db.base import get_async_session
from app.models.competitor import CompetitorProfile, CompetitorAward
from app.schemas.competitor import CompetitorProfileCreate, CompetitorProfileRead
from app.core.security import get_optional_user, get_current_user

router = APIRouter(prefix="/competitors", tags=["competitors"])


@router.post("/", response_model=CompetitorProfileRead)
async def create_competitor(
    competitor: CompetitorProfileCreate,
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_current_user),
):
    """Create a new competitor profile"""
    # Normalize name for searching
    normalized = competitor.name.lower().strip()
    db_competitor = CompetitorProfile(
        **competitor.model_dump(),
        normalized_name=normalized,
    )
    db.add(db_competitor)
    await db.commit()
    await db.refresh(db_competitor)
    return db_competitor


@router.get("/", response_model=List[CompetitorProfileRead])
async def list_competitors(
    district: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_optional_user),
):
    """List competitor profiles with filters"""
    stmt = select(CompetitorProfile)
    
    if district:
        stmt = stmt.where(CompetitorProfile.district.ilike(f"%{district}%"))
    if category:
        stmt = stmt.where(CompetitorProfile.category == category)
    if search:
        stmt = stmt.where(CompetitorProfile.normalized_name.ilike(f"%{search.lower()}%"))
    
    stmt = stmt.order_by(desc(CompetitorProfile.total_awarded_amount)).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/stats")
async def get_competitor_stats(
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_optional_user),
):
    """Get competitor statistics"""
    total = await db.scalar(select(func.count(CompetitorProfile.id)))
    total_amount = await db.scalar(select(func.sum(CompetitorProfile.total_awarded_amount)))
    
    # By category
    by_category = await db.execute(
        select(CompetitorProfile.category, func.count(CompetitorProfile.id), func.sum(CompetitorProfile.total_awarded_amount))
        .group_by(CompetitorProfile.category)
        .order_by(func.sum(CompetitorProfile.total_awarded_amount).desc())
    )
    
    # By district
    by_district = await db.execute(
        select(CompetitorProfile.district, func.count(CompetitorProfile.id), func.sum(CompetitorProfile.total_awarded_amount))
        .group_by(CompetitorProfile.district)
        .order_by(func.sum(CompetitorProfile.total_awarded_amount).desc())
        .limit(10)
    )
    
    return {
        "total_competitors": total or 0,
        "total_awarded_amount": float(total_amount) if total_amount else 0,
        "by_category": [
            {"category": r[0], "count": r[1], "total_amount": float(r[2])}
            for r in by_category if r[0]
        ],
        "by_district": [
            {"district": r[0], "count": r[1], "total_amount": float(r[2])}
            for r in by_district if r[0]
        ],
    }


@router.get("/{competitor_id}", response_model=CompetitorProfileRead)
async def get_competitor(
    competitor_id: str,
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_optional_user),
):
    """Get competitor by ID"""
    stmt = select(CompetitorProfile).where(CompetitorProfile.id == competitor_id)
    result = await db.execute(stmt)
    competitor = result.scalar_one_or_none()
    if not competitor:
        raise HTTPException(status_code=404, detail="Competitor not found")
    return competitor


@router.get("/{competitor_id}/awards")
async def get_competitor_awards(
    competitor_id: str,
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_optional_user),
):
    """Get awards for a specific competitor"""
    from app.models.award import AwardRecord
    
    stmt = select(AwardRecord).join(
        CompetitorAward, CompetitorAward.award_id == AwardRecord.id
    ).where(CompetitorAward.competitor_id == competitor_id)
    result = await db.execute(stmt)
    return result.scalars().all()
