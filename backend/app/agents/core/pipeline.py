"""
Intelligence Pipeline — Chains agents into knowledge-building workflows.
Each pipeline stage enriches data and passes it to the next.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Callable

from app.db import get_session

logger = logging.getLogger(__name__)


class PipelineStage:
    """A single stage in an intelligence pipeline."""
    
    def __init__(self, agent_id: str, input_mapping: Dict[str, str] = None,
                 output_keys: List[str] = None, depends_on: List[str] = None,
                 timeout: int = 60):
        self.agent_id = agent_id
        self.input_mapping = input_mapping or {}  # context key → agent input key
        self.output_keys = output_keys or []  # which output keys to propagate
        self.depends_on = depends_on or []
        self.timeout = timeout


class IntelligencePipeline:
    """
    Chains agents into a knowledge pipeline.
    
    Pipeline Flow:
      TenderRadar → TenderAcquisition → BOQIntelligence → 
      SpecIntelligence → EligibilityCompliance → MarketRateIntelligence →
      CompetitorIntelligence → WinProbability → BidPositionOptimizer →
      ExecutiveDecision
    
    Each stage:
      1. Receives enriched context from previous stages
      2. Executes its agent via the Brain
      3. Extracts key outputs and passes them forward
      4. Shares learnings to the Knowledge Lake
    """
    
    # The master pipeline definition
    PIPELINE = [
        PipelineStage(
            agent_id="agent-001-tender-radar",
            output_keys=["matched_tenders", "total", "scanned"],
        ),
        PipelineStage(
            agent_id="agent-002-tender-acquisition",
            depends_on=["agent-001-tender-radar"],
            output_keys=["nit", "tds", "boq", "drawings", "status"],
        ),
        PipelineStage(
            agent_id="agent-005-boq-intelligence",
            depends_on=["agent-002-tender-acquisition"],
            output_keys=["items", "total_amount", "anomalies", "classification"],
        ),
        PipelineStage(
            agent_id="agent-006-spec-intelligence",
            depends_on=["agent-002-tender-acquisition"],
            output_keys=["requirements", "risks", "special_materials", "compliance_gaps"],
        ),
        PipelineStage(
            agent_id="agent-007-eligibility-compliance",
            depends_on=["agent-005-boq-intelligence", "agent-006-spec-intelligence"],
            output_keys=["meets_criteria", "missing_requirements", "score"],
        ),
        PipelineStage(
            agent_id="agent-012-market-rate-intelligence",
            depends_on=["agent-005-boq-intelligence"],
            output_keys=["rates", "variances", "recommendation"],
        ),
        PipelineStage(
            agent_id="agent-013-competitor-intelligence",
            depends_on=["agent-001-tender-radar"],
            output_keys=["competitors", "win_rates", "patterns"],
        ),
        PipelineStage(
            agent_id="agent-016-win-probability",
            depends_on=["agent-013-competitor-intelligence", "agent-007-eligibility-compliance"],
            output_keys=["probability", "confidence", "factors"],
        ),
        PipelineStage(
            agent_id="agent-017-bid-position-optimizer",
            depends_on=["agent-016-win-probability", "agent-012-market-rate-intelligence"],
            output_keys=["recommended_discount", "ranges", "expected_margin"],
        ),
        PipelineStage(
            agent_id="agent-022-executive-decision",
            depends_on=["agent-016-win-probability", "agent-017-bid-position-optimizer"],
            output_keys=["decision", "confidence_score", "factors"],
        ),
    ]
    
    def __init__(self, brain):
        self.brain = brain
        self._results: Dict[str, Any] = {}
        self._start_time: float = 0
    
    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Run the full intelligence pipeline."""
        self._start_time = datetime.now(timezone.utc).timestamp()
        self._results = {"pipeline_start": self._start_time, "stages": []}
        
        enriched = dict(context)
        
        for stage in self.PIPELINE:
            stage_start = datetime.now(timezone.utc).timestamp()
            
            # Check dependencies
            deps_satisfied = all(dep in self._results for dep in stage.depends_on)
            if not deps_satisfied:
                logger.warning(f"Pipeline: {stage.agent_id} skipped (deps not ready)")
                continue
            
            # Prepare input from enriched context
            agent_input = dict(enriched)
            
            # Add outputs from dependency agents
            for dep in stage.depends_on:
                if dep in self._results:
                    agent_input[dep] = self._results[dep]
            
            try:
                # Execute agent via Brain
                agent = self.brain.get_agent(stage.agent_id)
                if not agent:
                    logger.warning(f"Pipeline: Agent {stage.agent_id} not found")
                    continue
                
                result = await agent.run(agent_input)
                elapsed = int((datetime.now(timezone.utc).timestamp() - stage_start) * 1000)
                
                # Extract outputs
                output = result.output if hasattr(result, 'output') else {}
                if isinstance(output, dict):
                    for key in stage.output_keys:
                        if key in output:
                            enriched[key] = output[key]
                            self._results[key] = output[key]
                
                # Store stage result
                self._results[stage.agent_id] = {
                    "status": result.status.value if hasattr(result.status, 'value') else str(result.status),
                    "elapsed_ms": elapsed,
                    "output_keys": list(output.keys()) if isinstance(output, dict) else [],
                }
                
                self._results["stages"].append({
                    "agent_id": stage.agent_id,
                    "status": result.status.value if hasattr(result.status, 'value') else str(result.status),
                    "elapsed_ms": elapsed,
                })
                
                logger.info(f"  ⚡ Pipeline stage: {stage.agent_id} → {result.status.value if hasattr(result.status, 'value') else 'done'} ({elapsed}ms)")
                
                # Share pipeline progress to Brain
                if self.brain:
                    await self.brain.broadcast(
                        sender_id="pipeline-orchestrator",
                        subject="pipeline_progress",
                        body={
                            "stage": stage.agent_id,
                            "status": result.status.value if hasattr(result.status, 'value') else str(result.status),
                            "elapsed_ms": elapsed,
                            "tender_id": context.get("tender_id", ""),
                        }
                    )
                
            except Exception as e:
                logger.error(f"Pipeline error at {stage.agent_id}: {e}")
                self._results[stage.agent_id] = {"status": "failed", "error": str(e)}
        
        total_elapsed = int((datetime.now(timezone.utc).timestamp() - self._start_time) * 1000)
        self._results["pipeline_complete"] = datetime.now(timezone.utc).isoformat()
        self._results["total_elapsed_ms"] = total_elapsed
        
        logger.info(f"🏁 Pipeline complete: {len(self._results['stages'])} stages in {total_elapsed}ms")
        
        return self._results


class KnowledgeFeedbackLoop:
    """
    Builds feedback loops where agents learn from each other's outcomes.
    
    How it works:
      1. Agent A makes a prediction → stored in DB
      2. Actual outcome happens → stored in DB  
      3. Learning Agent detects the gap
      4. Learning Agent broadcasts to all agents
      5. Agent A updates its weights for next time
      6. Agent B (different) uses Agent A's lesson to improve
    """
    
    @staticmethod
    async def record_outcome(agent_id: str, tender_id: str, 
                              predicted: Dict, actual: Dict, brain) -> Dict:
        """Record an outcome and trigger learning."""
        # Ask Learning Agent to analyze
        learning_result = await brain.request(
            sender_id=agent_id,
            recipient_id="agent-026-learning",
            subject="analyze_outcome",
            body={
                "tender_id": tender_id,
                "predicted": predicted,
                "actual": actual,
                "action": "analyze",
            }
        )
        
        # Broadcast findings if significant
        if learning_result and isinstance(learning_result, dict):
            accuracy = learning_result.get("prediction_accuracy", {})
            lessons = learning_result.get("lessons", [])
            if lessons:
                await brain.broadcast(
                    sender_id=agent_id,
                    subject="learning_from_outcome",
                    body={
                        "tender_id": tender_id,
                        "agent": agent_id,
                        "lessons": lessons,
                        "accuracy": accuracy,
                    }
                )
        
        return learning_result or {}
