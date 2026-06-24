"""SOR API routes"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, Dict, Any
from pathlib import Path

from app.core.config import settings
from app.core.security import get_optional_user
from app.sor.sor_service import sor_service

router = APIRouter(prefix="/sor", tags=["sor"])


@router.get("/agencies")
async def list_sor_agencies(
    user: dict = Depends(get_optional_user),
):
    """List available SOR agencies with stats"""
    agencies = []
    for agency in ['BWDB', 'PWD', 'LGED']:
        stats = sor_service.get_stats(agency)
        agencies.append({
            "id": agency.lower(),
            "name": agency,
            "total_rates": stats["total_rates"],
            "has_csv": stats["has_csv"],
        })
    return {"agencies": agencies}


@router.get("/lookup")
async def lookup_sor_rate(
    code: str = Query(..., description="Item code to look up"),
    agency: str = Query("BWDB", pattern="^(BWDB|PWD|LGED)$"),
    zone: Optional[str] = Query(None, pattern="^(A|B|C|D)$"),
    description: Optional[str] = Query(None),
    user: dict = Depends(get_optional_user),
):
    """Look up a single SOR rate by code"""
    rate, record = sor_service.find_rate(code, description or "", agency, zone)
    if rate is None:
        raise HTTPException(status_code=404, detail="Rate not found")
    
    return {
        "code": record.code,
        "description": record.description,
        "unit": record.unit,
        "zone_a": record.zone_a,
        "zone_b": record.zone_b,
        "zone_c": record.zone_c,
        "zone_d": record.zone_d,
        "rate": rate,
        "zone": zone or "A",
        "agency": agency,
    }


@router.post("/load-pdf")
async def load_sor_from_pdf(
    agency: str = Query(..., pattern="^(BWDB|PWD|LGED)$"),
    zone: Optional[str] = Query(None, pattern="^(A|B|C|D)$"),
    file: Optional[str] = Query(None, description="Path to PDF file"),
    user: dict = Depends(get_optional_user),
):
    """Load SOR rates from PDF file"""
    if not file:
        raise HTTPException(status_code=400, detail="PDF file path required")
    
    pdf_path = Path(file)
    if not pdf_path.exists():
        # Try relative to base dir
        pdf_path = Path(settings.BASE_DIR) / "uploads" / file
        if not pdf_path.exists():
            raise HTTPException(status_code=404, detail="PDF file not found")
    
    loaded = sor_service.load_from_pdf(agency, str(pdf_path), zone)
    return {"success": True, "loaded": loaded, "agency": agency}
