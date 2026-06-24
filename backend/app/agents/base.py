"""
Procurement Flow Specialist BD — Base Agent Architecture
Defines the abstract base class for all 27 agents.
"""

from __future__ import annotations

import enum
import json
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentStatus(enum.Enum):
    """Lifecycle status of an agent execution."""
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


@dataclass
class AgentResult:
    """Standard output envelope for every agent."""
    agent_id: str
    agent_name: str
    status: AgentStatus
    output: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)

    @classmethod
    def empty(cls, agent_id: str, agent_name: str) -> "AgentResult":
        return cls(
            agent_id=agent_id,
            agent_name=agent_name,
            status=AgentStatus.IDLE,
            output={},
        )


class BaseAgent(ABC):
    """
    Abstract base for every Procurement Flow Specialist BD agent.
    
    Subclasses must implement:
    - agent_id       (class-level constant)
    - agent_name     (human-readable)
    - description    (purpose statement)
    - dependencies   (list of agent_ids that must run first)
    - version
    - execute(context) -> AgentResult
    """

    agent_id: str = ""
    agent_name: str = ""
    description: str = ""
    dependencies: List[str] = []
    version: str = "1.0.0"

    def __init__(self) -> None:
        if not self.agent_id:
            raise ValueError(f"{type(self).__name__} must define agent_id")
        self._status = AgentStatus.IDLE
        self._last_result: Optional[AgentResult] = None

    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        """Execute the agent's primary logic."""
        ...

    async def run(self, context: Dict[str, Any]) -> AgentResult:
        """Wrapper that times execution and handles errors."""
        logger.info(f"[{self.agent_id}] {self.agent_name} — starting")
        self._status = AgentStatus.RUNNING
        start = datetime.now(timezone.utc)

        try:
            result = await self.execute(context)
            result.agent_id = self.agent_id
            result.agent_name = self.agent_name
            result.status = AgentStatus.SUCCESS
            logger.info(f"[{self.agent_id}] completed in {result.execution_time_ms:.0f}ms")
        except Exception as exc:
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            result = AgentResult(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error=str(exc),
                execution_time_ms=elapsed,
            )
            logger.error(f"[{self.agent_id}] failed: {exc}")

        elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        result.execution_time_ms = elapsed
        result.timestamp = datetime.now(timezone.utc).isoformat()
        self._last_result = result
        self._status = result.status
        return result

    @property
    def status(self) -> AgentStatus:
        return self._status

    @property
    def last_result(self) -> Optional[AgentResult]:
        return self._last_result

    def info(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "description": self.description,
            "dependencies": self.dependencies,
            "version": self.version,
            "status": self._status.value,
        }
