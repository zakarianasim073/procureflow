"""Intelligence API routes — PostgreSQL-backed, replaces all JSON reads."""
from fastapi import APIRouter, Depends, Query, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from pathlib import Path

from app.db.base import get_async_session
from app.core.security import get_current_user
from app.services.intelligence_data_service import ImportProgress, IntelligenceDataService, RUNTIME_DIR

router = APIRouter(prefix="/intel", tags=["intelligence"])


def get_svc(db: AsyncSession = Depends(get_async_session)) -> IntelligenceDataService:
    return IntelligenceDataService(db)


@router.get("/contractors")
async def list_contractors(
    query: Optional[str] = Query(None),
    limit: int = Query(100, le=5000),
    offset: int = Query(0),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    if query:
        records = await svc.search_contractors(query, limit)
    else:
        records = await svc.list_contractors(limit, offset)
    return {"success": True, "data": records, "total": len(records)}


@router.get("/contractors/stats")
async def contractor_stats(
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    stats = await svc.get_contractor_stats()
    return {"success": True, **stats}


@router.get("/contractors/{identifier}")
async def get_contractor(
    identifier: str,
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    record = await svc.get_contractor(identifier)
    if record:
        dna = await svc.get_contractor_dna(record.get("id", ""))
        return {"success": True, "contractor": record, "dna": dna}
    return {"success": False, "error": "Not found"}


@router.get("/contractors/{identifier}/benchmark")
async def benchmark_contractor(
    identifier: str,
    agency: Optional[str] = Query(None),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    record = await svc.get_contractor(identifier)
    if not record:
        return {"success": False, "error": "Contractor not found"}
    benchmark = await svc.benchmark_contractor(record.get("id", ""), agency=agency)
    return {"success": True, **benchmark} if benchmark else {"success": False, "error": "No DNA data"}


@router.get("/lifecycle")
async def query_lifecycle(
    agency: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    contractor: Optional[str] = Query(None),
    min_amount: float = Query(0),
    max_amount: float = Query(0),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    method: Optional[str] = Query(None),
    match: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(100, le=5000),
    offset: int = Query(0),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    result = await svc.query_lifecycle(
        agency=agency, zone=zone, contractor=contractor,
        min_amount=min_amount, max_amount=max_amount,
        date_from=date_from, date_to=date_to,
        method=method, match_type=match, data_source=source,
        limit=limit, offset=offset,
    )
    return {"success": True, **result}


@router.get("/lifecycle/stats")
async def lifecycle_stats(
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    stats = await svc.get_lifecycle_stats()
    return {"success": True, **stats}


@router.get("/agency-intel")
async def agency_intel(
    agency: Optional[str] = Query(None),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    data = await svc.get_agency_intelligence(agency)
    return {"success": True, "data": data}


@router.get("/npp-trends")
async def npp_trends(
    months: int = Query(12),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    data = await svc.get_npp_trends(months)
    return {"success": True, "data": data}


@router.get("/zone-intel")
async def zone_intel(
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    data = await svc.get_zone_intelligence()
    return {"success": True, "data": data}


@router.get("/discount-patterns")
async def discount_patterns(
    agency: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    data = await svc.get_discount_patterns(agency, zone)
    return {"success": True, "data": data}


@router.get("/award-trends")
async def award_trends(
    agency: Optional[str] = Query(None),
    year: Optional[str] = Query(None),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    data = await svc.get_award_trends(agency, year)
    return {"success": True, "data": data}


@router.get("/agent-feed")
async def agent_feed(
    agency: Optional[str] = Query(None),
    limit: int = Query(25, le=100),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    data = await svc.get_agent_feed(agency=agency, limit=limit)
    return {"success": True, "data": data}


@router.get("/live-tenders/stats")
async def live_tender_stats(
    agency: Optional[str] = Query(None),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    data = await svc.get_live_tender_stats(agency=agency)
    return {"success": True, **data}


@router.get("/import/status")
async def import_status(
    request: Request,
    user: dict = Depends(get_current_user),
):
    raw = getattr(request.app.state, "intelligence_import_status", None)
    if raw is None:
        status = {"state": "unknown", "started": False}
    elif hasattr(raw, "to_dict"):
        status = raw.to_dict()
    else:
        status = raw
    return {"success": True, "status": status}


@router.post("/import/contractors")
async def import_contractors(svc: IntelligenceDataService = Depends(get_svc)):
    count = await svc.import_contractors_from_json()
    await svc.db.commit()
    return {"success": True, "imported": count}


@router.post("/import/lifecycle")
async def import_lifecycle(svc: IntelligenceDataService = Depends(get_svc)):
    count = await svc.import_lifecycle_from_json()
    await svc.db.commit()
    return {"success": True, "imported": count}


@router.post("/import/all")
async def import_all_json_data(
    request: Request,
    svc: IntelligenceDataService = Depends(get_svc),
):
    raw = getattr(request.app.state, "intelligence_import_status", None)
    current_state = raw.state if hasattr(raw, "state") else (raw or {}).get("state")
    if current_state == "running":
        raise HTTPException(status_code=409, detail="Background JSON import already running")

    progress = ImportProgress()
    request.app.state.intelligence_import_status = progress
    summary = await svc.import_existing_json_data(progress=progress)
    return {"success": True, "summary": summary}


@router.post("/rebuild")
async def rebuild_intelligence(svc: IntelligenceDataService = Depends(get_svc)):
    lifecycle = await svc.rebuild_procurement_lifecycle()
    contractors = await svc.rebuild_contractor_intelligence()
    aggregates = await svc.rebuild_aggregate_intelligence()
    await svc.db.commit()
    return {
        "success": True,
        "lifecycle": lifecycle,
        "contractors": contractors,
        "aggregates": aggregates,
    }


# ── eExperience / eCMS (EContractExecution) ──────────────────────────

@router.get("/eexperience")
async def query_eexperience(
    agency: Optional[str] = Query(None),
    contractor: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None, description="EEXPERIENCE_ALL | ECMS_ONGOING"),
    work_status: Optional[str] = Query(None),
    min_value: Optional[float] = Query(None),
    max_value: Optional[float] = Query(None),
    limit: int = Query(100, le=5000),
    offset: int = Query(0),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    result = await svc.query_eexperience(
        agency=agency, contractor=contractor,
        date_from=date_from, date_to=date_to,
        status=status, source=source,
        work_status=work_status, min_value=min_value, max_value=max_value,
        limit=limit, offset=offset,
    )
    return {"success": True, **result}


@router.get("/eexperience/completed", summary="Filtered completed works (EEXPERIENCE_ALL)")
async def eexperience_completed(
    agency: Optional[str] = Query(None),
    contractor: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    min_value: Optional[float] = Query(None),
    max_value: Optional[float] = Query(None),
    limit: int = Query(100, le=5000),
    offset: int = Query(0),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    result = await svc.query_eexperience(
        agency=agency, contractor=contractor,
        date_from=date_from, date_to=date_to,
        source="EEXPERIENCE_ALL",
        min_value=min_value, max_value=max_value,
        limit=limit, offset=offset,
    )
    return {"success": True, **result}


@router.get("/eexperience/ongoing", summary="Filtered ongoing packages (ECMS_ONGOING)")
async def eexperience_ongoing(
    agency: Optional[str] = Query(None),
    contractor: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    min_value: Optional[float] = Query(None),
    max_value: Optional[float] = Query(None),
    limit: int = Query(100, le=5000),
    offset: int = Query(0),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    result = await svc.query_eexperience(
        agency=agency, contractor=contractor,
        date_from=date_from, date_to=date_to,
        source="ECMS_ONGOING",
        min_value=min_value, max_value=max_value,
        limit=limit, offset=offset,
    )
    return {"success": True, **result}


@router.get("/eexperience/stats")
async def eexperience_stats(
    source: Optional[str] = Query(None, description="EEXPERIENCE_ALL | ECMS_ONGOING"),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    stats = await svc.get_eexperience_stats(source=source)
    return {"success": True, **stats}


@router.get("/eexperience/completed/stats", summary="Completed works aggregated stats")
async def eexperience_completed_stats(
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    stats = await svc.get_eexperience_stats(source="EEXPERIENCE_ALL")
    return {"success": True, **stats}


@router.get("/eexperience/ongoing/stats", summary="Ongoing packages aggregated stats")
async def eexperience_ongoing_stats(
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    stats = await svc.get_eexperience_stats(source="ECMS_ONGOING")
    return {"success": True, **stats}


@router.get("/eexperience/intelligence")
async def eexperience_intelligence(
    agency: Optional[str] = Query(None),
    source: Optional[str] = Query(None, description="EEXPERIENCE_ALL | ECMS_ONGOING"),
    limit: int = Query(8, le=100),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    data = await svc.get_execution_intelligence(agency=agency, source=source, limit=limit)
    return {"success": True, "data": data}


@router.get("/eexperience/agencies")
async def eexperience_agencies(
    source: Optional[str] = Query(None, description="EEXPERIENCE_ALL | ECMS_ONGOING"),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    data = await svc.list_eexperience_agencies(source=source)
    return {"success": True, "data": data}


@router.get("/eexperience/contractor/{name}", summary="Contractor performance intelligence")
async def eexperience_contractor(
    name: str,
    source: Optional[str] = Query(None, description="EEXPERIENCE_ALL | ECMS_ONGOING"),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    data = await svc.get_contractor_performance(contractor_name=name, source=source)
    return {"success": True, "data": data}


@router.get("/eexperience/timeline", summary="Monthly/yearly execution timeline")
async def eexperience_timeline(
    source: Optional[str] = Query(None, description="EEXPERIENCE_ALL | ECMS_ONGOING"),
    granularity: str = Query("month", pattern="^(month|year)$"),
    year: Optional[int] = Query(None),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    data = await svc.get_eexperience_timeline(source=source, granularity=granularity, year=year)
    return {"success": True, "data": data}


@router.get("/eexperience/agency-comparison", summary="Agency performance comparison")
async def eexperience_agency_comparison(
    source: Optional[str] = Query(None, description="EEXPERIENCE_ALL | ECMS_ONGOING"),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    data = await svc.get_agency_comparison(source=source)
    return {"success": True, "data": data}


@router.post("/import/eexperience")
async def import_eexperience(
    path: Optional[str] = Query(None),
    svc: IntelligenceDataService = Depends(get_svc),
):
    fp = Path(path) if path else (RUNTIME_DIR / "knowledge" / "eexperience" / "all_experience.json")
    if not fp.exists():
        raise HTTPException(status_code=404, detail=f"eExperience JSON not found at {fp}")
    count = await svc.import_eexperience_from_json(fp)
    await svc.db.commit()
    return {"success": True, "imported": count, "path": str(fp)}


@router.post("/import/all-experience", summary="Import from eexperience_all (completed + ongoing)")
async def import_all_experience(
    svc: IntelligenceDataService = Depends(get_svc),
):
    base = RUNTIME_DIR / "knowledge" / "eexperience_all"
    results = {}
    for subdir, source in [("completed", "EEXPERIENCE_ALL"), ("ongoing", "ECMS_ONGOING")]:
        fp = base / subdir / "all_completed.json" if subdir == "completed" else base / subdir / "all_ongoing.json"
        if fp.exists():
            count = await svc.import_eexperience_from_json(fp)
            results[source] = count
        else:
            results[source] = 0
    await svc.db.commit()
    return {"success": True, "imported": results, "base_dir": str(base)}


# ── Crawl trigger stubs (CLI tools called separately) ─────────────────

@router.get("/eexperience/rate-quoted", summary="Rate Quoted analysis — award vs completed value")
async def eexperience_rate_quoted(
    agency: Optional[str] = Query(None),
    contractor: Optional[str] = Query(None),
    source: Optional[str] = Query(None, description="EEXPERIENCE_ALL | ECMS_ONGOING"),
    limit: int = Query(100, le=5000),
    offset: int = Query(0),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    data = await svc.get_rate_quoted_analysis(
        agency=agency, contractor=contractor, source=source, limit=limit, offset=offset,
    )
    return {"success": True, "data": data}


@router.get("/eexperience/reconcile-lifecycle", summary="Match eExperience records to lifecycle by package_no")
async def eexperience_reconcile_lifecycle(
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    data = await svc.reconcile_execution_to_lifecycle()
    return {"success": True, "data": data}


# ── Dedicated tables: eexperience_completed & ecms_ongoing ──────────

@router.post("/import/experience-dedicated", summary="Import eExperience bulk data into dedicated tables")
async def import_experience_dedicated(svc: IntelligenceDataService = Depends(get_svc)):
    results = await svc.import_experience_to_dedicated_tables()
    await svc.db.commit()
    return {"success": True, "data": results}


@router.post("/import/per-agency-experience", summary="Import per-agency experience.json (with agency_code) into dedicated tables")
async def import_per_agency_experience(svc: IntelligenceDataService = Depends(get_svc)):
    results = await svc.import_per_agency_experience()
    await svc.db.commit()
    return {"success": True, "data": results}


@router.get("/completed", summary="Query completed executions (eexperience_completed table)")
async def query_completed(
    agency: Optional[str] = Query(None),
    contractor: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(100, le=5000),
    offset: int = Query(0),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    data = await svc.query_completed_executions(
        agency=agency, contractor=contractor,
        date_from=date_from, date_to=date_to,
        limit=limit, offset=offset,
    )
    return {"success": True, **data}


@router.get("/ongoing", summary="Query ongoing packages (ecms_ongoing table)")
async def query_ongoing(
    agency: Optional[str] = Query(None),
    contractor: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(100, le=5000),
    offset: int = Query(0),
    svc: IntelligenceDataService = Depends(get_svc),
    user: dict = Depends(get_current_user),
):
    data = await svc.query_ongoing_executions(
        agency=agency, contractor=contractor,
        date_from=date_from, date_to=date_to,
        limit=limit, offset=offset,
    )
    return {"success": True, **data}


@router.get("/crawl/status")
async def crawl_status(user: dict = Depends(get_current_user)):
    """Check what crawl directories and data exist in runtime/knowledge."""
    econtracts_dir = RUNTIME_DIR / "knowledge" / "econtracts"
    eexperience_dir = RUNTIME_DIR / "knowledge" / "eexperience"
    eexperience_all_dir = RUNTIME_DIR / "knowledge" / "eexperience_all"
    agencies = sorted(d.name for d in econtracts_dir.iterdir() if d.is_dir() and d.name.isupper()) if econtracts_dir.exists() else []
    experience_dirs = sorted(d.name for d in eexperience_dir.iterdir() if d.is_dir()) if eexperience_dir.exists() else []
    all_completed = None
    all_ongoing = None
    if eexperience_all_dir.exists():
        completed_fp = eexperience_all_dir / "completed" / "all_completed.json"
        ongoing_fp = eexperience_all_dir / "ongoing" / "all_ongoing.json"
        if completed_fp.exists():
            import json
            all_completed = len(json.loads(completed_fp.read_text(encoding="utf-8")))
        if ongoing_fp.exists():
            import json
            all_ongoing = len(json.loads(ongoing_fp.read_text(encoding="utf-8")))
    return {
        "success": True,
        "econtracts_agencies": agencies,
        "eexperience_agencies": experience_dirs,
        "eexperience_all_completed_records": all_completed,
        "eexperience_all_ongoing_records": all_ongoing,
        "econtracts_dir": str(econtracts_dir),
        "eexperience_dir": str(eexperience_dir),
        "eexperience_all_dir": str(eexperience_all_dir) if eexperience_all_dir.exists() else None,
    }
