"""Department tree + live tender search — PostgreSQL-backed."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_async_session
from app.services.intelligence_data_service import IntelligenceDataService

router = APIRouter(prefix="/deptree", tags=["deptree"])


def get_svc(db: AsyncSession = Depends(get_async_session)) -> IntelligenceDataService:
    return IntelligenceDataService(db)


@router.get("/targets")
async def get_target_agencies(svc: IntelligenceDataService = Depends(get_svc)):
    tree = await svc.get_department_tree()
    return {
        item["id"]: {
            "id": item["id"],
            "name": item["name"],
            "office_count": item["office_count"],
            "total_packages": item["total_packages"],
        }
        for item in tree
    }


@router.get("/tree")
async def get_full_tree(svc: IntelligenceDataService = Depends(get_svc)):
    tree = await svc.get_department_tree()
    return {
        "tree": tree,
        "total": len(tree),
        "targets": {m["id"]: {"name": m["name"], "office_count": m["office_count"]} for m in tree},
        "total_packages": sum(m["total_packages"] for m in tree),
    }


@router.get("/ministries")
async def get_ministries(svc: IntelligenceDataService = Depends(get_svc)):
    tree = await svc.get_department_tree()
    return [
        {
            "id": m["id"],
            "name": m["name"],
            "type": "Ministry",
            "office_count": m["office_count"],
            "total_packages": m["total_packages"],
        }
        for m in tree
    ]


@router.get("/ministry/{ministry_id}")
async def get_ministry_detail(ministry_id: str, svc: IntelligenceDataService = Depends(get_svc)):
    tree = await svc.get_department_tree()
    for ministry in tree:
        if ministry["id"].upper() == ministry_id.upper():
            return ministry
    raise HTTPException(404, f"Ministry '{ministry_id}' not found")


@router.get("/offices/{ministry_id}")
async def get_offices(ministry_id: str, svc: IntelligenceDataService = Depends(get_svc)):
    tree = await svc.get_department_tree()
    for ministry in tree:
        if ministry["id"].upper() == ministry_id.upper():
            return ministry["offices"]
    raise HTTPException(404, f"Ministry '{ministry_id}' not found")


@router.get("/search")
async def search_deptree(
    query: str = Query("", min_length=1),
    svc: IntelligenceDataService = Depends(get_svc),
):
    tree = await svc.get_department_tree()
    q = query.lower()
    results = []
    for ministry in tree:
        if q in ministry["name"].lower():
            results.append({"id": ministry["id"], "name": ministry["name"], "type": "Ministry", "match_field": "name"})
        for office in ministry["offices"]:
            if q in office["name"].lower() or q in office["id"].lower():
                results.append(
                    {
                        "id": office["id"],
                        "name": office["name"],
                        "type": "PE Office",
                        "ministry": ministry["name"],
                        "package_count": office["package_count"],
                        "match_field": "office",
                    }
                )
    return {"results": results[:50], "total": len(results)}


@router.get("/live-tenders")
async def search_live_tenders(
    department_id: str = Query(""),
    office_id: str = Query(""),
    keyword: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    svc: IntelligenceDataService = Depends(get_svc),
):
    result = await svc.search_live_tenders(
        department_id=department_id,
        office_id=office_id,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    result["view_type"] = "postgres"
    return result
