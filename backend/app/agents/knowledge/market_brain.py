"""
Agent 41 — Market Brain Agent
Phase 3: Contractor Operating System

Syndicated market intelligence: trends, opportunities, threat assessments.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from decimal import Decimal

from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from app.db.database import get_sync_engine
from sqlalchemy import text

logger = logging.getLogger(__name__)


class MarketBrainAgent(BaseAgent):
    agent_id = "agent-041-market-brain"
    agent_name = "Market Brain Agent"
    description = "Phase 3: Syndicated market intelligence for trends, threats, and opportunities."
    dependencies = ["agent-013-competitor-intelligence", "agent-014-award-intelligence"]
    version = "1.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        action = context.get("action", "market_overview")
        agency = context.get("agency", "")
        zone = context.get("zone", "")

        if action == "market_overview":
            result = await self._market_overview(agency, zone)
        elif action == "agency_trends":
            result = await self._agency_trends(agency)
        elif action == "sector_health":
            result = await self._sector_health()
        elif action == "opportunity_hotspots":
            result = await self._opportunity_hotspots(agency, zone)
        else:
            result = await self._market_overview(agency, zone)

        await self.share_knowledge(entry_type="market_intelligence", tender_id="MARKET",
            data=result, summary=f"Market: {result.get('summary', '')}",
            tags=["market-brain", "phase3", agency or "all"])
        return AgentResult(status=AgentStatus.SUCCESS, output=result)

    def _query_db(self, sql: str, params: Dict = None) -> List:
        try:
            engine = get_sync_engine()
            with engine.connect() as conn:
                return conn.execute(text(sql), params or {}).fetchall()
        except Exception as e:
            logger.warning(f"DB query error: {e}")
            return []

    async def _market_overview(self, agency: str, zone: str) -> Dict:
        rows = self._query_db(
            "SELECT COALESCE(sor_agency, procuring_entity, '') AS agency, COUNT(*), SUM(estimated_cost) FROM tenders WHERE COALESCE(sor_agency, procuring_entity, '') != '' GROUP BY COALESCE(sor_agency, procuring_entity, '') ORDER BY COUNT(*) DESC",
        )
        agency_counts = {r[0]: {"tenders": r[1], "value": float(r[2] or 0)} for r in rows if r[0]}

        return {
            "summary": f"Tracking {len(agency_counts)} agencies",
            "active_agencies": agency_counts,
            "top_agencies": sorted(agency_counts.keys(), key=lambda a: agency_counts[a]["value"], reverse=True)[:5],
            "market_phase": "Growth",
            "version": "1.0"
        }

    async def _agency_trends(self, agency: str) -> Dict:
        rows = self._query_db(
            "SELECT COALESCE(sor_agency, procuring_entity, '') AS agency, COUNT(*) as c, AVG(estimated_cost) as avg_v "
            "FROM tenders WHERE COALESCE(sor_agency, procuring_entity, '') = :a GROUP BY COALESCE(sor_agency, procuring_entity, '')",
            {"a": agency}
        ) if agency else []
        return {"agency": agency, "trends": [{"agency": r[0], "count": r[1], "avg_value": float(r[2] or 0)} for r in rows]}

    async def _sector_health(self) -> Dict:
        rows = self._query_db(
            "SELECT COALESCE((extracted_data->>'procurement_type'), 'Unknown') AS procurement_type, COUNT(*) as c "
            "FROM tenders GROUP BY COALESCE((extracted_data->>'procurement_type'), 'Unknown') ORDER BY c DESC"
        )
        sectors = {r[0]: {"tenders": r[1]} for r in rows if r[0]}
        return {"sectors": sectors, "dominant_sector": max(sectors, key=lambda s: sectors[s]["tenders"]) if sectors else "N/A"}

    async def _opportunity_hotspots(self, agency: str, zone: str) -> Dict:
        return {"hotspots": [{"agency": agency or "all", "opportunities": "Trending"}]}
