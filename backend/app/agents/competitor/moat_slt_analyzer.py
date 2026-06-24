"""
MOAT & SLT Analyzer Agent — Pre-emptive Competitive Intelligence.

MOAT = Margin Over Assessment Threshold (competitive advantage analysis)
SLT  = Standard L1 Threshold (expected winning discount per category)

Runs pre-emptively during idle time:
  1. Analyzes 50K+ historical awards to compute SLT per category/agency/zone
  2. Computes NPPI (Normalized Percentage Price Index) per procurement category
  3. Identifies competitive moat: what advantage does each bidder have?
  4. Pre-computes expected winning range for each LIVE tender
  
Outputs cached in pre_computed_intelligence table for instant query.
"""
from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from decimal import Decimal
from sqlalchemy import text, func

from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from app.agents.core.regime import get_regime, regime_weight, regime_sql_filter
from app.db.database import get_sync_engine, get_session
from app.db.models import PreComputedIntelligence

logger = logging.getLogger(__name__)


class MoatSLTAnalyzerAgent(BaseAgent):
    """
    Pre-emptive competitive intelligence agent.
    
    During idle time, analyzes historical data to pre-compute:
    - SLT per category/agency/zone (expected discount threshold)
    - NPPI values per procurement category
    - Competitor positioning maps
    - Expected winning ranges for LIVE tenders
    - Competitive moat analysis for each bidder
    """
    
    agent_id = "agent-036-moat-slt-analyzer"
    agent_name = "MOAT & SLT Analyzer"
    description = "Pre-emptive competitive intelligence & threshold analysis"
    version = "1.0.0"
    
    def __init__(self, brain=None):
        super().__init__(brain)
        self._engine = get_sync_engine()
    
    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        action = context.get("action", "full_analysis")
        tender_id = context.get("tender_id", "")
        
        if action == "compute_slt":
            result = await self._compute_slt_by_category()
        elif action == "compute_nppi":
            result = await self._compute_nppi_values()
        elif action == "tender_analysis":
            result = await self._analyze_tender(tender_id, context)
        elif action == "competitor_moat":
            result = self._competitor_moat_analysis(tender_id, context)
        elif action == "full_analysis":
            # Run full pre-emptive analysis (idle cycle)
            result = await self._full_analysis()
        elif action == "get_cached":
            result = await self._get_cached_analysis(tender_id)
        else:
            result = {"status": "error", "message": f"Unknown action: {action}"}
        
        return AgentResult(status=AgentStatus.SUCCESS, output=result)
    
    async def _full_analysis(self) -> Dict:
        """Run full pre-emptive analysis cycle."""
        logger.info("🧠 MOAT/SLT: Starting full analysis cycle...")
        
        # Step 1: Compute SLT per category/agency
        slt_by_cat = await self._compute_slt_by_category()
        
        # Step 2: Compute NPPI values
        nppi = await self._compute_nppi_values()
        
        # Step 3: Analyze all LIVE tenders
        tender_analyses = await self._analyze_live_tenders()
        
        # Step 4: Cache results
        await self._cache_results("moat_slt_full", {
            "slt_by_category": slt_by_cat,
            "nppi_values": nppi,
            "tenders_analyzed": len(tender_analyses),
            "analyzed_at": datetime.now(timezone.utc).isoformat()
        })
        
        # Share to Knowledge Lake
        if self.brain:
            await self.share_knowledge(
                entry_type="moat_slt_analysis",
                tender_id="GLOBAL-MOAT-SLT",
                data={"slt_categories": len(slt_by_cat), "nppi_categories": len(nppi)},
                summary=f"Pre-computed SLT for {len(slt_by_cat)} categories, NPPI for {len(nppi)} categories",
                tags=["moat", "slt", "nppi", "pre-emptive"]
            )
        
        return {
            "status": "complete",
            "slt_categories": len(slt_by_cat),
            "nppi_categories": len(nppi),
            "tenders_analyzed": len(tender_analyses),
            "cached": True
        }
    
    async def _compute_slt_by_category(self) -> List[Dict]:
        """
        Compute Standard L1 Threshold (SLT) per procurement category.
        
        SLT = Expected winning discount for a given category.
        Uses 50K+ historical awards to calculate:
          - Average discount (OE - Award) / OE
          - Standard deviation
          - 10th/90th percentile (aggressive/conservative ranges)
        """
        with self._engine.connect() as conn:
            # Get awards that have matching tenders with estimates
            rows = conn.execute(text("""
                SELECT 
                    COALESCE(a.procurement_type, (t.extracted_data->>'procurement_type'), 'Unknown') as category,
                    COALESCE(t.sor_agency, t.procuring_entity, a.agency, 'Unknown') as agency,
                    COALESCE(t.zone, t.division, 'Unknown') as zone,
                    COUNT(*) as sample_count,
                    AVG((t.estimated_cost - a.award_amount) / NULLIF(t.estimated_cost, 0) * 100) as avg_discount_pct,
                    MIN((t.estimated_cost - a.award_amount) / NULLIF(t.estimated_cost, 0) * 100) as min_discount_pct,
                    MAX((t.estimated_cost - a.award_amount) / NULLIF(t.estimated_cost, 0) * 100) as max_discount_pct
                FROM awards a
                JOIN tenders t ON a.tender_id = t.tender_id
                WHERE t.estimated_cost > 0 
                  AND a.award_amount > 0
                  AND t.opening_date >= '2025-09-28'
                GROUP BY 1, 2, 3
                ORDER BY sample_count DESC
                LIMIT 200
            """)).fetchall()
            
            results = []
            for r in rows:
                entry = {
                    "category": r[0] or "Unknown",
                    "agency": r[1] or "Unknown",
                    "zone": r[2] or "Unknown",
                    "sample_count": r[3],
                    "avg_discount_pct": float(r[4]) if r[4] else 0,
                    "min_discount_pct": float(r[5]) if r[5] else 0,
                    "max_discount_pct": float(r[6]) if r[6] else 0,
                    "slt_conservative": max(0, (float(r[4]) if r[4] else 0) * 0.7),  # 70% of avg
                    "slt_aggressive": min(30, (float(r[4]) if r[4] else 0) * 1.3),     # 130% of avg, capped
                }
                results.append(entry)
            
            # Cache each
            for entry in results[:100]:
                await self._cache_results(f"slt_{entry['agency']}_{entry['category']}", entry)
            
            logger.info(f"  SLT: Computed for {len(results)} category/agency/zone combinations")
            return results
    
    async def _compute_nppi_values(self) -> List[Dict]:
        """
        Compute Normalized Percentage Price Index per category.
        
        NPPI = (Estimate - Award) / Estimate × 100
        Stored per category for future bid positioning.
        """
        with self._engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT 
                    COALESCE(a.procurement_type, (t.extracted_data->>'procurement_type'), 'Unknown') as category,
                    COALESCE(t.sor_agency, t.procuring_entity, a.agency, 'Unknown') as agency,
                    COUNT(*) as total_awards,
                    AVG((t.estimated_cost - a.award_amount) / NULLIF(t.estimated_cost, 0) * 100) as nppi,
                    AVG(a.award_amount) as avg_award_amount,
                    AVG(t.estimated_cost) as avg_estimate
                FROM awards a
                JOIN tenders t ON a.tender_id = t.tender_id
                WHERE t.estimated_cost > 0 AND a.award_amount > 0
                  AND t.opening_date >= '2025-09-28'
                GROUP BY 1, 2
                HAVING COUNT(*) >= 5  -- Minimum sample size
                ORDER BY total_awards DESC
                LIMIT 200
            """)).fetchall()
            
            results = []
            for r in rows:
                nppi_val = float(r[3]) if r[3] else 0
                entry = {
                    "category": r[0] or "Unknown",
                    "agency": r[1] or "Unknown",
                    "total_awards": r[2],
                    "nppi": round(nppi_val, 2),
                    "avg_award_amount": float(r[4]) if r[4] else 0,
                    "avg_estimate": float(r[5]) if r[5] else 0,
                    "slt_risk": "low" if nppi_val < 8 else "medium" if nppi_val < 12 else "high",
                    "confidence": "high" if r[2] >= 20 else "medium" if r[2] >= 10 else "low"
                }
                results.append(entry)
                
                # Cache individually
                await self._cache_results(f"nppi_{entry['agency']}_{entry['category']}", entry)
            
            logger.info(f"  NPPI: Computed for {len(results)} categories across all agencies")
            return results
    
    async def _analyze_tender(self, tender_id: str, context: Dict) -> Dict:
        """Pre-analyze a specific tender with competitive intelligence."""
        async with get_session() as s:
            # Get tender details
            result = await s.execute(text("""
                SELECT
                    tender_id,
                    COALESCE(sor_agency, procuring_entity, '') AS agency,
                    COALESCE((extracted_data->>'procurement_type'), 'Unknown') AS procurement_type,
                    COALESCE(zone, division, '') AS zone,
                    COALESCE(estimated_cost, 0) AS estimated_cost
                FROM tenders
                WHERE tender_id = :tender_id
            """), {"tender_id": tender_id})
            tender = result.mappings().first()
            
            if not tender:
                return {"status": "not_found", "tender_id": tender_id}
            agency = tender["agency"] or ""
            category = tender["procurement_type"] or "Unknown"
            zone = tender["zone"] or ""
            estimate = float(tender["estimated_cost"] or 0)
            
            # Get SLT for this category/agency
            slt_key = f"slt_{agency}_{category}"
            cached = await self._get_cached(slt_key)
            
            # Get NPPI
            nppi_key = f"nppi_{agency}_{category}"
            nppi_cached = await self._get_cached(nppi_key)
            
            # Get competitors who bid on similar tenders
            comp_result = await s.execute(text("""
                SELECT a.contractor_name, COUNT(*) as bids, 
                       AVG(a.award_amount) as avg_amount,
                       SUM(CASE WHEN a.award_amount > 0 THEN 1 ELSE 0 END) as wins
                FROM awards a
                JOIN tenders t ON a.tender_id = t.tender_id
                WHERE COALESCE(t.sor_agency, t.procuring_entity, '') = :agency 
                  AND a.contractor_name IS NOT NULL 
                  AND a.contractor_name != ''
                GROUP BY a.contractor_name
                ORDER BY bids DESC
                LIMIT 20
            """), {"agency": agency})
            competitors = comp_result.fetchall()
            
            # Estimate expected winning range
            expected_discount = nppi_cached.get("nppi", 5.0) if nppi_cached else 5.0
            expected_win_range = {
                "conservative": round(estimate * (1 - expected_discount / 100 * 0.7), 2),
                "balanced": round(estimate * (1 - expected_discount / 100), 2),
                "aggressive": round(estimate * (1 - expected_discount / 100 * 1.3), 2),
            }
            
            analysis = {
                "tender_id": tender_id,
                "agency": agency,
                "category": category,
                "estimate": estimate,
                "slt": {
                    "expected_discount_pct": cached.get("avg_discount_pct", 5.0) if cached else None,
                    "conservative_pct": cached.get("slt_conservative", 3.5) if cached else None,
                    "aggressive_pct": cached.get("slt_aggressive", 6.5) if cached else None,
                    "sample_size": cached.get("sample_count", 0) if cached else 0
                },
                "nppi": {
                    "value": nppi_cached.get("nppi", None) if nppi_cached else None,
                    "confidence": nppi_cached.get("confidence", "low") if nppi_cached else "low",
                    "slt_risk": nppi_cached.get("slt_risk", "unknown") if nppi_cached else "unknown"
                },
                "expected_winning_range": expected_win_range,
                "competitors": [
                    {
                        "name": c[0],
                        "total_bids": c[1],
                        "avg_amount": float(c[2]) if c[2] else 0,
                        "wins": c[3]
                    }
                    for c in competitors if c[0]
                ],
                "bidder_count": len(competitors),
                "market_concentration": "high" if len(competitors) <= 5 else "medium" if len(competitors) <= 15 else "low",
                "recommendation": self._generate_recommendation(estimate, expected_discount, competitors),
                "pre_computed_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Cache this analysis
            await self._cache_results(f"tender_analysis_{tender_id}", analysis)
            
            return analysis
    
    async def _analyze_live_tenders(self) -> List[Dict]:
        """Pre-analyze all LIVE tenders for instant response."""
        with self._engine.connect() as conn:
            tenders = conn.execute(text(
                "SELECT tender_id "
                "FROM tenders WHERE estimated_cost > 0 LIMIT 500"
            )).fetchall()
        
        results = []
        for t in tenders:
            analysis = await self._analyze_tender(t[0], {})
            if analysis.get("status") != "not_found":
                results.append(analysis)
        
        logger.info(f"  Pre-analyzed {len(results)} tenders")
        return results
    
    def _competitor_moat_analysis(self, tender_id: str, context: Dict) -> Dict:
        """
        Analyze competitive moat — what advantage does each bidder have?
        
        MOAT factors:
          - Agency relationship (past awards from same PE)
          - Zone specialization
          - Category expertise  
          - Pricing aggressiveness
          - Win rate in similar tenders
        """
        with self._engine.connect() as conn:
            # Get tender details
            tender = conn.execute(text(
                "SELECT "
                "  COALESCE(sor_agency, procuring_entity, '') AS agency, "
                "  COALESCE((extracted_data->>'procurement_type'), 'Unknown') AS procurement_type, "
                "  COALESCE(zone, division, '') AS zone, "
                "  COALESCE(estimated_cost, 0) AS estimated_cost "
                "FROM tenders WHERE tender_id = :id"
            ), {"id": tender_id}).fetchone()
            
            if not tender:
                return {"status": "not_found"}
            
            agency = tender[0] or ""
            category = tender[1] or "Unknown"
            zone = tender[2] or ""
            
            # Find all contractors who've worked with this agency
            contractors = conn.execute(text("""
                SELECT 
                    a.contractor_name,
                    COUNT(*) as total_awards,
                    SUM(CASE WHEN a.agency = :agency THEN 1 ELSE 0 END) as agency_awards,
                    SUM(CASE WHEN COALESCE(t.zone, t.division, '') = :zone AND COALESCE(t.zone, t.division, '') != '' THEN 1 ELSE 0 END) as zone_awards,
                    AVG(a.award_amount) as avg_amount,
                    COUNT(DISTINCT a.agency) as agencies_worked
                FROM awards a
                LEFT JOIN tenders t ON a.tender_id = t.tender_id
                WHERE a.contractor_name IS NOT NULL AND a.contractor_name != ''
                GROUP BY a.contractor_name
                HAVING COUNT(*) >= 3
                ORDER BY agency_awards DESC, total_awards DESC
                LIMIT 30
            """), {"agency": agency, "zone": zone}).fetchall()
            
            moat_analysis = []
            for c in contractors:
                total = c[1] or 1
                agency_ratio = (c[2] or 0) / total * 100
                moat_score = min(100, agency_ratio + (c[5] or 0) * 5)
                
                moat_analysis.append({
                    "contractor": c[0],
                    "moat_score": round(moat_score, 1),
                    "agency_loyalty_pct": round(agency_ratio, 1),
                    "total_awards": total,
                    "agency_awards": c[2] or 0,
                    "zone_awards": c[3] or 0,
                    "avg_amount": float(c[4] or 0),
                    "diversification": c[5] or 1,
                    "threat_level": "high" if moat_score > 60 else "medium" if moat_score > 30 else "low"
                })
            
            return {
                "tender_id": tender_id,
                "agency": agency,
                "competitor_count": len(moat_analysis),
                "moat_analysis": sorted(moat_analysis, key=lambda x: x["moat_score"], reverse=True)
            }
    
    def _generate_recommendation(self, estimate: float, expected_discount: float, competitors) -> Dict:
        """Generate bid recommendation based on analysis."""
        comp_count = len([c for c in competitors if c[0]])
        
        if comp_count == 0:
            return {"bid": True, "confidence": "low", "reason": "No competitor data available"}
        
        bid_now = comp_count <= 3
        wait = comp_count > 10
        
        return {
            "bid": bid_now if not wait else "wait",
            "confidence": "high" if comp_count <= 5 else "medium",
            "expected_discount": round(expected_discount, 2),
            "competitors_expected": comp_count,
            "reason": f"{'Low' if bid_now else 'High'} competition ({comp_count} bidders)" if not wait else f"Very high competition ({comp_count}), consider waiting"
        }
    
    async def _get_cached_analysis(self, tender_id: str) -> Dict:
        """Get pre-computed analysis for a tender."""
        cached = await self._get_cached(f"tender_analysis_{tender_id}")
        if cached:
            return cached
        # If not cached, compute on demand
        return await self._analyze_tender(tender_id, {})
    
    async def _cache_results(self, key: str, data: Dict):
        """Cache pre-computed intelligence in database."""
        from app.db.models import PreComputedIntelligence
        from app.db import get_session
        try:
            async with get_session() as s:
                from sqlalchemy import select
                existing = await s.execute(
                    select(PreComputedIntelligence).where(
                        PreComputedIntelligence.cache_key == key
                    )
                )
                entry = existing.scalar_one_or_none()
                if entry:
                    entry.cache_data = data
                    entry.updated_at = datetime.now(timezone.utc)
                else:
                    entry = PreComputedIntelligence(
                        cache_key=key,
                        cache_data=data,
                        intelligence_type=key.split("_")[0],
                    )
                    s.add(entry)
                await s.commit()
        except Exception as e:
            logger.warning(f"Cache error for {key}: {e}")
    
    async def _get_cached(self, key: str) -> Optional[Dict]:
        """Get cached intelligence from database."""
        from app.db.models import PreComputedIntelligence
        from sqlalchemy import select
        from app.db import get_session
        try:
            async with get_session() as s:
                existing = await s.execute(
                    select(PreComputedIntelligence).where(
                        PreComputedIntelligence.cache_key == key
                    )
                )
                entry = existing.scalar_one_or_none()
                return entry.cache_data if entry else None
        except Exception as e:
            logger.warning(f"Cache lookup error for {key}: {e}")
            return None
