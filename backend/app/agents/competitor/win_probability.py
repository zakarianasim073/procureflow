"""
Agent 16 — Win Probability Engine v2
Phase 2: Decision Intelligence Engine

Formula: WinProb = Base × AgencyMatch × ContractorHistory ÷ CompetitionRisk × DiscountPosition

Provides explainable breakdown: each factor contributes a clear percentage.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional
from decimal import Decimal

from app.agents.core.base import BaseAgent, AgentResult, AgentStatus
from app.agents.core.regime import get_regime, regime_weight, get_relevant_discounts
from app.db.database import get_sync_engine
from app.services.ppr_ml_service import get_ppr_ml_service
from sqlalchemy import text

logger = logging.getLogger(__name__)


class WinProbabilityAgent(BaseAgent):
    agent_id = "agent-016-win-probability"
    agent_name = "Win Probability Engine v2"
    description = "Phase 2 Decision Engine: computes win probability with explainable factor breakdown."
    dependencies = ["agent-013-competitor-intelligence", "agent-014-award-intelligence", "agent-036-moat-slt-analyzer"]
    version = "3.0.0"

    BASE_RATE = 0.50  # 50% baseline

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        tender_id = context.get("tender_id", "")
        company = context.get("company_profile", {}) or context.get("company", {})
        bid_amount = self._safe_float(context.get("bid_amount", context.get("quoted_amount", 0)), 0.0)
        estimate = self._safe_float(context.get("estimate", context.get("estimated_amount", 0)), 0.0)
        agency = context.get("agency", "")
        zone = context.get("zone", context.get("division", ""))
        regime = context.get("regime") or get_regime(context.get("tender_open_date") or context.get("opening_date"))

        # Gather intelligence
        kg_scores = await self._score_knowledge_graph(company, agency, zone)
        competitors = await self._assess_competition(tender_id, agency)
        discount_pos = await self._analyze_discount_position(bid_amount, estimate, agency, zone)
        historical = await self._historical_performance(company, agency)
        heuristic_result = self._compute_probability(kg_scores, competitors, discount_pos, historical)
        ml_result = await self._predict_with_ml(
            context={
                **context,
                "agency": agency,
                "zone": zone,
                "regime": regime,
                "estimated_cost": estimate,
                "bid_price": bid_amount,
                "bid_ratio": (bid_amount / estimate) if estimate > 0 else context.get("bid_ratio"),
                "discount_pct": discount_pos.get("our_discount", 0.0),
                "bidder_count": competitors.get("competitor_count", context.get("bidder_count", 1)),
                "bidder_name": company.get("company_name", company.get("name", "")),
                "company_name": company.get("company_name", company.get("name", "")),
                "contractor_history_rows": historical.get("total_bids", 0),
                "contractor_prior_bid_count": historical.get("total_bids", 0),
                "contractor_prior_win_rate": (historical.get("wins", 0) / max(historical.get("total_bids", 1), 1)),
                "evidence_score": self._evidence_score(company, agency, zone, estimate, bid_amount, competitors, historical),
            }
        )
        prob_result = self._blend_results(heuristic_result, ml_result, competitors, historical)

        # Store result
        await self.share_knowledge(
            entry_type="win_probability",
            tender_id=tender_id,
            data=prob_result,
            summary=f"Win Prob: {prob_result['probability']}% for {tender_id}",
            tags=["win-probability", "v2", agency]
        )

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=prob_result
        )

    async def _predict_with_ml(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            service = get_ppr_ml_service()
            prediction = await service.predict_market_row(context)
            if not isinstance(prediction, dict):
                return None
            if not prediction.get("trained") and not prediction.get("win"):
                return None
            return prediction
        except Exception as exc:
            logger.warning("PPR ML win prediction unavailable: %s", exc)
            return None

    def _blend_results(self, heuristic: Dict[str, Any], ml: Optional[Dict[str, Any]], competitors: Dict[str, Any], hist: Dict[str, Any]) -> Dict:
        if not ml or "win" not in ml:
            heuristic["model_source"] = "heuristic_fallback"
            heuristic["evidence_score"] = self._evidence_score_from_heuristic(competitors, hist)
            heuristic["confidence"] = self._refine_confidence(heuristic.get("confidence", "Medium"), heuristic["evidence_score"])
            return heuristic

        ml_prob = self._safe_float(ml.get("win", {}).get("probability", 0.0), 0.0)
        ml_pct = ml_prob * 100.0 if ml_prob <= 1.0 else ml_prob
        heur_pct = self._safe_float(heuristic.get("probability", 0.0), 0.0)
        blended = (0.70 * ml_pct) + (0.30 * heur_pct)
        factors = self._merge_factors(
            ml.get("win", {}).get("factors", []),
            heuristic.get("factors", []),
            ml.get("explanation", {}),
        )
        evidence_score = self._safe_float(ml.get("evidence", {}).get("evidence_score", 0.0), 0.0)
        if evidence_score <= 0:
            evidence_score = self._evidence_score_from_heuristic(competitors, hist)
        confidence = ml.get("win", {}).get("confidence") or heuristic.get("confidence", "Medium")
        confidence = self._refine_confidence(str(confidence), evidence_score, abs(ml_pct - heur_pct))
        recommendations = list(dict.fromkeys(
            (ml.get("explanation", {}) or {}).get("summary", "").split("\n")
            if isinstance((ml.get("explanation", {}) or {}).get("summary", ""), str)
            else []
        ))
        recommendations.extend(heuristic.get("recommendations", []))
        recommendations = [r for r in recommendations if r]
        return {
            "probability": round(max(5.0, min(95.0, blended)), 1),
            "confidence": confidence,
            "model_source": ml.get("model_version", "ppr_ml_service"),
            "ml_probability": round(ml_pct, 1),
            "heuristic_probability": heur_pct,
            "evidence_score": round(evidence_score, 3),
            "factors": factors,
            "formula": heuristic.get("formula", "Hybrid calibrated ML + heuristic blend"),
            "base_rate": heuristic.get("base_rate", 50.0),
            "total_adjustment": heuristic.get("total_adjustment", 0.0),
            "recommendations": recommendations[:5] if recommendations else heuristic.get("recommendations", []),
            "explanation": ml.get("explanation", {}),
            "slt": ml.get("slt", {}),
            "win_raw": ml.get("win", {}),
            "heuristic_signal": heuristic,
            "model_signal": ml,
        }

    def _merge_factors(self, ml_factors: Any, heuristic_factors: List[Dict[str, Any]], explanation: Dict[str, Any]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        for factor in ml_factors or []:
            if isinstance(factor, dict):
                name = str(factor.get("feature") or factor.get("name") or "Model factor").replace("_", " ")
                impact = self._safe_float(factor.get("impact_logit", factor.get("impact", 0.0)), 0.0)
                score = self._safe_float(factor.get("score", factor.get("value", 0.0)), 0.0)
                detail = factor.get("direction") or factor.get("detail") or factor.get("reason") or "Model contribution"
                merged.append({
                    "name": name.title(),
                    "impact": round(impact, 2),
                    "score": round(score, 2),
                    "detail": str(detail),
                    "source": "ml",
                })
            else:
                merged.append({
                    "name": "Model factor",
                    "impact": 0.0,
                    "score": 0.0,
                    "detail": str(factor),
                    "source": "ml",
                })

        for factor in heuristic_factors or []:
            if not isinstance(factor, dict):
                continue
            merged.append({
                "name": str(factor.get("name", "Heuristic factor")),
                "impact": self._safe_float(factor.get("impact", 0.0), 0.0),
                "score": self._safe_float(factor.get("score", 0.0), 0.0),
                "detail": str(factor.get("detail", "")),
                "source": "heuristic",
            })

        summary = explanation.get("summary") if isinstance(explanation, dict) else ""
        if summary:
            merged.insert(0, {"name": "Explanation", "impact": 0.0, "score": 0.0, "detail": str(summary), "source": "ml"})
        return merged[:8]

    def _evidence_score(self, company: Dict[str, Any], agency: str, zone: str, estimate: float, bid_amount: float, competitors: Dict[str, Any], hist: Dict[str, Any]) -> float:
        score = 0.25
        if company.get("company_name") or company.get("name"):
            score += 0.15
        if agency:
            score += 0.10
        if zone:
            score += 0.05
        if estimate > 0:
            score += 0.10
        if bid_amount > 0:
            score += 0.10
        if competitors.get("competitor_count", 0):
            score += 0.10
        if hist.get("total_bids", 0):
            score += min(0.15, hist.get("total_bids", 0) / 40.0)
        return round(min(1.0, score), 3)

    def _evidence_score_from_heuristic(self, competitors: Dict[str, Any], hist: Dict[str, Any]) -> float:
        score = 0.35
        if competitors.get("competitor_count", 0):
            score += min(0.25, competitors.get("competitor_count", 0) / 20.0)
        if hist.get("total_bids", 0):
            score += min(0.25, hist.get("total_bids", 0) / 40.0)
        if hist.get("wins", 0):
            score += min(0.15, hist.get("wins", 0) / 20.0)
        return round(min(1.0, score), 3)

    def _refine_confidence(self, confidence: str, evidence_score: float, disagreement: float = 0.0) -> str:
        confidence = str(confidence or "Medium").title()
        if evidence_score >= 0.72 and disagreement <= 12:
            return "High"
        if evidence_score >= 0.50 and disagreement <= 18:
            return "Medium"
        if confidence.lower() == "high" and disagreement <= 20:
            return "Medium"
        return "Low"

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default

    async def _score_knowledge_graph(self, company: Dict, agency: str, zone: str) -> Dict:
        """Score company against agency/zone from Knowledge Graph."""
        scores = {"agency_match": 1.0, "zone_match": 1.0, "contractor_history": 1.0}
        
        company_name = company.get("company_name", company.get("name", ""))
        if not company_name or not agency:
            return scores
        
        try:
            engine = get_sync_engine()
            with engine.connect() as conn:
                # Agency relationship score
                agency_awards = conn.execute(text(
                    "SELECT COUNT(*) FROM awards WHERE agency = :agency AND contractor_name LIKE :name"
                ), {"agency": agency, "name": f"%{company_name[:20]}%"}).fetchone()
                
                prior_awards = agency_awards[0] if agency_awards else 0
                # Scale: 0 awards = 0.7, 1-2 = 0.85, 3-5 = 1.0, 6+ = 1.15
                if prior_awards == 0:
                    scores["agency_match"] = 0.70
                elif prior_awards <= 2:
                    scores["agency_match"] = 0.85
                elif prior_awards <= 5:
                    scores["agency_match"] = 1.00
                else:
                    scores["agency_match"] = 1.15
                
                # Zone match
                if zone:
                    zone_awards = conn.execute(text(
                        "SELECT COUNT(*) FROM awards a "
                        "JOIN tenders t ON a.tender_id = t.tender_id "
                        "WHERE t.division = :zone AND a.contractor_name LIKE :name"
                    ), {"zone": zone, "name": f"%{company_name[:20]}%"}).fetchone()
                    zone_count = zone_awards[0] if zone_awards else 0
                    scores["zone_match"] = 0.80 if zone_count == 0 else min(1.20, 0.80 + zone_count * 0.08)
                
                # Contractor history - years active
                years = company.get("experience_years", company.get("years_in_business", 5))
                scores["contractor_history"] = min(1.20, 0.70 + years * 0.02)
                
        except Exception as e:
            logger.warning(f"KG scoring error: {e}")
        
        return scores

    async def _assess_competition(self, tender_id: str, agency: str) -> Dict:
        """Assess competition level and intensity."""
        result = {"competition_risk": 1.0, "competitor_count": 0, "syndicate_risk": False}
        
        try:
            engine = get_sync_engine()
            with engine.connect() as conn:
                # Get competitor count from opening reports for similar tenders
                if agency:
                    count_row = conn.execute(text(
                        "SELECT AVG(json_array_length(bidders)) FROM opening_reports "
                        "WHERE pe_office LIKE :agency AND bidders IS NOT NULL LIMIT 20"
                    ), {"agency": f"%{agency}%"}).fetchone()
                    avg_competitors = float(count_row[0]) if count_row and count_row[0] else 5
                else:
                    avg_competitors = 5
                
                result["competitor_count"] = int(avg_competitors)
                
                # Competition risk: fewer competitors = lower risk
                if avg_competitors <= 3:
                    result["competition_risk"] = 0.70
                elif avg_competitors <= 5:
                    result["competition_risk"] = 0.85
                elif avg_competitors <= 8:
                    result["competition_risk"] = 1.00
                elif avg_competitors <= 12:
                    result["competition_risk"] = 1.15
                else:
                    result["competition_risk"] = 1.30
                
        except Exception as e:
            logger.warning(f"Competition assessment error: {e}")
        
        return result

    async def _analyze_discount_position(self, bid_amount: float, estimate: float, 
                                          agency: str, zone: str) -> Dict:
        """Analyze how bid discount compares to market norms."""
        result = {"discount_factor": 1.0, "market_discount": 5.0, "our_discount": 0.0}
        
        if not estimate or estimate <= 0:
            return result
        
        our_discount = ((estimate - bid_amount) / estimate * 100) if bid_amount > 0 else 5.0
        result["our_discount"] = round(our_discount, 2)
        
        try:
            engine = get_sync_engine()
            with engine.connect() as conn:
                # Get market average discount
                nppi_row = conn.execute(text(
                    "SELECT AVG(lowest_percent_below_oe) FROM npp_records WHERE agency = :agency LIMIT 10"
                ), {"agency": agency}).fetchone() if agency else None
                
                market_discount = float(nppi_row[0]) if nppi_row and nppi_row[0] else 5.5
                result["market_discount"] = round(market_discount, 1)
                
                # Discount position relative to market
                ratio = our_discount / market_discount if market_discount > 0 else 1.0
                if ratio < 0.5:  # Very conservative
                    result["discount_factor"] = 0.80
                elif ratio < 0.8:  # Slightly conservative
                    result["discount_factor"] = 0.90
                elif ratio < 1.2:  # On market
                    result["discount_factor"] = 1.00
                elif ratio < 1.5:  # Aggressive
                    result["discount_factor"] = 1.10
                else:  # Very aggressive - may be risky
                    result["discount_factor"] = 0.95
                    
        except Exception as e:
            logger.warning(f"Discount analysis error: {e}")
        
        return result

    async def _historical_performance(self, company: Dict, agency: str) -> Dict:
        """Score historical win rate for this contractor."""
        result = {"win_rate": 1.0, "total_bids": 0, "wins": 0}
        
        company_name = company.get("company_name", company.get("name", ""))
        if not company_name:
            return result
        
        try:
            engine = get_sync_engine()
            with engine.connect() as conn:
                award_count = conn.execute(text(
                    "SELECT COUNT(*) FROM awards WHERE contractor_name LIKE :name"
                ), {"name": f"%{company_name[:20]}%"}).fetchone()
                
                result["wins"] = award_count[0] if award_count else 0
                result["total_bids"] = max(result["wins"] * 3, 10)  # estimate
                
                # Win rate factor
                if result["wins"] > 10:
                    result["win_rate"] = 1.15
                elif result["wins"] > 5:
                    result["win_rate"] = 1.05
                elif result["wins"] > 2:
                    result["win_rate"] = 0.95
                else:
                    result["win_rate"] = 0.80
                    
        except Exception as e:
            logger.warning(f"Historical performance error: {e}")
        
        return result

    def _compute_probability(self, kg: Dict, comp: Dict, disc: Dict, hist: Dict) -> Dict:
        """
        Win Probability = BaseRate × AgencyMatch × ContractorHistory 
                         ÷ CompetitionRisk × DiscountPosition
        """
        base = self.BASE_RATE
        agency_match = kg.get("agency_match", 1.0)
        zone_match = kg.get("zone_match", 1.0)
        contractor_history = kg.get("contractor_history", 1.0)
        competition_risk = comp.get("competition_risk", 1.0)
        discount_factor = disc.get("discount_factor", 1.0)
        win_rate = hist.get("win_rate", 1.0)

        # Compute
        raw_prob = base * agency_match * zone_match * contractor_history * win_rate / competition_risk * discount_factor
        probability = max(5, min(95, round(raw_prob * 100, 1)))

        # Factor breakdown
        factors = [
            {
                "name": "Agency Match",
                "impact": round((agency_match - 1.0) * 100, 1),
                "score": round(agency_match, 2),
                "detail": f"{'+' if agency_match > 1.0 else ''}{round((agency_match-1.0)*100, 1)}% from agency relationship"
            },
            {
                "name": "Zone Match",
                "impact": round((zone_match - 1.0) * 100, 1),
                "score": round(zone_match, 2),
                "detail": f"{'+' if zone_match > 1.0 else ''}{round((zone_match-1.0)*100, 1)}% from zone presence"
            },
            {
                "name": "Contractor History",
                "impact": round((contractor_history - 1.0) * 100, 1),
                "score": round(contractor_history, 2),
                "detail": f"{'+' if contractor_history > 1.0 else ''}{round((contractor_history-1.0)*100, 1)}% from track record"
            },
            {
                "name": "Win Rate",
                "impact": round((win_rate - 1.0) * 100, 1),
                "score": round(win_rate, 2),
                "detail": f"{hist['wins']} previous awards"
            },
            {
                "name": "Competition Risk",
                "impact": round((1.0 - competition_risk) * 100, 1),
                "score": round(competition_risk, 2),
                "detail": f"{comp['competitor_count']} avg competitors ({'-' if competition_risk > 1.0 else '+'}{round(abs(1.0-competition_risk)*100, 1)}%)"
            },
            {
                "name": "Discount Position",
                "impact": round((discount_factor - 1.0) * 100, 1),
                "score": round(discount_factor, 2),
                "detail": f"Our {disc['our_discount']}% vs market {disc['market_discount']}%"
            }
        ]

        total_impact = sum(f["impact"] for f in factors)
        confidence = "High" if abs(total_impact) < 30 else "Medium" if abs(total_impact) < 50 else "Low"

        return {
            "probability": probability,
            "confidence": confidence,
            "formula": "Base(50%) × AgencyMatch × ZoneMatch × History × WinRate ÷ CompetitionRisk × DiscountPos",
            "base_rate": self.BASE_RATE * 100,
            "factors": factors,
            "total_adjustment": round(total_impact, 1),
            "engine_version": "v2.0",
            "recommendations": self._generate_recommendations(probability, factors, hist, comp)
        }

    def _generate_recommendations(self, prob: float, factors: List, hist: Dict, comp: Dict) -> List:
        recs = []
        if prob < 40:
            recs.append("Bid only if strategic (low win probability)")
            recs.append("Consider more aggressive discount to improve position")
        elif prob < 60:
            recs.append("Bid competitively with balanced discount")
            recs.append("Focus on qualification strengths in technical proposal")
        else:
            recs.append("Strong position — bid confidently")
            recs.append("Optimize for margin, not just winning")
        
        return recs
