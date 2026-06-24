"""
Procurement Flow Specialist BD — Agent Registry
Central registry for discovering, managing, and executing agents.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Type

from .base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class AgentRegistry:
    """
    Singleton registry that holds all agent instances.
    
    Provides discovery, dependency resolution, and orchestrated execution.
    """

    _instance: Optional["AgentRegistry"] = None
    _agents: Dict[str, BaseAgent] = {}

    def __new__(cls) -> "AgentRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._agents = {}
        return cls._instance

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, agent: BaseAgent) -> None:
        if not agent.agent_id:
            raise ValueError(f"Cannot register agent without agent_id: {type(agent).__name__}")
        self._agents[agent.agent_id] = agent
        logger.info(f"Registered agent [{agent.agent_id}] {agent.agent_name}")

    def register_many(self, *agents: BaseAgent) -> None:
        for a in agents:
            self.register(a)

    def get(self, agent_id: str) -> Optional[BaseAgent]:
        return self._agents.get(agent_id)

    def list_agents(self) -> List[Dict[str, Any]]:
        return [
            {"agent_id": a.agent_id, "agent_name": a.agent_name,
             "description": a.description, "status": a.status.value,
             "dependencies": a.dependencies, "version": a.version}
            for a in self._agents.values()
        ]

    def list_by_status(self, status: AgentStatus) -> List[BaseAgent]:
        return [a for a in self._agents.values() if a.status == status]

    @property
    def count(self) -> int:
        return len(self._agents)

    # ------------------------------------------------------------------
    # Dependency resolution
    # ------------------------------------------------------------------

    def _resolve_order(self, agent_ids: List[str]) -> List[str]:
        """Topological sort of requested agents by dependency graph."""
        graph: Dict[str, List[str]] = {}
        for aid in agent_ids:
            agent = self.get(aid)
            if not agent:
                raise ValueError(f"Unknown agent: {aid}")
            graph[aid] = [d for d in agent.dependencies if d in agent_ids]

        visited: set = set()
        resolved: List[str] = []

        def dfs(node: str) -> None:
            if node in visited:
                return
            visited.add(node)
            for dep in graph.get(node, []):
                dfs(dep)
            resolved.append(node)

        for aid in agent_ids:
            dfs(aid)
        return resolved

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def run_agent(self, agent_id: str, context: Dict[str, Any]) -> AgentResult:
        agent = self.get(agent_id)
        if not agent:
            return AgentResult(
                agent_id=agent_id, agent_name="Unknown",
                status=AgentStatus.FAILED, error=f"Agent not found: {agent_id}",
            )
        return await agent.run(context)

    async def run_pipeline(
        self,
        agent_ids: List[str],
        context: Dict[str, Any],
        stop_on_failure: bool = True,
    ) -> Dict[str, AgentResult]:
        """
        Run a list of agents in dependency order, passing the shared context.
        Each agent's output is merged into context under agent_results[agent_id].
        """
        if "agent_results" not in context:
            context["agent_results"] = {}

        order = self._resolve_order(agent_ids)
        results: Dict[str, AgentResult] = {}

        for aid in order:
            agent = self.get(aid)
            if not agent:
                continue

            # Check dependencies
            missing_deps = [d for d in agent.dependencies if d not in results]
            if missing_deps:
                result = AgentResult(
                    agent_id=aid, agent_name=agent.agent_name,
                    status=AgentStatus.BLOCKED,
                    error=f"Missing dependencies: {missing_deps}",
                )
                results[aid] = result
                if stop_on_failure:
                    break
                continue

            # Merge upstream outputs into context for this agent
            run_context = dict(context)
            run_context["upstream"] = {
                dep: results[dep].output for dep in agent.dependencies if dep in results
            }

            result = await agent.run(run_context)
            results[aid] = result
            context["agent_results"][aid] = result.to_dict()

            if result.status == AgentStatus.FAILED and stop_on_failure:
                logger.warning(f"Pipeline stopped at [{aid}] due to failure")
                break

        return results
