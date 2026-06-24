"""
Agent 1 - Tender Radar Agent
Scans e-GP/LGED/RHD/BWDB/PWD for new tenders matching company profile.
"""
from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from typing import Any, Dict, List
import logging

logger = logging.getLogger(__name__)

class TenderRadarAgent(BaseAgent):
    agent_id = "agent-001-tender-radar"
    agent_name = "Tender Radar"
    description = "Tender discovery and matching engine"
    dependencies = []
    version = "1.0.0"

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        tenders = context.get("tenders", [])
        filters = context.get("filters", {})
        matched = []
        for t in tenders:
            score = self._match_score(t, filters)
            if score > 0:
                matched.append({"tender_id": t.get("tender_id"), "title": t.get("title"), "score": score})
        
        # Share knowledge: notify brain about matched tenders
        for m in matched:
            await self.share_knowledge(
                entry_type="tender_alert",
                tender_id=m["tender_id"],
                data={"title": m["title"], "score": m["score"], "filters": filters},
                summary=f"Matched tender {m['tender_id']} with score {m['score']}",
                tags=["tender_radar", "matched"]
            )
        
        # Ask TenderAcquisition to download docs for top matches
        if matched and self.brain:
            top = sorted(matched, key=lambda x: x["score"], reverse=True)[:3]
            for m in top:
                await self.ask_agent(
                    "agent-002-tender-acquisition",
                    "download_documents",
                    {"tender_id": m["tender_id"], "title": m["title"], "priority": "high"}
                )
        
        return AgentResult(
            status=AgentStatus.SUCCESS,
            output={"matched_tenders": matched, "total": len(matched), "scanned": len(tenders)}
        )

    def _match_score(self, tender: Dict, filters: Dict) -> float:
        score = 50.0
        if filters.get("agency") and filters["agency"].lower() in str(tender.get("agency", "")).lower():
            score += 20
        if filters.get("min_value") and float(tender.get("estimated_amount_bdt", 0)) >= filters["min_value"]:
            score += 15
        if filters.get("max_value") and float(tender.get("estimated_amount_bdt", 0)) <= filters["max_value"]:
            score += 15
        return score
