from __future__ import annotations
"""
Base Agent — All agents inherit from this.
Provides DB integration, Agent Brain communication, standard result format.
"""

import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


@dataclass
class AgentResult:
    """Standard agent execution result."""
    agent_id: str = ""
    agent_name: str = ""
    status: AgentStatus = AgentStatus.PENDING
    output: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    execution_time_ms: int = 0
    model_used: str = ""
    trace_id: str = ""
    request_id: str = ""
    tender_id: str = ""
    source_ids: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "status": self.status.value if isinstance(self.status, AgentStatus) else self.status,
            "output": self.output,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "model_used": self.model_used,
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "tender_id": self.tender_id,
            "created_at": self.created_at,
        }
class BaseAgent(ABC):
    """Abstract base class for all ProcureFlow agents.
    
    Every agent must implement:
    - agent_id: Unique identifier
    - agent_name: Human-readable name
    - description: What this agent does
    - execute(context): Main execution method
    
    Optional:
    - dependencies: List of agent_ids this agent depends on
    - version: Semantic version
    - brain: AgentBrain instance for inter-agent communication
    """
    
    agent_id: str = "base-agent"
    agent_name: str = "Base Agent"
    description: str = "Base agent class"
    dependencies: List[str] = []
    version: str = "1.0.0"
    
    def __init__(self, brain=None):
        self.brain = brain
        self._db_session = None
        self._status = AgentStatus.PENDING
    
    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        """Execute the agent's primary function.
        
        Args:
            context: Dict containing:
                - tender_id: str
                - request_id: str
                - bid_data: Dict
                - upstream: Dict of upstream agent results
                - Any other agent-specific data
        
        Returns:
            AgentResult with status and output
        """
        pass
    
    async def run(self, context: Dict[str, Any]) -> AgentResult:
        """Wrapper around execute() with timing and error handling."""
        start = time.time()
        trace_id = str(uuid.uuid4())
        request_id = context.get("request_id", trace_id)
        tender_id = context.get("tender_id", "")
        self._status = AgentStatus.RUNNING
        
        logger.info(f"▶ {self.agent_id} ({self.agent_name}) starting — request_id={request_id[:8]}...")
        
        try:
            # Add trace info
            context["_trace_id"] = trace_id
            context["_request_id"] = request_id
            context["_agent_id"] = self.agent_id
            context["_start_time"] = start
            
            result = await self.execute(context)
            
            if not isinstance(result, AgentResult):
                result = AgentResult(
                    agent_id=self.agent_id,
                    agent_name=self.agent_name,
                    status=AgentStatus.SUCCESS,
                    output=result if isinstance(result, dict) else {"result": result},
                )
            
            result.agent_id = self.agent_id
            result.agent_name = self.agent_name
            result.execution_time_ms = int((time.time() - start) * 1000)
            result.trace_id = trace_id
            result.request_id = request_id
            result.tender_id = tender_id
            
            if result.status == AgentStatus.PENDING:
                result.status = AgentStatus.SUCCESS

            self._status = result.status
            logger.info(f"✓ {self.agent_id} completed in {result.execution_time_ms}ms — {result.status.value}")

        except Exception as e:
            elapsed = int((time.time() - start) * 1000)
            logger.error(f"✗ {self.agent_id} FAILED after {elapsed}ms: {e}")
            
            result = AgentResult(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error=str(e),
                execution_time_ms=elapsed,
                trace_id=trace_id,
                request_id=request_id,
                tender_id=tender_id,
            )
            self._status = AgentStatus.FAILED

        await self.store_result(result)
        return result
    
    async def store_result(self, result: AgentResult, session=None):
        """Persist agent result to database."""
        from app.db import AgentResult as DBResult
        from app.db.database import get_sync_session

        owns_session = session is None
        db_session = session or get_sync_session()
        try:
            db_result = DBResult(
                agent_id=result.agent_id,
                agent_name=result.agent_name,
                agent_version=self.version,
                request_id=result.request_id,
                tender_id=result.tender_id,
                status=result.status.value if isinstance(result.status, AgentStatus) else result.status,
                output=result.output,
                error=result.error,
                execution_time_ms=result.execution_time_ms,
                trace_id=result.trace_id,
            )
            db_session.add(db_result)
            db_session.commit()
        except Exception as e:
            logger.warning(f"Could not persist result: {e}")
        finally:
            if owns_session:
                try:
                    db_session.close()
                except Exception:
                    pass
    
    async def share_knowledge(self, entry_type: str, tender_id: str = "", 
                               data: Dict = None, summary: str = "", tags: List[str] = None):
        """Share knowledge via the Agent Brain."""
        if self.brain:
            return await self.brain.store_knowledge(
                agent_id=self.agent_id,
                entry_type=entry_type,
                tender_id=tender_id,
                data=data,
                summary=summary,
                tags=tags,
            )
        logger.warning(f"Cannot share knowledge: no AgentBrain connected")
        return None
    
    async def query_brain(self, entry_type: str = None, tender_id: str = None) -> List[Dict]:
        """Query the Agent Brain for knowledge."""
        if self.brain:
            return await self.brain.query_knowledge(
                entry_type=entry_type, tender_id=tender_id
            )
        return []
    
    async def ask_agent(self, recipient_id: str, subject: str, 
                         body: Dict, timeout: float = 30.0) -> Optional[Dict]:
        """Ask another agent for help via the Agent Brain."""
        if self.brain:
            return await self.brain.request(
                sender_id=self.agent_id,
                recipient_id=recipient_id,
                subject=subject,
                body=body,
                timeout=timeout,
            )
        logger.warning(f"Cannot ask agent: no AgentBrain connected")
        return None
    
    def get_dependencies(self) -> List[str]:
        return self.dependencies

    @property
    def status(self) -> AgentStatus:
        return self._status

    def info(self) -> Dict[str, Any]:
        """Return a stable metadata payload for registry and API consumers."""
        status = getattr(self, "_status", None)
        if isinstance(status, AgentStatus):
            status_value = status.value
        else:
            status_value = AgentStatus.PENDING.value

        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "description": self.description,
            "dependencies": list(self.dependencies),
            "version": self.version,
            "status": status_value,
        }

    def __repr__(self):
        return f"<{self.agent_id}: {self.agent_name}>"
