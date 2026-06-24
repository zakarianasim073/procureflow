"""
Agent 14 — Award Intelligence Agent
Collects and stores historical contract awards from eGP and other sources.
Integrates with database, DataIntelligenceService, and BWDB monitor.
Supports bulk daily collection of 1000+ tenders.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class AwardIntelligenceAgent(BaseAgent):
    agent_id = "agent-014-award-intelligence"
    agent_name = "Award Intelligence Agent"
    description = "Collects historical contract award data from eGP portals, stores locally, and alerts on high-value BWDB tenders."
    dependencies: List[str] = []
    version = "3.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        page = context.get("page", 1)
        limit = context.get("limit", 50)
        agency = context.get("agency", "")
        bulk_mode = context.get("bulk_mode", False)
        target_count = context.get("target_count", 1000)
        run_bwdb_monitor = context.get("run_bwdb_monitor", True)

        if bulk_mode:
            result = await self._run_bulk_collection(target_count, agency, run_bwdb_monitor)
        else:
            awards = await self._collect_awards(page, limit, agency)
            analysis = self._analyze_awards(awards)
            result = {
                "awards_collected": len(awards),
                "page": page,
                "total_available": len(awards),
                "awards": awards,
                "analysis": analysis,
                "status": "Award History Updated",
            }

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=result,
        )

    async def _run_bulk_collection(self, target_count: int, agency: str, run_bwdb_monitor: bool) -> Dict:
        """Run bulk collection targeting at least target_count records."""
        logger.info(f"Starting bulk collection: target={target_count}, agency='{agency}'")

        try:
            from ..services.data_intelligence import data_intelligence

            collection = data_intelligence.run_bulk_collection(target_count=target_count)

            # Run BWDB monitor on collected tenders
            bwdb_alerts = []
            if run_bwdb_monitor:
                try:
                    from ..services.bwdb_monitor import bwdb_monitor
                    tenders = data_intelligence.get_tenders_by_agency("BWDB")
                    bwdb_alerts = await bwdb_monitor.scan_and_alert(tenders)
                    logger.info(f"BWDB monitor: {len(bwdb_alerts)} alerts sent")
                except Exception as e:
                    logger.warning(f"BWDB monitor failed: {e}")

            # Collect award statistics
            stats = data_intelligence.get_statistics()

            return {
                "bulk_collection": collection,
                "bwdb_alerts_sent": len(bwdb_alerts),
                "bwdb_alerts": bwdb_alerts[:10],
                "statistics": stats,
                "status": "Bulk Collection Complete",
                "target_met": collection.get("target_met", False),
            }

        except Exception as e:
            logger.error(f"Bulk collection failed: {e}")
            return {
                "error": str(e),
                "status": "Bulk Collection Failed",
                "target_met": False,
            }

    def _analyze_awards(self, awards: List[Dict]) -> Dict:
        """Analyze collected award data for patterns and insights."""
        if not awards:
            return {
                "avg_discount": 0,
                "avg_bidders": 0,
                "top_winners": [],
                "agency_breakdown": {},
                "total_value": 0,
            }

        total_value = sum(a.get("award_amount", 0) for a in awards)
        avg_discount = sum(a.get("discount_percent", 0) for a in awards) / len(awards) if awards else 0
        avg_bidders = sum(a.get("num_bidders", 0) for a in awards) / len(awards) if awards else 0

        winners = {}
        for a in awards:
            w = a.get("winner", "Unknown")
            winners[w] = winners.get(w, 0) + 1
        top_winners = sorted(winners.items(), key=lambda x: -x[1])[:5]

        agencies = {}
        for a in awards:
            e = a.get("procuring_entity", "Unknown")
            if e not in agencies:
                agencies[e] = {"count": 0, "total_value": 0}
            agencies[e]["count"] += 1
            agencies[e]["total_value"] += a.get("award_amount", 0)

        return {
            "avg_discount": round(avg_discount, 2),
            "avg_bidders": round(avg_bidders, 1),
            "top_winners": [{"name": w, "wins": c} for w, c in top_winners],
            "agency_breakdown": agencies,
            "total_value": total_value,
        }

    async def _collect_awards(self, page: int, limit: int, agency: str) -> List[Dict]:
        """Collect awards from eGP portal using NOA/eCMS scraping."""
        try:
            from .egp_client import eGPClient
            from .credentials import get_credentials
            creds = get_credentials()
            client = eGPClient(email=creds.egp.email, password=creds.egp.password, timeout=15)
            if creds.egp.is_valid:
                client.login()
            result = client.collect_award_intelligence(entity=agency)
            client.close()

            awards = []
            for source_key in ['noa_awards', 'ecms_experience', 'offline_awards']:
                for raw in result.get(source_key, []):
                    award = {
                        "tender_id": raw.get("tender_id", f"UNKNOWN-{len(awards)}"),
                        "source": raw.get("source", source_key),
                        "procuring_entity": agency or raw.get("raw_data", [""])[1] if len(raw.get("raw_data", [])) > 1 else "",
                        "award_amount": raw.get("amount_bdt", 0),
                        "winner": raw.get("raw_data", [""])[2] if len(raw.get("raw_data", [])) > 2 else "Unknown",
                        "award_date": "",
                        "num_bidders": 0,
                        "discount_percent": 0,
                        "contract_period_days": 0,
                        "category": "Award",
                    }
                    if award["tender_id"] and award["tender_id"] != "UNKNOWN":
                        awards.append(award)

            if awards:
                logger.info(f"Collected {len(awards)} real awards from eGP")
                return awards
        except Exception as exc:
            logger.warning(f"eGP award scraping failed: {exc}")

        # Primary fallback: use PostgreSQL-backed intelligence data
        try:
            from app.db.base import get_session_factory
            from app.services.intelligence_data_service import IntelligenceDataService

            sf = get_session_factory()
            async with sf() as session:
                db_records = await IntelligenceDataService(session).list_awards_for_agent(agency, limit=limit)
            if db_records:
                logger.info(f"Loaded {len(db_records)} awards from PostgreSQL for {agency or 'all agencies'}")
                return db_records
        except Exception as exc:
            logger.debug(f"PostgreSQL award fallback failed: {exc}")

        # Fallback: use DataIntelligenceService
        try:
            from ..services.data_intelligence import data_intelligence
            result = data_intelligence.collect_noa_awards(entity=agency, days=90, max_pages=3)
            fp = result.get("file", "")
            if fp:
                import json
                from pathlib import Path
                awards_data = json.loads(Path(fp).read_text())
                logger.info(f"Loaded {len(awards_data)} awards from local storage")
                return awards_data
        except Exception as exc:
            logger.debug(f"Data intelligence fallback failed: {exc}")

        # Use NOA servlet directly
        try:
            from .egp_client import eGPClient
            client = eGPClient(timeout=10)
            noa_results = client.search_noa("", agency, 90)
            client.close()
            if noa_results:
                logger.info(f"Collected {len(noa_results)} real NOA awards for '{agency}'")
                return noa_results
        except Exception as exc:
            logger.warning(f"NOA collection failed: {exc}")

        # Final fallback: return mock data
        logger.info("Using mock award data (no eGP or DB available)")
        return self._mock_awards(page, limit, agency)

    def _mock_awards(self, page: int, limit: int, agency: str) -> List[Dict]:
        """Generate mock award data as final fallback."""
        agencies_pool = ["LGED", "RHD", "PWD", "BWDB", "DPHE", "BREB", "BADC", "City Corporation"]
        winners_pool = [
            "XYZ Builders Ltd.", "ABC Construction Ltd.", "PQR Infrastructure Ltd.",
            "Delta Engineering Ltd.", "Sigma Developers Ltd.", "Omega Construction",
            "Metro Builders Ltd.", "Prime Contractors Ltd.", "United Engineering",
            "Royal Construction Co.", "Modern Builders Ltd.", "Trust Developers Ltd.",
        ]
        
        filtered_agencies = [a for a in agencies_pool if not agency or agency.upper() in a.upper()]
        if not filtered_agencies:
            filtered_agencies = agencies_pool[:1]
        
        awards = []
        for i in range(1, min(limit + 1, 25)):
            entity = filtered_agencies[i % len(filtered_agencies)]
            month = (i % 12) + 1
            award = {
                "tender_id": f"eGP-MOCK-{page}-{i}",
                "title": f"Development Works Package {chr(64+i)} under {entity}",
                "procuring_entity": entity,
                "winner": winners_pool[i % len(winners_pool)],
                "award_amount": round(25_000_000 + (i * 1_500_000 * (page * 0.5 + 0.5)), 2),
                "award_date": f"2026-{month:02d}-15",
                "num_bidders": 3 + (i % 5),
                "discount_percent": round(3.5 + (i % 7) * 0.75, 2),
                "contract_period_days": 300 + (i * 20),
                "source": "mock",
                "category": "Construction" if i % 3 != 0 else "Goods",
            }
            awards.append(award)
        
        return awards
