"""
Agent 26 — Learning Agent
Analyzes historical outcomes and continuously improves agent predictions based on past results.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class LearningAgent(BaseAgent):
    agent_id = "agent-026-learning"
    agent_name = "Learning Agent"
    description = "Analyzes historical bid outcomes and agent predictions to continuously improve accuracy and recommendations."
    dependencies: List[str] = ["agent-025-knowledge-lake"]
    version = "2.0.0"

    def __init__(self):
        super().__init__()

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        action = context.get("action", "analyze")
        outcome_data = context.get("outcome_data", {})
        historical_results = context.get("historical_results", [])

        if action == "record_outcome":
            learning = await self._record_outcome(outcome_data)
        elif action == "analyze":
            learning = await self._analyze_patterns(historical_results)
        elif action == "improve":
            learning = await self._generate_improvements()
        else:
            learning = {"error": f"Unknown action: {action}"}

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=learning,
        )

    async def _record_outcome(self, outcome: Dict) -> Dict:
        """Record an actual bid outcome for future learning."""
        from app.db.base import get_session_factory
        from app.models.intelligence import LearningOutcome
        import uuid

        actual_outcome = "WON" if outcome.get("won") else "LOST" if outcome.get("submitted") else "NOT_SUBMITTED"
        
        record = LearningOutcome(
            id=str(uuid.uuid4()),
            tender_id=outcome.get("tender_id", "unknown"),
            submitted=bool(outcome.get("submitted", False)),
            won=bool(outcome.get("won", False)),
            our_bid_amount=float(outcome.get("our_bid_amount", outcome.get("our_bid", 0))),
            lert_amount=float(outcome.get("lert_amount", 0)),
            our_discount_pct=float(outcome.get("our_discount_pct", outcome.get("our_discount", 0))),
            predicted_win_probability=float(outcome.get("predicted_win_probability", 0)),
            actual_outcome=actual_outcome,
            recorded_at=datetime.utcnow()
        )
        
        sf = get_session_factory()
        async with sf() as session:
            session.add(record)
            await session.commit()
            
            # count total
            from sqlalchemy import func, select
            stmt = select(func.count(LearningOutcome.id))
            res = await session.execute(stmt)
            total_count = res.scalar() or 0
        
        return {
            "status": "recorded",
            "outcome": actual_outcome,
            "total_outcomes_recorded": total_count,
        }

    async def _analyze_patterns(self, historical: List[Dict]) -> Dict:
        """Analyze historical outcomes to identify patterns and insights."""
        outcomes = await self._load_outcomes()
        
        if not outcomes:
            return {
                "status": "insufficient_data",
                "message": "Need outcome records for meaningful analysis",
                "current_records": 0,
                "required": 5,
            }
        
        total = len(outcomes)
        won = sum(1 for o in outcomes if o.get("won"))
        lost = total - won
        win_rate = (won / total * 100) if total > 0 else 0
        
        # Discount analysis
        avg_discount_when_won = sum(o.get("our_discount", 0) for o in outcomes if o.get("won")) / max(won, 1)
        avg_discount_when_lost = sum(o.get("our_discount", 0) for o in outcomes if not o.get("won")) / max(lost, 1)
        
        # Probability prediction accuracy
        if total > 0:
            accuracy = sum(
                1 for o in outcomes
                if (o.get("won") and o.get("predicted_win_probability", 0) >= 50) or
                   (not o.get("won") and o.get("predicted_win_probability", 0) < 50)
            ) / total * 100
        else:
            accuracy = 0
        
        return {
            "status": "analyzed",
            "total_outcomes": total,
            "win_rate": round(win_rate, 1),
            "total_wins": won,
            "total_losses": lost,
            "avg_discount_when_won": round(avg_discount_when_won, 2),
            "avg_discount_when_lost": round(avg_discount_when_lost, 2),
            "prediction_accuracy_pct": round(accuracy, 1),
            "insights": self._generate_insights(win_rate, avg_discount_when_won, avg_discount_when_lost),
        }

    async def _generate_improvements(self) -> Dict:
        """Generate improvement recommendations based on learning."""
        outcomes = await self._load_outcomes()
        
        if len(outcomes) < 3:
            return {
                "status": "need_more_data",
                "improvements": [],
                "note": "Collect more outcome data for actionable improvements",
            }
        
        won = [o for o in outcomes if o.get("won")]
        lost = [o for o in outcomes if not o.get("won")]
        
        improvements = []
        
        if lost and won:
            avg_win_discount = sum(o.get("our_discount", 0) for o in won) / len(won)
            avg_lose_discount = sum(o.get("our_discount", 0) for o in lost) / len(lost)
            
            if avg_win_discount > avg_lose_discount:
                improvements.append(f"Competitive discounts ({avg_win_discount:.1f}%) correlate with wins — maintain aggressive pricing")
            else:
                improvements.append(f"Higher discounts ({avg_lose_discount:.1f}%) correlate with losses — consider value-based pricing")
        
        if len(won) >= 1:
            improvements.append("Focus on tenders with similar characteristics to past wins")
        
        return {
            "status": "improvements_generated",
            "improvements": improvements,
            "total_outcomes_analyzed": len(outcomes),
        }

    async def _load_outcomes(self) -> List[Dict]:
        """Load historical outcome records."""
        from app.db.base import get_session_factory
        from app.models.intelligence import LearningOutcome
        from sqlalchemy import select

        sf = get_session_factory()
        async with sf() as session:
            stmt = select(LearningOutcome).order_by(LearningOutcome.recorded_at.desc())
            res = await session.execute(stmt)
            records = res.scalars().all()
            
        outcomes = []
        for r in records:
            outcomes.append({
                "tender_id": r.tender_id,
                "submitted": r.submitted,
                "won": r.won,
                "our_bid": r.our_bid_amount,
                "lert_amount": r.lert_amount,
                "our_discount": r.our_discount_pct,
                "predicted_win_probability": r.predicted_win_probability,
                "actual_outcome": r.actual_outcome,
                "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
            })
        return outcomes

    async def _count_outcomes(self) -> int:
        """Count total outcome records."""
        from app.db.base import get_session_factory
        from app.models.intelligence import LearningOutcome
        from sqlalchemy import func, select

        sf = get_session_factory()
        async with sf() as session:
            stmt = select(func.count(LearningOutcome.id))
            res = await session.execute(stmt)
            return res.scalar() or 0

    def _generate_insights(self, win_rate: float, avg_discount_won: float, avg_discount_lost: float) -> List[str]:
        """Generate human-readable insights from analysis."""
        insights = []
        
        if win_rate >= 60:
            insights.append(f"Strong win rate ({win_rate:.0f}%) — strategy is working well")
        elif win_rate >= 40:
            insights.append(f"Moderate win rate ({win_rate:.0f}%) — room for improvement")
        else:
            insights.append(f"Low win rate ({win_rate:.0f}%) — consider strategy adjustment")
        
        if avg_discount_won and avg_discount_lost:
            diff = avg_discount_won - avg_discount_lost
            if diff > 2:
                insights.append(f"Aggressive discounting ({diff:.1f}% higher when winning) may be key differentiator")
            elif diff < -2:
                insights.append(f"Conservative discounts working better ({abs(diff):.1f}% lower when winning)")
            else:
                insights.append(f"Discount rate not a significant differentiator in outcomes")
        
        return insights
