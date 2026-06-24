"""
Procurement Flow Specialist BD — Joint Venture (JV) Matchmaker
Finds optimal JV partners based on complementary licenses, experience, and past collaborations.
Bangladesh-specific: LGED/RHD/PWD license categories, district presence, financial capacity.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger("procureflow.jv_matchmaker")


@dataclass
class JVProposal:
    """A proposed Joint Venture match."""
    primary_firm: str
    partner_firm: str
    match_score: float = 0.0
    strengths: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    work_share_pct: int = 50  # 50-50 default
    risk_level: str = "low"


class JVMatchmaker:
    """
    Matches contractors for Joint Ventures based on:
    - License categories (LGED A/B/C, RHD, PWD, etc.)
    - District presence overlap/complement
    - Past collaboration history
    - Financial capacity (turnover, working capital)
    - Work type specialization
    """

    def __init__(self):
        self.jv_history: Dict[str, List[str]] = {}  # firm -> list of past JV partners

    async def find_partners(self, primary_firm: Dict[str, Any],
                              candidate_pool: List[Dict[str, Any]],
                              tender_requirements: Dict[str, Any]) -> List[JVProposal]:
        """
        Find best JV partners for a specific tender.
        
        Args:
            primary_firm: Profile of the primary bidder
            candidate_pool: List of potential partner profiles
            tender_requirements: What the tender needs (licenses, districts, etc.)
        
        Returns:
            Ranked list of JV proposals
        """
        proposals = []
        
        for candidate in candidate_pool:
            if candidate.get("name") == primary_firm.get("name"):
                continue  # Skip self
            
            proposal = await self._evaluate_partner(primary_firm, candidate, tender_requirements)
            proposals.append(proposal)
        
        # Sort by match score descending
        proposals.sort(key=lambda p: p.match_score, reverse=True)
        return proposals[:10]  # Top 10

    async def _evaluate_partner(self, primary: Dict, partner: Dict, 
                                  tender_reqs: Dict) -> JVProposal:
        """Evaluate a single partner for JV suitability."""
        strengths = []
        gaps = []
        score = 0.0
        
        p_name = primary.get("name", "Unknown")
        partner_name = partner.get("name", "Unknown")
        
        # 1. License complementarity (max 25 pts)
        p_licenses = set(primary.get("licenses", []))
        partner_licenses = set(partner.get("licenses", []))
        required_licenses = set(tender_reqs.get("required_licenses", []))
        
        combined = p_licenses | partner_licenses
        license_coverage = len(combined & required_licenses) / max(len(required_licenses), 1)
        score += license_coverage * 25
        
        if license_coverage >= 0.8:
            strengths.append(f"Combined licenses cover {license_coverage:.0%} of requirements")
        
        missing = required_licenses - combined
        if missing:
            gaps.append(f"Still missing licenses: {', '.join(missing)}")
        
        # 2. District presence complementarity (max 20 pts)
        p_districts = set(primary.get("districts", []))
        partner_districts = set(partner.get("districts", []))
        target_district = tender_reqs.get("district", "")
        
        if target_district in p_districts or target_district in partner_districts:
            score += 20
            strengths.append(f"Presence in target district: {target_district}")
        elif p_districts & partner_districts:
            overlap = len(p_districts & partner_districts)
            score += min(overlap * 2, 10)
            strengths.append(f"Combined presence in {overlap} shared districts")
        else:
            total_districts = len(p_districts | partner_districts)
            score += min(total_districts * 1.5, 10)
            strengths.append(f"Combined reach: {total_districts} districts")
        
        # 3. Financial complementarity (max 20 pts)
        p_turnover = primary.get("annual_turnover", 0) or 0
        partner_turnover = partner.get("annual_turnover", 0) or 0
        combined_turnover = p_turnover + partner_turnover
        required_turnover = tender_reqs.get("required_turnover", 0) or 0
        
        if required_turnover > 0:
            turnover_ratio = combined_turnover / required_turnover
            score += min(turnover_ratio * 10, 20)
            if turnover_ratio >= 1.5:
                strengths.append(f"Combined turnover ৳{combined_turnover:,.0f} exceeds requirement")
            elif turnover_ratio < 1:
                gaps.append(f"Combined turnover still below requirement by ৳{required_turnover - combined_turnover:,.0f}")
        
        # 4. Past collaboration (max 15 pts)
        p_history = self.jv_history.get(p_name, [])
        if partner_name in p_history:
            score += 15
            strengths.append("Successful JV collaboration history")
        
        # 5. Work type specialization (max 10 pts)
        p_work = set(primary.get("work_types", [])) if primary.get("work_types") else set()
        partner_work = set(partner.get("work_types", [])) if partner.get("work_types") else set()
        all_work = p_work | partner_work
        if all_work:
            score += min(len(all_work) * 2, 10)
        
        # 6. Size compatibility (max 10 pts)
        p_size = p_turnover or 1
        partner_size = partner_turnover or 1
        size_ratio = min(p_size, partner_size) / max(p_size, partner_size, 1)
        if size_ratio > 0.3:
            score += size_ratio * 10
        else:
            gaps.append("Significant size mismatch between firms")
        
        # Determine work share
        work_share = 50
        if p_turnover > 0 and partner_turnover > 0:
            work_share = int((p_turnover / (p_turnover + partner_turnover)) * 100)
            work_share = max(30, min(70, work_share))  # Clamp between 30-70
        
        # Risk level
        if score < 40:
            risk = "high"
        elif score < 60:
            risk = "medium"
        else:
            risk = "low"
        
        return JVProposal(
            primary_firm=p_name,
            partner_firm=partner_name,
            match_score=round(score, 1),
            strengths=strengths,
            gaps=gaps,
            work_share_pct=work_share,
            risk_level=risk,
        )


jv_matchmaker = JVMatchmaker()
