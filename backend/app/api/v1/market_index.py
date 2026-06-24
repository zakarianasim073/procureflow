"""Market Rate Index API — Real-time construction material/labor/equipment rates"""

from fastapi import APIRouter, Depends, Query
from typing import Optional

from app.core.security import get_optional_user
from app.services.market_index import market_index

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/rates")
async def get_market_rates(
    zone: str = Query("A", description="Zone: A (Dhaka), B (Chattogram), C (Rajshahi/Khulna), D (Rangpur/Barishal)"),
    category: Optional[str] = Query(None, description="Filter: materials, labor, equipment, transport"),
    user: dict = Depends(get_optional_user),
):
    """Get current market rates for construction inputs, zone-adjusted."""
    if category:
        data = market_index.get_by_category(category, zone)
        return {
            "success": True,
            "category": category,
            "zone": zone.upper(),
            "count": len(data),
            "data": data,
        }
    
    data = market_index.get_all_rates(zone)
    return {"success": True, "data": data}


@router.get("/trends")
async def get_market_trends(
    user: dict = Depends(get_optional_user),
):
    """Get items with significant price movements."""
    trends = market_index.get_trends()
    return {
        "success": True,
        "total": len(trends),
        "trends": trends,
    }


@router.get("/indices")
async def get_price_indices(
    user: dict = Depends(get_optional_user),
):
    """Get economic price indices (CPI, WPI) for construction."""
    data = market_index.get_all_rates()
    return {
        "success": True,
        "data": data.get("indices", {}),
    }
