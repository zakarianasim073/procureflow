"""
Learning Agent — Continuous Learning from Procurement Outcomes.
Analyzes historical data to improve agent performance over time.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from collections import defaultdict

from app.agents.core.base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class LearningAgent(BaseAgent):
    agent_id = "agent-026-learning"
    agent_name = "Learning Agent"
    description = "Continuous learning from procurement outcomes"
    dependencies: List[str] = ["agent-025-knowledge-lake"]
    version = "2.0.0"

    def __init__(self, brain=None):
        super().__init__(brain)
        self._feedback_store: List[Dict] = []
        self._accuracy_tracker: Dict[str, List[bool]] = defaultdict(list)
        self._pattern_store: Dict[str, Dict] = {}

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        action = context.get("action", "analyze")
        result = None
        
        if action == "analyze":
            result = await self._analyze_outcomes(context)
        elif action == "record_feedback":
            result = await self._record_feedback(context)
        elif action == "get_accuracy":
            result = await self._get_accuracy()
        elif action == "learn_from_history":
            result = await self._learn_from_history(context)
        elif action == "recommend_improvements":
            result = await self._recommend_improvements(context)
        else:
            result = AgentResult(status=AgentStatus.SUCCESS, output={"action": action, "status": "unknown_action"})
        
        # Broadcast learnings to ALL agents after any analysis completes
        if self.brain and result and result.status == AgentStatus.SUCCESS:
            output = result.output if isinstance(result.output, dict) else {}
            learnings = output.get("learnings") or output.get("improvements") or output.get("lessons")
            if learnings:
                await self.brain.broadcast(
                    sender_id=self.agent_id,
                    subject="new_learnings",
                    body={
                        "learnings": learnings,
                        "tender_id": context.get("tender_id", ""),
                        "action": action,
                        "agent": self.agent_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
                logger.info(f"📢 LearningAgent broadcast: {len(learnings) if isinstance(learnings, list) else 1} learnings shared")
        
        return result if result else AgentResult(status=AgentStatus.SUCCESS, output={"status": "done"})

    async def _analyze_outcomes(self, context: Dict) -> AgentResult:
        """Analyze procurement outcomes vs predictions."""
        tender_id = context.get("tender_id", "")
        predicted = context.get("predicted", {})
        actual = context.get("actual", {})
        
        if not predicted and not tender_id:
            return AgentResult(status=AgentStatus.SUCCESS, output=self._generate_periodic_report())
        
        analysis = {
            "tender_id": tender_id,
            "prediction_accuracy": {},
            "lessons": [],
            "learnings": [],
            "adjustments": [],
        }
        
        # Win probability accuracy
        if "win_probability" in predicted and "awarded" in actual:
            predicted_prob = predicted["win_probability"]
            awarded = actual["awarded"]
            error = abs(predicted_prob - (1.0 if awarded else 0.0))
            self._accuracy_tracker["win_probability"].append(error < 0.2)
            analysis["prediction_accuracy"]["win_probability"] = {
                "predicted": predicted_prob, "actual": 1.0 if awarded else 0.0, "error": error
            }
            if error >= 0.3:
                analysis["lessons"].append(f"Win probability off by {error:.0%}")
        
        # Discount prediction accuracy
        if "recommended_discount" in predicted and "actual_discount" in actual:
            diff = abs(predicted["recommended_discount"] - actual["actual_discount"])
            self._accuracy_tracker["discount"].append(diff < 2.0)
            analysis["prediction_accuracy"]["discount"] = {
                "predicted_pct": predicted.get("recommended_discount", 0),
                "actual_pct": actual["actual_discount"], "difference": diff,
            }
        
        # SLT prediction accuracy
        if "slt_predicted" in predicted and "slt_actual" in actual:
            slt_correct = predicted["slt_predicted"] == actual["slt_actual"]
            self._accuracy_tracker["slt_detection"].append(slt_correct)
            if not slt_correct:
                analysis["lessons"].append("SLT/ALT detection missed. Review threshold calibration.")
        
        self._pattern_store[tender_id] = {
            "predicted": predicted, "actual": actual, "analysis": analysis,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        # Query Knowledge Lake for historical patterns
        historical = await self.query_brain(entry_type="tender", tender_id=tender_id)
        if historical:
            analysis["historical_patterns"] = len(historical)
        
        return AgentResult(status=AgentStatus.SUCCESS, output=analysis)

    async def _record_feedback(self, context: Dict) -> AgentResult:
        """Record human feedback on agent outputs."""
        feedback = {
            "agent_id": context.get("agent_id", ""),
            "tender_id": context.get("tender_id", ""),
            "rating": context.get("rating", 0),
            "comment": context.get("comment", ""),
            "corrected_output": context.get("corrected_output", {}),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._feedback_store.append(feedback)
        
        # If there's a correction, learn from it
        if feedback["corrected_output"]:
            await self._learn_from_correction(feedback)
        
        # Share feedback with Knowledge Lake
        await self.share_knowledge(
            entry_type="feedback", tender_id=feedback["tender_id"],
            data=feedback, summary=f"Feedback for {feedback['agent_id']}: {feedback['rating']}",
            tags=["feedback", f"rating_{feedback['rating']}"]
        )
        
        return AgentResult(status=AgentStatus.SUCCESS, output={"recorded": True, "feedback": feedback})

    async def _get_accuracy(self) -> AgentResult:
        """Get accuracy metrics for all tracked agents."""
        metrics = {}
        for metric, values in self._accuracy_tracker.items():
            metrics[metric] = {
                "total": len(values),
                "correct": sum(values),
                "accuracy": sum(values) / len(values) if values else 0,
            }
        return AgentResult(status=AgentStatus.SUCCESS, output=metrics)

    async def _learn_from_history(self, context: Dict) -> AgentResult:
        """Learn from historical tender data."""
        tender_id = context.get("tender_id", "")
        patterns = self._analyze_win_patterns()
        discount_patterns = self._analyze_discount_patterns()
        learnings = []
        
        if len(self._pattern_store) >= 10:
            learnings.append(f"Analyzed {len(self._pattern_store)} outcomes")
            for metric, vals in self._accuracy_tracker.items():
                if vals:
                    acc = sum(vals) / len(vals)
                    learnings.append(f"{metric} accuracy: {acc:.0%}")
        
        result = {
            "tender_id": tender_id,
            "patterns": patterns + discount_patterns,
            "learnings": learnings,
            "total_patterns_stored": len(self._pattern_store),
        }
        return AgentResult(status=AgentStatus.SUCCESS, output=result)

    async def _recommend_improvements(self, context: Dict) -> AgentResult:
        """Generate improvement recommendations based on learning."""
        improvements = []
        if len(self._pattern_store) < 10:
            improvements.append({
                "area": "data_collection", "priority": "high",
                "message": f"Only {len(self._pattern_store)} outcomes recorded. Need at least 50.",
            })
        for metric, values in self._accuracy_tracker.items():
            if len(values) >= 5:
                accuracy = sum(values[-5:]) / len(values[-5:])
                if accuracy < 0.7:
                    improvements.append({
                        "area": metric, "priority": "high",
                        "message": f"Accuracy for {metric} is {accuracy:.0%} (below 70%)",
                    })
        negative = [f for f in self._feedback_store if f.get("rating", 0) < 0]
        if len(negative) > 3:
            improvements.append({
                "area": "agent_output", "priority": "medium",
                "message": f"{len(negative)} negative feedback entries",
            })
        
        return AgentResult(status=AgentStatus.SUCCESS, output={
            "improvements": improvements, "learnings": improvements,
            "total_outcomes": len(self._pattern_store), "total_feedback": len(self._feedback_store),
        })

    async def _learn_from_correction(self, feedback: Dict):
        """Learn from a human correction."""
        self._pattern_store[f"correction_{feedback['tender_id']}_{feedback['agent_id']}"] = {
            "type": "human_correction", "feedback": feedback,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _analyze_win_patterns(self) -> List[str]:
        patterns = []
        if self._pattern_store:
            patterns.append("Pattern analysis engine ready.")
        return patterns

    def _analyze_discount_patterns(self) -> List[str]:
        patterns = []
        if self._pattern_store:
            patterns.append("Discount pattern analysis initialized.")
        return patterns

    def _generate_periodic_report(self) -> Dict:
        return {
            "report_type": "periodic_learning",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "total_outcomes": len(self._pattern_store),
                "total_feedback": len(self._feedback_store),
                "tracked_agents": list(self._accuracy_tracker.keys()),
            },
            "learnings": ["Learning agent active. Collecting data for insights."],
        }
