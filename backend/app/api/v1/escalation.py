"""Price Escalation API — GCC 70.1 Price Adjustment Calculator"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, Optional
from pydantic import BaseModel

from app.core.security import get_optional_user
from app.services.price_escalation import price_escalation

router = APIRouter(prefix="/escalation", tags=["escalation"])


@router.get("/indices")
async def get_market_indices(
    user: dict = Depends(get_optional_user),
):
    """Get current market price indices for all materials and labor."""
    return {
        "success": True,
        "data": price_escalation.get_current_indices(),
    }


class EscalationRequest(BaseModel):
    base_contract_value: float
    contract_start: str
    current_date: str
    work_type: str = "general"
    material_index_change: Optional[float] = None
    labor_index_change: Optional[float] = None


@router.post("/calculate")
async def calculate_escalation(
    req: EscalationRequest,
    user: dict = Depends(get_optional_user),
):
    """Calculate price escalation for a contract using GCC 70.1 formula."""
    try:
        result = price_escalation.calculate_escalation(
            base_contract_value=req.base_contract_value,
            contract_start=req.contract_start,
            current_date=req.current_date,
            work_type=req.work_type,
            material_index_change=req.material_index_change,
            labor_index_change=req.labor_index_change,
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Escalation calculation failed: {str(e)}")


class ProjectionRequest(BaseModel):
    base_contract_value: float
    contract_start: str
    contract_end: str
    work_type: str = "general"
    annual_escalation_rate: float = 8.0


@router.post("/project")
async def project_escalation(
    req: ProjectionRequest,
    user: dict = Depends(get_optional_user),
):
    """Project total price escalation over full contract period."""
    try:
        result = price_escalation.estimate_future_escalation(
            base_contract_value=req.base_contract_value,
            contract_start=req.contract_start,
            contract_end=req.contract_end,
            work_type=req.work_type,
            annual_escalation_rate=req.annual_escalation_rate,
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Escalation projection failed: {str(e)}")
