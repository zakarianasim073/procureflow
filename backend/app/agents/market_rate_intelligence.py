"""
Agent 12 — Market Rate Intelligence Agent
Analyzes current market rates for materials, labor, and equipment to validate SOR rates and flag variances.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class MarketRateIntelligenceAgent(BaseAgent):
    agent_id = "agent-012-market-rate-intelligence"
    agent_name = "Market Rate Intelligence Agent"
    description = "Analyzes current market rates for construction inputs (materials, labor, equipment) to validate SOR rates and flag significant variances."
    dependencies: List[str] = ["agent-011-rate-analysis"]
    version = "2.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        sor_data = context.get("sor_data", {})
        zone = context.get("zone", "A")
        if isinstance(zone, dict):
            zone = zone.get("BWDB") or zone.get("PWD") or zone.get("LGED") or "A"
        zone = str(zone or "A")
        boq_items = context.get("boq_items", [])

        market_rates = await self._analyze_market_rates(sor_data, zone, boq_items)

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=market_rates,
        )

    async def _analyze_market_rates(self, sor_data: Dict, zone: str, boq_items: List) -> Dict:
        """Analyze market rates and compare with SOR."""
        # Market rate database (simulated — in production would fetch from live sources)
        market_rates_db = {
            "materials": {
                "Cement (OPC)": {"unit": "bag", "market_rate": 480, "sor_rate": 520, "trend": "stable"},
                "Cement (PCC)": {"unit": "bag", "market_rate": 460, "sor_rate": 500, "trend": "stable"},
                "MS Rod (60 grade)": {"unit": "ton", "market_rate": 78000, "sor_rate": 82000, "trend": "up"},
                "MS Rod (40 grade)": {"unit": "ton", "market_rate": 74000, "sor_rate": 78000, "trend": "up"},
                "Brick (1st class)": {"unit": "1000pcs", "market_rate": 9500, "sor_rate": 10200, "trend": "stable"},
                "Brick (2nd class)": {"unit": "1000pcs", "market_rate": 8200, "sor_rate": 8800, "trend": "stable"},
                "Stone chips": {"unit": "cft", "market_rate": 85, "sor_rate": 95, "trend": "up"},
                "Sand (coarse)": {"unit": "cft", "market_rate": 55, "sor_rate": 60, "trend": "stable"},
                "Sand (fine)": {"unit": "cft", "market_rate": 40, "sor_rate": 45, "trend": "down"},
                "Bitumen (80/100)": {"unit": "ton", "market_rate": 65000, "sor_rate": 72000, "trend": "up"},
                "Paint (weather)": {"unit": "litre", "market_rate": 350, "sor_rate": 400, "trend": "stable"},
                "Tile (ceramic)": {"unit": "sqft", "market_rate": 95, "sor_rate": 110, "trend": "stable"},
                "Sanitary ware": {"unit": "set", "market_rate": 4500, "sor_rate": 5200, "trend": "stable"},
            },
            "labor": {
                "Skilled labor": {"unit": "day", "market_rate": 800, "sor_rate": 700, "trend": "up"},
                "Semi-skilled": {"unit": "day", "market_rate": 600, "sor_rate": 550, "trend": "up"},
                "Unskilled labor": {"unit": "day", "market_rate": 450, "sor_rate": 400, "trend": "stable"},
                "Mason": {"unit": "day", "market_rate": 950, "sor_rate": 850, "trend": "up"},
                "Carpenter": {"unit": "day", "market_rate": 900, "sor_rate": 800, "trend": "up"},
                "Rod bender": {"unit": "day", "market_rate": 850, "sor_rate": 750, "trend": "up"},
            },
            "equipment": {
                "Excavator (1 cft)": {"unit": "hour", "market_rate": 2500, "sor_rate": 2200, "trend": "stable"},
                "Bulldozer (D6)": {"unit": "hour", "market_rate": 4500, "sor_rate": 4000, "trend": "up"},
                "Vibratory roller": {"unit": "hour", "market_rate": 3500, "sor_rate": 3200, "trend": "stable"},
                "Concrete mixer": {"unit": "hour", "market_rate": 1200, "sor_rate": 1000, "trend": "stable"},
                "Dump truck": {"unit": "hour", "market_rate": 2000, "sor_rate": 1800, "trend": "stable"},
                "Crane (15 ton)": {"unit": "hour", "market_rate": 5000, "sor_rate": 4500, "trend": "stable"},
            },
        }

        # Zone adjustment factors
        zone_factors = {"A": 1.0, "B": 1.05, "C": 1.10, "D": 1.15}
        zf = zone_factors.get(zone.upper(), 1.0)

        # Analyze each category
        flagged_items = []
        category_analysis = {}
        
        for category, items in market_rates_db.items():
            category_items = []
            total_variance = 0
            
            for name, data in items.items():
                adjusted_market = data["market_rate"] * zf
                variance_pct = ((data["sor_rate"] - adjusted_market) / max(adjusted_market, 1)) * 100
                
                item = {
                    "name": name,
                    "unit": data["unit"],
                    "market_rate": round(adjusted_market, 2),
                    "sor_rate": data["sor_rate"],
                    "variance_pct": round(variance_pct, 1),
                    "trend": data["trend"],
                    "flag": "OVER" if variance_pct > 10 else "UNDER" if variance_pct < -10 else "AT PAR",
                }
                category_items.append(item)
                total_variance += abs(variance_pct)
                
                if abs(variance_pct) > 15:
                    flagged_items.append(item)
            
            category_analysis[category] = {
                "items": category_items,
                "avg_variance": round(total_variance / max(len(items), 1), 1),
                "count": len(items),
            }

        # Overall market insight
        total_market = sum(
            sum(data["market_rate"] for data in items.values())
            for items in market_rates_db.values()
        )
        total_sor = sum(
            sum(data["sor_rate"] for data in items.values())
            for items in market_rates_db.values()
        )
        overall_variance = ((total_sor - total_market) / max(total_market, 1)) * 100

        return {
            "zone": zone.upper(),
            "zone_factor": zf,
            "overall_variance_pct": round(overall_variance, 1),
            "overall_assessment": "SOR rates are above market" if overall_variance > 5 else "SOR rates align with market" if overall_variance > -5 else "SOR rates are below market",
            "categories": category_analysis,
            "flagged_items": flagged_items,
            "recommendations": [
                "Consider market rate adjustments for items with >15% variance",
                f"Zone {zone.upper()} has {zf}x multiplier applied to base market rates",
                "Labor rates are trending upward — factor into bid pricing",
                "Steel and bitumen prices are rising — consider price escalation clause",
            ],
        }
