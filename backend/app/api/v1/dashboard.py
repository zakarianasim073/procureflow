"""Dashboard API routes"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from typing import Dict, Any
from pathlib import Path

from app.db.base import get_async_session
from app.models.user import User
from app.models.tender import Tender
from app.models.boq import BOQComparison, BOQItem
from app.models.award import AwardRecord
from app.models.competitor import CompetitorProfile
from app.core.security import get_current_user
from app.services.intelligence_data_service import IntelligenceDataService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_current_user),
):
    """Get dashboard statistics"""
    is_guest = False

    tender_count_stmt = select(func.count(Tender.id))
    comparison_count_stmt = select(func.count(BOQComparison.id))
    boq_count_stmt = select(func.count(BOQItem.id))
    recent_stmt = select(BOQComparison).order_by(desc(BOQComparison.created_at)).limit(5)
    status_stmt = select(Tender.status, func.count(Tender.id)).group_by(Tender.status)

    if not is_guest:
        tender_count_stmt = tender_count_stmt.where(Tender.owner_id == user["id"])
        comparison_count_stmt = comparison_count_stmt.where(BOQComparison.user_id == user["id"])
        boq_count_stmt = boq_count_stmt.join(Tender).where(Tender.owner_id == user["id"])
        recent_stmt = recent_stmt.where(BOQComparison.user_id == user["id"])
        status_stmt = status_stmt.where(Tender.owner_id == user["id"])

    total_tenders = await db.scalar(tender_count_stmt)
    total_comparisons = await db.scalar(comparison_count_stmt)
    total_boq_items = await db.scalar(boq_count_stmt)
    recent_comparisons = await db.execute(recent_stmt)
    status_breakdown = await db.execute(status_stmt)
    
    return {
        "success": True,
        "stats": {
            "total_tenders": total_tenders or 0,
            "total_comparisons": total_comparisons or 0,
            "total_boq_items": total_boq_items or 0,
            "recent_comparisons": [
                {
                    "id": c.id,
                    "boq_file_id": c.boq_file_id,
                    "total_items": c.total_items,
                    "matches": c.matches,
                    "variances": c.variances,
                    "mismatches": c.mismatches,
                    "created_at": c.created_at.isoformat(),
                }
                for c in recent_comparisons.scalars().all()
            ],
            "tender_status": dict(status_breakdown.all()),
        }
    }


@router.get("/analytics")
async def get_analytics(
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_current_user),
):
    """Get detailed analytics"""
    # Comparison stats by agency
    agency_stats = await db.execute(
        select(BOQComparison.sor_agency, func.count(BOQComparison.id), func.avg(BOQComparison.discount_pct))
        .where(BOQComparison.user_id == user["id"])
        .group_by(BOQComparison.sor_agency)
    )
    
    # Monthly comparison counts
    month_expr = func.to_char(BOQComparison.created_at, 'YYYY-MM')
    monthly = await db.execute(
        select(
            month_expr,
            func.count(BOQComparison.id)
        )
        .where(BOQComparison.user_id == user["id"])
        .group_by(month_expr)
        .order_by(month_expr)
    )
    
    # Flag distribution
    flag_stats = await db.execute(
        select(BOQItem.flag, func.count(BOQItem.id))
        .join(Tender, BOQItem.tender_id == Tender.id)
        .where(Tender.owner_id == user["id"])
        .group_by(BOQItem.flag)
    )
    
    return {
        "success": True,
        "analytics": {
            "by_agency": [
                {"agency": r[0], "count": r[1], "avg_discount": float(r[2]) if r[2] else 0}
                for r in agency_stats.all()
            ],
            "monthly": [
                {"month": r[0], "count": r[1]}
                for r in monthly.all()
            ],
            "flag_distribution": dict(flag_stats.all()),
        }
    }


@router.get("/data-intelligence")
async def get_data_intelligence(
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_current_user),
):
    """Get DB-backed intelligence statistics."""
    svc = IntelligenceDataService(db)
    lifecycle = await svc.get_lifecycle_stats()
    contractors = await svc.get_contractor_stats()
    data_quality = await svc.get_award_data_quality_stats()
    return {"success": True, **lifecycle, **contractors, "data_quality": data_quality}


@router.post("/data-intelligence/collect")
async def trigger_collection(payload: Dict[str, Any] = {}):
    """Trigger data collection (live tenders, awards)."""
    from app.services.data_intelligence import data_intelligence
    from app.db.base import get_session_factory

    mode = payload.get("mode", "live")
    if mode == "all_tabs":
        result = data_intelligence.collect_all_tender_tabs()
    elif mode == "awards":
        entity = payload.get("entity", "")
        days = payload.get("days", 90)
        result = data_intelligence.collect_noa_awards(entity=entity, days=days, max_pages=5)
    elif mode == "bulk":
        target = payload.get("target", 1000)
        result = data_intelligence.run_bulk_collection(target_count=target)
    else:
        keyword = payload.get("keyword", "")
        result = data_intelligence.collect_live_tenders(keyword=keyword, max_pages=5)

    sync_summary = {}
    sf = get_session_factory()
    async with sf() as session:
        svc = IntelligenceDataService(session)
        file_path = result.get("file")
        if file_path:
            fp = Path(file_path)
            lowered = fp.name.lower()
            if "award" in lowered:
                sync_summary["awards_imported"] = await svc.import_awards_from_json(fp)
            else:
                sync_summary["tenders_imported"] = await svc.import_live_tenders_from_json(fp)
        else:
            sync_summary = await svc.import_existing_json_data()
        await svc.rebuild_procurement_lifecycle()
        await svc.rebuild_contractor_intelligence()
        await svc.rebuild_aggregate_intelligence()
        regime_summary = await svc.backfill_tender_regimes()
        await session.commit()
    return {"success": True, "result": result, "sync": sync_summary, "regime_backfill": regime_summary}


@router.get("/bwdb-monitor")
async def get_bwdb_monitor(user: dict = Depends(get_current_user)):
    """Get BWDB monitor statistics and alert history."""
    from app.services.bwdb_monitor import bwdb_monitor
    stats = await bwdb_monitor.get_stats()
    history = await bwdb_monitor.get_alert_history(limit=20)
    return {"success": True, "stats": stats, "alerts": history}


@router.post("/bwdb-monitor/scan")
async def trigger_bwdb_scan(payload: Dict[str, Any] = {}):
    """Scan collected tenders for BWDB high-value alerts."""
    from app.services.data_intelligence import data_intelligence
    from app.services.bwdb_monitor import bwdb_monitor
    tenders = data_intelligence.get_tenders_by_agency("BWDB")
    alerts = await bwdb_monitor.scan_and_alert(tenders)
    return {"success": True, "alerts_sent": len(alerts), "alerts": alerts}
