"""
Meta-Allocator — Multi-client conflict resolution & priority scoring.
Layer 3: Given one tender and multiple clients, allocates recommendation sharpness.
"""
from __future__ import annotations
import logging, uuid
from typing import Any, Dict, List, Optional
from app.db.database import get_sync_engine, get_sync_session
from app.db.models import ClientPriorityState

logger = logging.getLogger(__name__)


class MetaAllocator:
    """
    For a single tender, evaluates all interested clients and produces:
    - Priority tier per client (HIGH / MEDIUM / LOW)
    - Normalized recommendation sharpness
    - Conflict warnings when multiple clients target same tender
    
    Output to each client is SANITIZED — ranges not exact numbers.
    """

    def __init__(self):
        self._engine = get_sync_engine()

    def evaluate_clients(self, tender_id: str, 
                          client_profiles: List[Dict]) -> List[Dict]:
        """
        Evaluate multiple clients for one tender.
        Returns priority-ordered list with sanitized recommendations.
        """
        if not client_profiles:
            return []

        n_clients = len(client_profiles)
        results = []

        for profile in client_profiles:
            priority = self._compute_priority(profile)
            results.append({
                "tenant_id": profile.get("tenant_id", ""),
                "company_name": profile.get("company_name", "Unknown"),
                "priority_score": priority["score"],
                "priority_tier": priority["tier"],
                "workload_score": priority["workload"],
                "need_score": priority["need"],
                "financial_headroom": profile.get("financial_headroom", 0),
            })

        # Sort by priority score descending
        results.sort(key=lambda r: r["priority_score"], reverse=True)

        # Adjust sharpness based on competition among our clients
        high_priority = [r for r in results if r["priority_tier"] == "HIGH"]
        if len(high_priority) > 1:
            # Multiple high-priority clients want same tender — conflict!
            for r in results:
                r["conflict_warning"] = True
                if r["priority_tier"] == "HIGH":
                    r["recommendation_sharpness"] = "standard"
                else:
                    r["recommendation_sharpness"] = "conservative"
        else:
            for r in results:
                r["conflict_warning"] = False
                if r["priority_tier"] == "HIGH":
                    r["recommendation_sharpness"] = "aggressive"
                elif r["priority_tier"] == "MEDIUM":
                    r["recommendation_sharpness"] = "standard"
                else:
                    r["recommendation_sharpness"] = "conservative"

        return results

    def _compute_priority(self, profile: Dict) -> Dict:
        """Compute priority tier for a single client on a tender."""
        score = 50  # baseline
        workload = profile.get("running_projects_count", 0)
        need = profile.get("need_for_work_score", 50)
        headroom = profile.get("financial_headroom", 0)
        agency_match = len(profile.get("preferred_agencies", [])) > 0

        # Workload: less busy = higher priority to win
        if workload <= 2: score += 15
        elif workload >= 8: score -= 25
        elif workload >= 5: score -= 10

        # Need: higher need = higher priority
        score += (need - 50) * 0.3

        # Agency match bonus
        if agency_match: score += 10

        # Financial headroom: tight = higher priority (needs cash flow)
        if headroom <= 5000000: score += 10
        elif headroom >= 100000000: score -= 5

        # Determine tier
        if score >= 65:
            tier = "HIGH"
        elif score >= 40:
            tier = "MEDIUM"
        else:
            tier = "LOW"

        return {"score": max(0, min(100, int(score))), "tier": tier,
                "workload": workload, "need": need}

    def sanitize_output(self, raw_output: Dict, priority_tier: str, 
                         sharpness: str) -> Dict:
        """
        Sanitize agent output: convert exact numbers to ranges.
        This protects IP and avoids over-trusting one magic number.
        """
        sanitized = {}

        # Win probability → range
        wp = raw_output.get("probability", raw_output.get("win_probability", 50))
        sanitized["win_probability_range"] = self._to_range(wp, sharpness, spread=8)

        # Discount → range
        discount = raw_output.get("optimal_discount", {}).get("percentage",
                   raw_output.get("discount_pct", raw_output.get("recommended_discount", 5)))
        if isinstance(discount, dict):
            discount = discount.get("percentage", 5)
        sanitized["recommended_discount_range"] = self._to_range(discount, sharpness, spread=1.0)

        # Margin → range
        margin = raw_output.get("optimal_discount", {}).get("expected_margin",
                raw_output.get("estimated_margin_pct", raw_output.get("expected_margin", 10)))
        if isinstance(margin, dict):
            margin = margin.get("expected_margin", 10)
        sanitized["expected_margin_range"] = self._to_range(margin, sharpness, spread=3)

        # Bidders → range (from competitor analysis)
        bidders = raw_output.get("competitor_count", raw_output.get("num_competitors", 
                 raw_output.get("avg_competitors", 5)))
        sanitized["expected_bidder_range"] = self._to_range(float(bidders), sharpness, spread=2, is_int=True)

        # Decision
        decision = raw_output.get("decision", raw_output.get("recommendation", 
                  raw_output.get("status", "review")))
        sanitized["recommendation"] = self._tiered_recommendation(decision, priority_tier, sharpness)

        return sanitized

    def _to_range(self, value: float, sharpness: str, spread: float = 5, 
                   is_int: bool = False) -> Dict:
        """Convert a point estimate to a range."""
        if sharpness == "aggressive":
            low = value - spread * 0.2
            high = value + spread * 0.2
        elif sharpness == "standard":
            low = value - spread * 0.5
            high = value + spread * 0.5
        else:  # conservative
            low = value - spread * 0.8
            high = value + spread * 0.8

        if is_int:
            low = max(1, int(round(low)))
            high = max(low + 1, int(round(high)))
            return {"min": low, "max": high, "estimated": int(round(value))}
        else:
            low = max(0, round(low, 1))
            high = max(low + 0.1, round(high, 1))
            return {"min": low, "max": high, "estimated": round(value, 1)}

    def _tiered_recommendation(self, decision: str, priority_tier: str, 
                                sharpness: str) -> str:
        """Generate human recommendation based on priority."""
        decision = str(decision).upper()

        if priority_tier == "HIGH" and sharpness == "aggressive":
            if "BID" in decision or "AGGRESSIVE" in decision:
                return "STRONGLY RECOMMENDED — bid aggressively within range"
            return "CONSIDER — review risk factors carefully"
        elif priority_tier == "MEDIUM":
            return "CONSIDER BID — review your capacity before deciding"
        elif priority_tier == "LOW":
            if "NO-BID" in decision:
                return "RECOMMENDED: DO NOT BID — focus on higher-priority opportunities"
            return "CAUTION — your current workload suggests reviewing capacity first"
        return "REVIEW"

    def persist_priority(self, tenant_id: str, tender_id: str, 
                          evaluation: Dict) -> str:
        """Store priority evaluation in database."""
        session = get_sync_session()
        try:
            entry = ClientPriorityState(
                tenant_id=tenant_id, tender_id=tender_id,
                priority_score=evaluation.get("priority_score", 50),
                priority_tier=evaluation.get("priority_tier", "MEDIUM"),
                workload_score=evaluation.get("workload_score", 0),
                need_for_work_score=evaluation.get("need_score", 50),
                financial_headroom=evaluation.get("financial_headroom", 0),
                recommendation=evaluation.get("recommendation_sharpness", "standard"),
                advice_summary=evaluation.get("advice_summary", ""),
            )
            session.add(entry); session.commit()
            return entry.id
        except Exception as e:
            session.rollback(); logger.error(f"Persist priority error: {e}")
            return ""
        finally:
            session.close()


_meta_allocator = None
def get_meta_allocator() -> MetaAllocator:
    global _meta_allocator
    if _meta_allocator is None: _meta_allocator = MetaAllocator()
    return _meta_allocator
