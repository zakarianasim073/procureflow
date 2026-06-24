"""
Tender Pre-Screener Agent — Idle-time Narrowing Engine.

Runs continuously in background during idle time:
  1. Scans all LIVE tenders (33K+)
  2. Scores each tender against company profile
  3. Narrows down to actionable tenders (pre-qualified)
  4. Pre-complicates competitor analysis for top matches
  5. Prepares initial summary for instant user response
  
Narrowing criteria:
  - Agency match (company history with this agency)
  - Zone match (company's zone presence)
  - Category match (company's expertise area)
  - Value match (tender value vs company capacity)
  - Competition intensity
  - Win probability (historical)
  - Profit margin potential
"""
from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import text

from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from app.db.database import get_sync_engine
from app.db.models import PreComputedIntelligence

logger = logging.getLogger(__name__)


class TenderPreScreenerAgent(BaseAgent):
    """
    Pre-emptive tender narrowing engine.
    
    During idle time, analyzes all tenders and scores them against
    company profile to identify the best opportunities before the
    user even asks.
    
    Outputs:
      - Narrowed list: Top 20 tenders for this company
      - Pre-computed analysis: Who, what, when, how to bid
      - Instant readiness: 80% overview ready before user asks
    """
    
    agent_id = "agent-038-tender-pre-screener"
    agent_name = "Tender Pre-Screener"
    description = "Idle-time narrowing engine — pre-qualifies tenders before user asks"
    version = "1.0.0"
    
    def __init__(self, brain=None):
        super().__init__(brain)
        self._engine = get_sync_engine()
    
    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        action = context.get("action", "pre_screen")
        company = context.get("company_profile", {})
        limit = context.get("limit", 50)
        
        if action == "pre_screen":
            result = await self._pre_screen_all(company, limit)
        elif action == "narrowed_list":
            result = await self._get_narrowed_list(company)
        elif action == "tender_match":
            result = self._score_tender(context.get("tender_id", ""), company)
        elif action == "idle_cycle":
            result = await self._idle_cycle()
        else:
            result = {"status": "error", "message": f"Unknown action: {action}"}
        
        return AgentResult(status=AgentStatus.SUCCESS, output=result)
    
    async def _pre_screen_all(self, company: Dict, limit: int = 50) -> Dict:
        """Score all LIVE tenders and return narrowed list."""
        logger.info("🔍 Pre-Screener: Starting pre-screen cycle...")
        
        with self._engine.connect() as conn:
            tenders = conn.execute(text("""
                SELECT tender_id,
                       sor_agency,
                       COALESCE((extracted_data->>'procurement_type'), 'Unknown') AS procurement_type,
                       zone AS zone,
                       estimated_cost,
                       title,
                       division
                FROM tenders 
                WHERE estimated_cost > 0
                LIMIT 2000
            """)).fetchall()
        
        scored = []
        for t in tenders:
            score = self._score_single_tender(t, company)
            if score["overall"] >= 40:  # Only keep promising ones
                scored.append(score)
        
        scored.sort(key=lambda x: x["overall"], reverse=True)
        top = scored[:limit]
        
        # Cache the result
        await self._cache_pre_screen(company.get("company_name", "default"), {
            "total_analyzed": len(tenders),
            "shortlisted": len(scored),
            "top_tenders": top,
            "analyzed_at": datetime.now(timezone.utc).isoformat()
        })
        
        # Share to Knowledge Lake
        await self.share_knowledge(
            entry_type="tender_pre_screen",
            data={
                "total_analyzed": len(tenders),
                "shortlisted": len(scored),
                "top_count": len(top),
            },
            summary=f"Pre-screened {len(tenders)} tenders → narrowed to {len(scored)} candidates",
            tags=["pre-screen", "narrowing", "idle-time"]
        )
        
        logger.info(f"  Pre-screened {len(tenders)} → {len(scored)} shortlisted → Top {len(top)}")
        
        return {
            "status": "complete",
            "total_analyzed": len(tenders),
            "shortlisted": len(scored),
            "top": top[:20],
            "recommendation": self._generate_priority_recommendation(top[:5]),
        }
    
    def _score_single_tender(self, tender, company: Dict) -> Dict:
        """Score a single tender against company profile."""
        tender_id = tender[0] or ""
        agency = tender[1] or ""
        category = tender[2] or ""
        zone = tender[3] or ""
        estimate = float(tender[4] or 0) if tender[4] else 0
        title = tender[5] or ""
        
        scores = {}
        
        # 1. Agency match (30% weight)
        company_agencies = company.get("target_agencies", [])
        if not isinstance(company_agencies, list):
            company_agencies = []
        if company_agencies:
            agency_match = 100 if agency in company_agencies else 30
        else:
            agency_match = 50  # Neutral
        scores["agency_match"] = agency_match
        
        # 2. Zone match (15% weight)
        company_zones = company.get("target_zones", [])
        if not isinstance(company_zones, list):
            company_zones = []
        if company_zones:
            zone_match = 100 if zone in company_zones else 20
        else:
            zone_match = 50
        scores["zone_match"] = zone_match
        
        # 3. Size match (20% weight) - tender should be 5-25% of annual turnover
        turnover = float(company.get("turnover", 0) or 0)
        if turnover > 0:
            ratio = estimate / turnover * 100
            if 5 <= ratio <= 25:
                size_match = 100
            elif 1 <= ratio <= 40:
                size_match = 60
            else:
                size_match = 20
        else:
            size_match = 50
        scores["size_match"] = size_match
        
        # 4. Category match (15% weight)
        company_categories = company.get("expertise_areas", [])
        if not isinstance(company_categories, list):
            company_categories = []
        if company_categories:
            cat_match = 100 if category in company_categories else 20
        else:
            cat_match = 50
        scores["category_match"] = cat_match
        
        # 5. Competition level (20% weight) - from historical data
        with self._engine.connect() as conn:
            comp_count = conn.execute(text("""
                SELECT COUNT(DISTINCT contractor_name) 
                FROM awards WHERE agency = :agency 
                AND contractor_name IS NOT NULL
            """), {"agency": agency}).fetchone()[0] or 0
        
        if comp_count == 0:
            comp_score = 80
        elif comp_count <= 5:
            comp_score = 60
        elif comp_count <= 15:
            comp_score = 40
        else:
            comp_score = 20
        scores["competition_level"] = comp_score
        
        # Calculate weighted overall
        weights = {
            "agency_match": 0.30,
            "zone_match": 0.15,
            "size_match": 0.20,
            "category_match": 0.15,
            "competition_level": 0.20,
        }
        
        overall = sum(scores[k] * weights[k] for k in weights)
        
        return {
            "tender_id": tender_id,
            "agency": agency,
            "category": category,
            "zone": zone,
            "estimate": estimate,
            "title": title[:100] if title else "",
            "scores": scores,
            "overall": round(overall),
            "tier": "top" if overall >= 75 else "watch" if overall >= 55 else "background",
        }
    
    async def _idle_cycle(self) -> Dict:
        """
        Full idle-time processing cycle.
        Called by Brain during idle periods.
        """
        # Default company profile (can be customized later)
        default_company = {
            "company_name": "Default",
            "turnover": 50000000,
            "target_agencies": ["LGED", "BWDB", "PWD"],
            "target_zones": [],
            "expertise_areas": ["Works"],
        }
        
        result = await self._pre_screen_all(default_company, 50)
        
        # Also trigger MOAT and PPR agents
        if self.brain:
            await self.brain.request(
                sender_id=self.agent_id,
                recipient_id="agent-036-moat-slt-analyzer",
                subject="idle_cycle",
                body={"action": "full_analysis"}
            )
        
        return result
    
    def _generate_priority_recommendation(self, top_tenders: List) -> Dict:
        """Generate priority actions from top tenders."""
        if not top_tenders:
            return {"action": "no_tenders", "message": "No matching tenders found"}
        
        best = top_tenders[0]
        return {
            "action": "analyze_top",
            "priority_tender": best["tender_id"],
            "priority_agency": best["agency"],
            "priority_estimate": best["estimate"],
            "match_score": best["overall"],
            "message": f"Top opportunity: {best['agency']} tender worth BDT {best['estimate']:,.0f}",
            "analysis_needed": True
        }
    
    async def _get_narrowed_list(self, company: Dict) -> List:
        """Get cached narrowed list or trigger new analysis."""
        key = f"pre_screen_{company.get('company_name', 'default')}"
        from app.db.database import get_session
        from sqlalchemy import select
        
        session = get_session()
        async with session as s:
            existing = await s.execute(
                select(PreComputedIntelligence).where(
                    PreComputedIntelligence.cache_key == key
                ).order_by(PreComputedIntelligence.updated_at.desc()).limit(1)
            )
            entry = existing.scalar_one_or_none()
            if entry:
                return entry.cache_data.get("top", [])
        
        return []
    
    async def _cache_pre_screen(self, company_name: str, data: Dict):
        """Cache pre-screen results."""
        from app.db.database import get_session
        from sqlalchemy import select
        
        key = f"pre_screen_{company_name}"
        session = get_session()
        async with session as s:
            existing = await s.execute(
                select(PreComputedIntelligence).where(
                    PreComputedIntelligence.cache_key == key
                ).limit(1)
            )
            entry = existing.scalar_one_or_none()
            if entry:
                entry.cache_data = data
                entry.intelligence_type = "pre_screen"
                entry.updated_at = datetime.now(timezone.utc)
            else:
                entry = PreComputedIntelligence(
                    cache_key=key,
                    cache_data=data,
                    intelligence_type="pre_screen",
                    updated_at=datetime.now(timezone.utc),
                )
                s.add(entry)
            await s.commit()

    def _score_tender(self, tender_id: str, company: Dict) -> Dict:
        """Score a single tender against company."""
        with self._engine.connect() as conn:
            tender = conn.execute(text(
                "SELECT tender_id, sor_agency, COALESCE((extracted_data->>'procurement_type'), 'Unknown') AS procurement_type, zone AS zone, estimated_cost, title FROM tenders WHERE tender_id = :id"
            ), {"id": tender_id}).fetchone()
            if tender:
                return self._score_single_tender(tuple(tender), company)
        return {"tender_id": tender_id, "status": "not_found"}
