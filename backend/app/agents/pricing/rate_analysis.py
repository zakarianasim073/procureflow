"""
Agent 11 — Automated Rate Analysis Agent
Generates rates using SOR zone-based unit rates with overhead and profit markup.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from app.agent_schemas import RateAnalysis

logger = logging.getLogger(__name__)

# Try to load SOR module
try:
    from app.sor import get_rate, get_rate_info
    from app.sor.bwdb import get_rate_info as bwdb_get_rate_info
    from app.sor.lged import get_rate as lged_get_rate
    from app.sor.pwd import get_rate as pwd_get_rate
    SOR_AVAILABLE = True
except ImportError:
    SOR_AVAILABLE = False
    logger.warning("SOR module not available — using estimation")


class RateAnalysisAgent(BaseAgent):
    agent_id = "agent-011-rate-analysis"
    agent_name = "Automated Rate Analysis Agent"
    description = "Generates item rates from SOR zone-based rates with material, labor, equipment, overhead, and profit analysis."
    dependencies: List[str] = ["agent-005-boq-intelligence"]
    version = "2.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        boq_data = context.get("upstream", {}).get("agent-005-boq-intelligence", {})
        items = boq_data.get("items", context.get("boq_items", []))

        # User's zone selection (default to A)
        zone_value = context.get("zone", context.get("sor_zone", "A"))
        if isinstance(zone_value, dict):
            zone_value = zone_value.get("BWDB") or zone_value.get("PWD") or zone_value.get("LGED") or "A"
        zone = str(zone_value or "A").upper()
        if zone not in ("A", "B", "C", "D"):
            zone = "A"

        markup_pct = float(context.get("markup_pct", 0))
        agency = str(context.get("agency", context.get("sor_agency", "BWDB")) or "BWDB").upper()
        if agency not in ("BWDB", "PWD", "LGED"):
            agency = "BWDB"

        analyzed_rates = []
        for item in items:
            item_agency = str(item.get("agency") or agency).upper()
            if item_agency not in ("BWDB", "PWD", "LGED"):
                item_agency = agency
            rate = self._analyze_item_rate(item, zone, markup_pct, item_agency)
            analyzed_rates.append({
                "item_no": rate.item_no,
                "description": rate.description,
                "sor_code": item.get("sor_code", ""),
                "unit": item.get("unit", ""),
                "quantity": item.get("quantity", 0),
                "material_cost": rate.material_cost,
                "labor_cost": rate.labor_cost,
                "equipment_cost": rate.equipment_cost,
                "overhead_percent": rate.overhead_percent,
                "profit_percent": rate.profit_percent,
                "sor_rate": rate.sor_rate,
                "recommended_rate": rate.recommended_rate,
                "notes": rate.notes,
                "agency": item_agency,
            })

        output = {
            "analyzed_items": len(analyzed_rates),
            "rates": analyzed_rates,
            "zone": zone,
            "agency": agency,
            "sor_source": "BWDB/PWD/LGED SOR" if SOR_AVAILABLE else "Estimation",
        }

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=output,
        )

    def _analyze_item_rate(self, item: Dict[str, Any], zone: str = "A", markup_pct: float = 0, agency: str = "BWDB") -> RateAnalysis:
        item_no = item.get("item_no", 0)
        description = item.get("description", "")
        sor_code = item.get("sor_code", "")
        qty = item.get("quantity", 1)
        unit = item.get("unit", "")

        analysis = RateAnalysis(
            item_no=item_no,
            description=description,
        )

        # Try SOR rate lookup first
        sor_rate = None
        sor_info = None
        if SOR_AVAILABLE and sor_code:
            agency = agency.upper()
            if agency == "BWDB":
                sor_info = bwdb_get_rate_info(sor_code, zone)
                sor_rate = sor_info.get("rate") if sor_info else None
            elif agency == "PWD":
                sor_rate = pwd_get_rate(sor_code, zone)
            elif agency == "LGED":
                sor_rate = lged_get_rate(sor_code, zone)
            if sor_rate is None and agency != "BWDB":
                sor_info = bwdb_get_rate_info(sor_code, zone)
                sor_rate = sor_info.get("rate") if sor_info else None
            if sor_rate is None and agency == "BWDB":
                sor_info = get_rate_info(sor_code, zone)
                sor_rate = sor_info.get("rate") if sor_info else None

        if sor_rate and sor_rate > 0:
            # Base rate from SOR
            base_rate = sor_rate
            analysis.sor_rate = round(sor_rate, 2)

            # Apply markup/discount if specified
            if markup_pct != 0:
                recommended = base_rate * (1 + markup_pct / 100)
            else:
                recommended = base_rate

            analysis.recommended_rate = round(recommended, 2)

            # Split into cost components (estimated proportions)
            analysis.material_cost = round(base_rate * qty * 0.55, 2)
            analysis.labor_cost = round(base_rate * qty * 0.20, 2)
            analysis.equipment_cost = round(base_rate * qty * 0.15, 2)
            analysis.overhead_percent = 7.0
            analysis.profit_percent = 3.0

            analysis.notes = (f"SOR rate: ৳{sor_rate:,.2f}/{unit} (Zone {zone})"
                             f"{' + ' + str(markup_pct) + '% markup' if markup_pct else ''}")
        else:
            # Fallback: estimate from category
            category = item.get("category", "")
            if "Earthwork" in category:
                analysis.material_cost = 0
                analysis.labor_cost = 85 * qty
                analysis.equipment_cost = 120 * qty
            elif "Concrete" in category:
                analysis.material_cost = 4500 * qty
                analysis.labor_cost = 800 * qty
                analysis.equipment_cost = 600 * qty
            elif "Steel" in category:
                analysis.material_cost = 120 * qty
                analysis.labor_cost = 15 * qty
                analysis.equipment_cost = 8 * qty
            else:
                analysis.material_cost = 200 * qty
                analysis.labor_cost = 100 * qty
                analysis.equipment_cost = 50 * qty

            analysis.overhead_percent = 10.0
            analysis.profit_percent = 15.0
            base_cost = analysis.material_cost + analysis.labor_cost + analysis.equipment_cost
            overhead_amount = base_cost * analysis.overhead_percent / 100
            profit_amount = (base_cost + overhead_amount) * analysis.profit_percent / 100
            if qty > 0:
                analysis.recommended_rate = round((base_cost + overhead_amount + profit_amount) / qty, 2)
            else:
                analysis.recommended_rate = 0.0
            analysis.sor_rate = 0.0
            analysis.notes = f"Estimated rate (no SOR match for {sor_code})"

        return analysis
