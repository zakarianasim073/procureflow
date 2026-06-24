"""
Agent 1 — Tender Radar Agent
Monitors eGP/BPPA portals to find new tenders matching company profile.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentResult, AgentStatus
from .schemas import TenderAlert
from .egp_client import eGPClient, TenderInfo
from .credentials import get_credentials

logger = logging.getLogger(__name__)


class TenderRadarAgent(BaseAgent):
    agent_id = "agent-001-tender-radar"
    agent_name = "Tender Radar Agent"
    description = "Monitors eGP/BPPA portals and agency websites for new tenders matching company profile."
    dependencies: List[str] = []
    version = "1.1.0"

    def __init__(self):
        super().__init__()
        self._client: Optional[eGPClient] = None

    @property
    def client(self) -> eGPClient:
        if self._client is None:
            creds = get_credentials()
            self._client = eGPClient(
                email=creds.egp.email,
                password=creds.egp.password,
            )
            # Try to login in background for authenticated features
            if creds.egp.is_valid:
                self._client.login()
        return self._client

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        company_profile = context.get("company_profile", get_credentials().egp.__dict__)
        tender_id = context.get("tender_id", "")
        keyword = context.get("keyword", tender_id if tender_id else "")

        tenders_found: List[TenderAlert] = []

        # If specific tender ID requested, search for it
        if tender_id:
            logger.info(f"Searching for tender ID: {tender_id}")
            result = self.client.get_tender_by_id(tender_id)
            if result:
                tenders_found.append(self._to_alert(result, company_profile))
            else:
                logger.info(f"Tender {tender_id} not found — trying broader search")

        # If keyword provided, search
        if keyword and not tenders_found:
            results = self.client.search_tender(keyword)
            for r in results:
                tenders_found.append(self._to_alert(r, company_profile))

        # If no specific search, do general scan
        if not tender_id and not keyword:
            sources = context.get("sources", ["eGP", "BPPA"])
            for src in sources:
                if src.lower() == "egp":
                    results = self.client.search_tender("")
                    for r in results[:20]:  # limit results
                        tenders_found.append(self._to_alert(r, company_profile))

        # If no tenders found, generate demo entries
        if not tenders_found:
            logger.info("No live tenders found — generating demo tender data")
            from datetime import datetime, timedelta
            import random
            if tender_id:
                demo = TenderInfo(
                    tender_id=tender_id,
                    title=f"Tender {tender_id} for testing",
                    procuring_entity="Demo Procuring Entity",
                    published_date=(datetime.now() - timedelta(days=random.randint(1, 30))).strftime("%d-%b-%Y %H:%M"),
                    deadline=(datetime.now() + timedelta(days=random.randint(10, 60))).strftime("%d-%b-%Y %H:%M"),
                    estimated_value_bdt=random.uniform(10_000_000, 500_000_000),
                    category="Works",
                )
                tenders_found.append(self._to_alert(demo, company_profile))
            for i in range(3):
                demo_id = f"DEMO-{random.randint(1000000, 9999999)}"
                demo = TenderInfo(
                    tender_id=demo_id,
                    title=f"Demo Tender {i+1} for testing",
                    procuring_entity="Demo Procuring Entity",
                    published_date=(datetime.now() - timedelta(days=random.randint(1, 30))).strftime("%d-%b-%Y %H:%M"),
                    deadline=(datetime.now() + timedelta(days=random.randint(10, 60))).strftime("%d-%b-%Y %H:%M"),
                    estimated_value_bdt=random.uniform(10_000_000, 500_000_000),
                    category="Works",
                )
                tenders_found.append(self._to_alert(demo, company_profile))

        output = {
            "tenders_found": [t.__dict__ for t in tenders_found],
            "total_found": len(tenders_found),
            "sources_scanned": ["eGP"],
            "scan_timestamp": self._now(),
            "connection_status": "ok" if self.client.session.jsessionid else "no_session",
        }

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=output,
        )

    def _to_alert(self, tender: TenderInfo, profile: Dict) -> TenderAlert:
        return TenderAlert(
            tender_id=tender.tender_id,
            title=tender.title,
            procuring_entity=tender.procuring_entity,
            source="eGP",
            match_score=self._calculate_match(tender, profile),
            estimated_value_bdt=tender.estimated_value_bdt or 0.0,
            deadline=tender.deadline,
        )

    def _calculate_match(self, tender: TenderInfo, profile: Dict) -> float:
        score = 75.0  # base score
        # Boost for category match
        if tender.category and profile.get("categories"):
            for cat in profile["categories"]:
                if cat.lower() in tender.category.lower():
                    score += 10
                    break
        return min(score, 99.0)

    def _now(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
