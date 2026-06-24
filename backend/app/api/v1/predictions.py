"""Prediction, NPP, and bid insight routes — PostgreSQL-backed."""

from collections import defaultdict

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_async_session
from app.services.intelligence_data_service import IntelligenceDataService

router = APIRouter(prefix="/predict", tags=["predict"])


def get_svc(db: AsyncSession = Depends(get_async_session)) -> IntelligenceDataService:
    return IntelligenceDataService(db)


@router.get("/npp/stats")
async def get_npp_stats(svc: IntelligenceDataService = Depends(get_svc)):
    trends = await svc.get_npp_trends(months=120)
    by_agency = defaultdict(lambda: {"total_records": 0, "weighted_npp": 0.0})
    for row in trends:
        agency = row.get("agency_code") or "Unknown"
        by_agency[agency]["total_records"] += row.get("count", 0)
        by_agency[agency]["weighted_npp"] += (row.get("avg_npp", 0) or 0) * (row.get("count", 0) or 0)
    payload = {}
    for agency, bucket in by_agency.items():
        total = bucket["total_records"]
        payload[agency] = {
            "total_records": total,
            "avg_npp": round(bucket["weighted_npp"] / total, 4) if total else 0,
        }
    return {"success": True, "by_agency": payload, "total_records": sum(v["total_records"] for v in payload.values())}


@router.get("/bid/stats")
async def get_bid_stats(svc: IntelligenceDataService = Depends(get_svc)):
    stats = await svc.get_contractor_stats()
    return {
        "success": True,
        "total_predictions": stats["total_contractors"],
        "contractors_with_data": stats["total_contractors"],
    }


@router.get("/bid/cross-check/auto")
async def auto_cross_check(
    svc: IntelligenceDataService = Depends(get_svc),
    limit: int = Query(100, ge=1, le=500),
):
    contractors = await svc.list_contractors(limit=limit, offset=0)
    lifecycle = await svc.query_lifecycle(limit=5000)
    wins_by_contractor = defaultdict(int)
    for row in lifecycle["records"]:
        if row.get("winner"):
            wins_by_contractor[row["winner"]] += 1
    details = []
    correct = 0
    for row in contractors:
        name = row.get("contractor_name", "")
        predicted_winner = (row.get("total_contracts", 0) or 0) > 0
        actual_wins = wins_by_contractor.get(name, 0)
        winner_correct = predicted_winner == (actual_wins > 0)
        if winner_correct:
            correct += 1
        details.append(
            {
                "contractor": name,
                "predicted_winner": predicted_winner,
                "actual_wins": actual_wins,
                "winner_correct": winner_correct,
            }
        )
    total_checked = len(details)
    return {
        "success": True,
        "total_checked": total_checked,
        "winner_accuracy_pct": round(correct / max(total_checked, 1) * 100, 1),
        "correct_winners": correct,
        "total_predictions": total_checked,
        "details": details[:20],
    }


@router.post("/bid/predict")
async def predict_bid(
    tender_id: str = Body(...),
    agency: str = Body("BWDB"),
    estimate: float = Body(..., gt=0),
    work_type: str = Body(""),
    interested_contractors: list[str] | None = Body(None),
    svc: IntelligenceDataService = Depends(get_svc),
):
    contractors = await svc.list_contractors(limit=1000, offset=0)
    agency_trends = [row for row in await svc.get_npp_trends(months=120) if (row.get("agency_code") or "").upper() == agency.upper()]
    agency_avg_npp = sum(row.get("avg_npp", 0) for row in agency_trends) / len(agency_trends) if agency_trends else 0

    candidates = []
    for row in contractors:
        name = row.get("contractor_name", "")
        if interested_contractors and name not in interested_contractors:
            continue
        agencies = row.get("agencies_worked") or []
        relevance = 1.0 if agency in agencies else 0.4
        wins = row.get("total_contracts", 0) or 0
        total_amount = row.get("total_amount_bdt", 0) or 0
        avg_discount_pct = max(0.0, (1 - (row.get("avg_npp", 0) or agency_avg_npp or 0)) * 100)
        score = (wins * 10 + total_amount / 1_000_000) * relevance
        candidates.append(
            {
                "contractor_name": name,
                "score": round(score, 2),
                "total_wins": wins,
                "total_amount_bdt": total_amount,
                "avg_discount_percent": round(avg_discount_pct, 2),
                "relevance": relevance,
            }
        )
    candidates.sort(key=lambda item: item["score"], reverse=True)
    winner = candidates[0] if candidates else None
    predicted_discount = (winner["avg_discount_percent"] / 100) if winner else agency_avg_npp
    return {
        "success": True,
        "tender_id": tender_id,
        "agency": agency,
        "estimate": estimate,
        "prediction": {
            "winner": winner["contractor_name"] if winner else None,
            "winning_discount": round(predicted_discount, 4),
            "predicted_amount": round(estimate * (1 - predicted_discount), 2),
            "confidence": "high" if len(candidates) > 1 and candidates[0]["score"] > candidates[1]["score"] * 1.5 else "medium",
            "top_candidates": candidates[:5],
        },
    }
