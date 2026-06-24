"""PPR 2025 Evaluation Dashboard — PostgreSQL-backed."""

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.base import get_async_session
from app.core.security import get_current_user
from app.services.intelligence_data_service import IntelligenceDataService
from app.services.ppr_ml_service import get_ppr_ml_service
from app.models.intelligence import PPREvaluation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ppr2025", tags=["ppr2025"])

RUNTIME_DIR = Path(__file__).resolve().parent.parent.parent.parent / "runtime"


def get_svc(db: AsyncSession = Depends(get_async_session)) -> IntelligenceDataService:
    return IntelligenceDataService(db)


@router.get("/overview")
async def ppr2025_overview(
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    contractor_stats = await svc.get_contractor_stats()
    lifecycle_stats = await svc.get_lifecycle_stats()
    award_trends = await svc.get_award_trends()
    npp = await svc.get_npp_trends(months=24)
    ml_service = get_ppr_ml_service(svc.db)
    ml_status = await ml_service.status()
    ml_report = await ml_service.model_report()
    agencies = sorted({row.get("agency_code") for row in award_trends if row.get("agency_code")})
    if not agencies:
        agencies = sorted({row.get("agency_code") for row in npp if row.get("agency_code")})
    return {
        "success": True,
        "data": {
            "total_awards": lifecycle_stats["total_records"],
            "total_npp_records": sum(row.get("count", 0) for row in npp),
            "total_predictions": lifecycle_stats["matched_packages"],
            "total_contractors": contractor_stats["total_contractors"],
            "total_agencies": len(agencies),
            "avg_discount_pct": round(max(0.0, (1 - contractor_stats["avg_npp"]) * 100), 2) if contractor_stats["avg_npp"] else 0,
            "agencies": agencies,
            "model_status": ml_status,
            "model_report": ml_report,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.get("/npp-trends")
async def ppr_npp_trends(
    agency: str = "",
    months: int = Query(24, ge=1, le=120),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    trends = await svc.get_npp_trends(months=months * 10)
    if agency:
        trends = [row for row in trends if (row.get("agency_code") or "").upper() == agency.upper()]
    result = [
        {
            "month": row["month"],
            "agency": row["agency_code"],
            "avg_npp": round((row["avg_npp"] or 0) * 100, 2),
            "median_npp": round((row["avg_npp"] or 0) * 100, 2),
            "min_npp": round((row["avg_npp"] or 0) * 100, 2),
            "max_npp": round((row["avg_npp"] or 0) * 100, 2),
            "count": row["count"],
        }
        for row in trends
    ]
    result = result[-months:] if months and len(result) > months else result
    return {
        "success": True,
        "data": {
            "trends": result,
            "agencies": sorted({row["agency"] for row in result if row["agency"]}),
            "total_records": sum(row["count"] for row in result),
        },
    }


@router.get("/predictions")
async def ppr_predictions(
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    patterns = await svc.get_discount_patterns()
    predictions = [
        {
            "agency_code": row.get("agency_code"),
            "zone_name": row.get("zone_name"),
            "procurement_method": row.get("procurement_method"),
            "sample_size": row.get("sample_size", 0),
            "predicted_npp": row.get("avg_npp", 0),
            "confidence_score": min(1.0, (row.get("sample_size", 0) or 0) / 20),
        }
        for row in patterns
    ]
    return {"success": True, "data": {"predictions": predictions, "total": len(predictions)}}


@router.get("/contractors")
async def ppr_contractors(
    limit: int = Query(20, ge=1, le=100),
    min_wins: int = Query(1, ge=0),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    contractors = await svc.list_contractors(limit=1000, offset=0)
    ranked = [
        {
            "name": row.get("contractor_name", ""),
            "total_wins": row.get("total_contracts", 0),
            "total_amount": row.get("total_amount_bdt", 0),
            "avg_amount": round((row.get("total_amount_bdt", 0) or 0) / max(row.get("total_contracts", 1), 1), 2),
            "avg_discount": round(max(0.0, (1 - (row.get("avg_npp", 0) or 0)) * 100), 2) if row.get("avg_npp") else 0,
            "years_active": [],
            "top_agency": (row.get("agencies_worked") or [None])[0],
            "top_agency_wins": 0,
            "win_probability": {},
        }
        for row in contractors
        if (row.get("total_contracts", 0) or 0) >= min_wins
    ]
    ranked.sort(key=lambda item: item["total_wins"], reverse=True)
    return {"success": True, "data": {"contractors": ranked[:limit], "total": len(ranked)}}


@router.get("/contractor/{name}")
async def ppr_contractor_detail(
    name: str,
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    profile = await svc.get_contractor(name)
    if not profile:
        raise HTTPException(404, f"Contractor '{name}' not found")
    return {"success": True, "data": profile}


@router.get("/rates")
async def ppr_rates(user: dict = Depends(get_current_user)):
    return {"success": True, "data": {"agencies": {}}}


@router.get("/awards")
async def ppr_awards(
    agency: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    result = await svc.query_lifecycle(
        agency=agency or None,
        limit=min(page_size, 200),
        offset=(page - 1) * min(page_size, 200),
    )
    total_pages = max(1, (result["total"] + result["limit"] - 1) // result["limit"])
    return {
        "success": True,
        "data": {
            "awards": result["records"],
            "total": result["total"],
            "page": page,
            "page_size": result["limit"],
            "total_pages": total_pages,
            "has_next": page < total_pages,
        },
    }


@router.get("/award-stats")
async def ppr_award_stats(
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    lifecycle = await svc.query_lifecycle(limit=5000)
    by_agency_year = defaultdict(lambda: {"count": 0, "total_amount": 0.0, "npps": [], "contractors": set()})
    for row in lifecycle["records"]:
        agency = row.get("agency_code") or "Unknown"
        year = (row.get("award_date") or "0000")[:4]
        key = (agency, year)
        by_agency_year[key]["count"] += 1
        by_agency_year[key]["total_amount"] += row.get("award_amount_bdt", 0) or 0
        if row.get("npp_ratio"):
            by_agency_year[key]["npps"].append(row["npp_ratio"])
        if row.get("winner"):
            by_agency_year[key]["contractors"].add(row["winner"])
    stats = []
    for (agency, year), bucket in sorted(by_agency_year.items()):
        stats.append(
            {
                "agency": agency,
                "year": year,
                "count": bucket["count"],
                "total_amount": round(bucket["total_amount"], 2),
                "avg_discount": round(max(0.0, (1 - (sum(bucket["npps"]) / len(bucket["npps"]) if bucket["npps"] else 0)) * 100), 2)
                if bucket["npps"]
                else 0,
                "unique_contractors": len(bucket["contractors"]),
            }
        )
    summary = defaultdict(lambda: {"count": 0, "total_amount": 0.0})
    for row in stats:
        summary[row["agency"]]["count"] += row["count"]
        summary[row["agency"]]["total_amount"] += row["total_amount"]
    return {
        "success": True,
        "data": {
            "by_agency_year": stats,
            "summary": [{"agency": agency, **vals} for agency, vals in sorted(summary.items())],
        },
    }


@router.post("/evaluate/tec")
async def run_tec_evaluation(data: dict = Body(...), db: AsyncSession = Depends(get_async_session)):
    from app.agents.ppr2025_compliance import PPR2025ComplianceAgent

    agent = PPR2025ComplianceAgent()
    tender_id = data.get("tender_id", f"TEC-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}")
    result = await agent.execute(
        {
            "vendor_name": data.get("vendor_name", "Unknown Vendor"),
            "tender_id": tender_id,
            "tender_type": data.get("tender_type", "works"),
            "experience_years": data.get("experience_years", 8),
            "annual_turnover": data.get("annual_turnover", 50_000_000),
            "similar_contracts": data.get("similar_contracts", 3),
            "equipment_available": data.get("equipment_available", True),
            "qualified_personnel": data.get("qualified_personnel", 10),
        }
    )
    result_dict = result.to_dict()
    db_eval = PPREvaluation(
        id=str(uuid4()),
        evaluation_type="tec",
        tender_id=tender_id,
        input_data=data,
        result_data=result_dict,
    )
    db.add(db_eval)
    await db.commit()
    return {"success": True, "evaluation": result_dict}


@router.post("/evaluate/ppr")
async def run_ppr_evaluation(data: dict = Body(...), db: AsyncSession = Depends(get_async_session)):
    from app.agents.ppr_evaluation import PPREvaluationAgent

    agent = PPREvaluationAgent()
    tender_id = data.get("tender_id", f"PPR-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}")
    context = {
        "tender_id": tender_id,
        "bid_price": data.get("bid_price", 5_000_000),
        "estimated_cost": data.get("estimated_cost", 5_500_000),
        "bid_security": data.get("bid_security", 500_000),
        "validity_days": data.get("validity_days", 90),
        "boq_items": data.get(
            "boq_items",
            [
                {"item_no": "1", "code": "EXC01", "description": "Earthwork", "quantity": 1000, "rate": 500, "total": 500000},
                {"item_no": "2", "code": "CON01", "description": "Concrete", "quantity": 500, "rate": 8000, "total": 4000000},
            ],
        ),
        "experience_years": data.get("experience_years", 6),
    }
    result = await agent.execute(context)
    result_dict = result.to_dict()
    ml_service = get_ppr_ml_service(db)
    result_dict["ml_assessment"] = await ml_service.predict(
        {
            "estimated_cost": data.get("estimated_cost", 5_500_000),
            "bid_price": data.get("bid_price", 5_000_000),
            "bidder_count": data.get("bidder_count", data.get("responsive_bidders_count", 1)),
            "agency": data.get("agency", ""),
            "zone": data.get("zone", data.get("division", "")),
            "tender_open_date": data.get("tender_open_date"),
            "regime": data.get("regime"),
            "bidder_name": data.get("bidder_name", data.get("company_name", "")),
        }
    )
    db_eval = PPREvaluation(
        id=str(uuid4()),
        evaluation_type="ppr",
        tender_id=tender_id,
        input_data=data,
        result_data=result_dict,
    )
    db.add(db_eval)
    await db.commit()
    return {"success": True, "evaluation": result_dict}


@router.post("/evaluate/works")
async def run_works_evaluation(data: dict = Body(...), db: AsyncSession = Depends(get_async_session)):
    from app.services.ppr_engine import PPRWorksEngine

    engine = PPRWorksEngine()
    tender_id = data.get("tender_id", f"WORKS-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}")
    result = await engine.evaluate_works_tender(data)
    ml_service = get_ppr_ml_service(db)
    result["ml_assessment"] = await ml_service.predict(
        {
            "estimated_cost": data.get("official_estimate", data.get("estimated_cost", 0)),
            "bid_price": data.get("bid_price", data.get("quoted_bid_price", 0)),
            "bidder_count": len(data.get("responsive_bidders", []) or [1]),
            "agency": data.get("agency", ""),
            "zone": data.get("district", data.get("zone", "")),
            "tender_open_date": data.get("tender_open_date"),
            "regime": data.get("regime"),
            "contractor_name": data.get("contractor_name", data.get("bidder_name", data.get("bidder", ""))),
            "bidder_name": data.get("bidder_name", data.get("bidder", "")),
            "responsive_bidders": data.get("responsive_bidders", []),
        }
    )
    db_eval = PPREvaluation(
        id=str(uuid4()),
        evaluation_type="works",
        tender_id=tender_id,
        input_data=data,
        result_data=result,
    )
    db.add(db_eval)
    await db.commit()
    return {"success": True, "evaluation": result}


@router.post("/evaluate/slt")
async def run_slt_evaluation(data: dict = Body(...), db: AsyncSession = Depends(get_async_session)):
    from app.services.ppr_engine import PPRWorksEngine

    engine = PPRWorksEngine()
    estimated_cost = float(data.get("estimated_cost", data.get("official_estimate", 5_000_000))) or 0
    bid_price = float(data.get("bid_price", 4_500_000)) or 0
    boq_items = data.get("boq_items", []) or []
    tender_id = data.get("tender_id", f"SLT-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}")
    works_payload = {
        "tender_id": tender_id,
        "tender_open_date": data.get("tender_open_date", datetime.now(timezone.utc).date().isoformat()),
        "official_estimate": estimated_cost,
        "agency": data.get("agency", "BWDB"),
        "district": data.get("district", ""),
        "method": data.get("method", ""),
        "work_type": data.get("work_type", "Works"),
        "custom_npp_definition_id": data.get("custom_npp_definition_id", "custom_npp"),
        "boq_items": boq_items,
        "responsive_bidders": [
            {
                "bidder_name": data.get("bidder_name", data.get("bidder", "Current Bidder")),
                "quoted_amount": bid_price,
                "documents_complete": data.get("documents_complete", True),
                "signed": data.get("signed", True),
                "bid_validity_days": data.get("bid_validity_days", data.get("validity_days", 90)),
                "qualification_passed": data.get("qualification_passed", True),
                "bid_security_amount": data.get("bid_security_amount", data.get("bid_security", estimated_cost * 0.01 if estimated_cost else 0)),
                "boq_items": boq_items,
            }
        ],
    }
    if data.get("responsive_bidders"):
        works_payload["responsive_bidders"] = data["responsive_bidders"]
    result = await engine.evaluate_works_tender(works_payload)
    ml_service = get_ppr_ml_service(db)
    result["ml_assessment"] = await ml_service.predict(
        {
            "estimated_cost": estimated_cost,
            "bid_price": bid_price,
            "bidder_count": len(works_payload.get("responsive_bidders", []) or []),
            "agency": data.get("agency", "BWDB"),
            "zone": data.get("zone", data.get("district", "")),
            "tender_open_date": data.get("tender_open_date"),
            "regime": data.get("regime"),
            "contractor_name": data.get("contractor_name", data.get("bidder_name", data.get("bidder", ""))),
            "bidder_name": data.get("bidder_name", data.get("bidder", "")),
            "responsive_bidders": works_payload.get("responsive_bidders", []),
        }
    )
    db_eval = PPREvaluation(
        id=str(uuid4()),
        evaluation_type="slt",
        tender_id=tender_id,
        input_data=data,
        result_data=result,
    )
    db.add(db_eval)
    await db.commit()
    return {"success": True, "evaluation": result}


@router.get("/evaluations")
async def list_evaluations(
    limit: int = Query(20, ge=1, le=100),
    eval_type: str = "",
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_current_user),
):
    query = select(PPREvaluation)
    if eval_type:
        query = query.where(PPREvaluation.evaluation_type == eval_type)
    query = query.order_by(PPREvaluation.created_at.desc()).limit(limit)
    res = await db.execute(query)
    evals = res.scalars().all()

    formatted = []
    for ev in evals:
        formatted.append({
            "evaluation_type": ev.evaluation_type,
            "timestamp": ev.created_at.isoformat(),
            "input": ev.input_data,
            "result": ev.result_data,
        })

    count_query = select(func.count(PPREvaluation.id))
    if eval_type:
        count_query = count_query.where(PPREvaluation.evaluation_type == eval_type)
    count_res = await db.execute(count_query)
    total = count_res.scalar() or 0

    if total == 0:
        ml_service = get_ppr_ml_service(db)
        report = await ml_service.model_report()
        if report.get("trained"):
            return {
                "success": True,
                "evaluations": [
                    {
                        "evaluation_type": "model_validation",
                        "timestamp": report.get("trained_at"),
                        "input": report.get("dataset", {}),
                        "result": report.get("summary", {}),
                    }
                ],
                "total": 1,
            }

    return {"success": True, "evaluations": formatted, "total": total}


@router.get("/model/status")
async def ppr_model_status(
    db: AsyncSession = Depends(get_async_session),
    user: dict = Depends(get_current_user),
):
    ml_service = get_ppr_ml_service(db)
    return {"success": True, "data": await ml_service.status()}


@router.post("/model/train")
async def ppr_model_train(data: dict = Body(default={}), db: AsyncSession = Depends(get_async_session)):
    ml_service = get_ppr_ml_service(db)
    summary = await ml_service.train_models(force=bool(data.get("force", False)))
    return {"success": True, "data": summary}


@router.post("/model/explain")
async def ppr_model_explain(data: dict = Body(...), db: AsyncSession = Depends(get_async_session)):
    ml_service = get_ppr_ml_service(db)
    prediction = await ml_service.predict(data)
    return {
        "success": True,
        "data": {
            "prediction": prediction,
            "explanation": prediction.get("explanation", {}),
            "evidence": prediction.get("evidence", {}),
            "model_version": prediction.get("model_version"),
        },
    }


@router.get("/document-checklist")
async def get_document_checklist(
    tender_type: str = "works",
    user: dict = Depends(get_current_user),
):
    checklists = {
        "works": {
            "tender_type": "Works",
            "schedule": "Schedule 5 (Works)",
            "required_documents": [
                {"name": "Bid Security (EMD)", "rule": "Rule 27(1)", "amount": "1% of estimated cost", "mandatory": True},
                {"name": "Trade License", "rule": "Rule 28(2)", "validity": "Valid for current year", "mandatory": True},
                {"name": "VAT Registration Certificate", "rule": "Rule 28(2)", "validity": "Valid BIN number", "mandatory": True},
                {"name": "Income Tax Certificate", "rule": "Rule 28(2)", "validity": "Valid TIN, up-to-date", "mandatory": True},
                {"name": "Tender Schedules (Signed)", "rule": "Rule 27(2)", "validity": "All pages signed & stamped", "mandatory": True},
                {"name": "Similar Experience Certificate", "rule": "Rule 28(3)", "validity": "Min 1 similar contract", "mandatory": True},
                {"name": "Annual Turnover Certificate", "rule": "Rule 28(4)", "validity": "Audited accounts, 3 years", "mandatory": True},
            ],
            "evaluation_criteria": [
                {"name": "General Experience", "max_marks": 15, "min_pass": 7},
                {"name": "Specific Experience", "max_marks": 25, "min_pass": 12},
                {"name": "Equipment", "max_marks": 15, "min_pass": 7},
                {"name": "Personnel", "max_marks": 20, "min_pass": 10},
            ],
            "tec_pass_threshold": 70,
            "slt_threshold_pct": 70,
            "alt_threshold_pct": 60,
        }
    }
    return {"success": True, "data": checklists.get(tender_type, checklists["works"])}
