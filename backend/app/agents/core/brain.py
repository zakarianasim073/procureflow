"""
Agent Brain — Inter-Agent Communication Hub.
Agents can:
  - Send/receive messages to/from other agents
  - Share knowledge via the Knowledge Lake
  - Query other agents for data
  - Broadcast to all agents
  - Store and retrieve facts

Architecture:
  AgentBrain (central hub) 
    → Message Queue (in-memory + DB persisted)
    → Agent Registry (who can do what)
    → Knowledge Store (what we know)
    → Query Router (which agent handles which query)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.core.watchdog import get_watchdog
from app.db import (
    AgentBrainMessage, AgentResult, AgentJob, AgentLog,
    KnowledgeEntry, get_session,
)

logger = logging.getLogger(__name__)


# ── Message Types ────────────────────────────────────────────────────────

class MessageType(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"
    BROADCAST = "broadcast"
    KNOWLEDGE_SHARE = "knowledge_share"
    QUERY = "query"
    STATUS_CHECK = "status_check"
    WORKFLOW_TRIGGER = "workflow_trigger"
    ERROR = "error"


@dataclass
class BrainMessage:
    """Standard message format for Agent Brain communication."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str = ""
    recipient_id: str = ""  # empty = broadcast
    message_type: str = MessageType.REQUEST
    subject: str = ""
    body: Dict[str, Any] = field(default_factory=dict)
    thread_id: str = ""
    response_to: str = ""
    priority: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "BrainMessage":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class AgentCapability:
    """What an agent can do."""
    agent_id: str
    agent_name: str
    description: str
    input_types: List[str] = field(default_factory=list)  # What data it needs
    output_types: List[str] = field(default_factory=list)  # What data it produces
    can_query: List[str] = field(default_factory=list)  # Query types it can answer
    version: str = "1.0.0"
    is_available: bool = True


class AgentBrain:
    """
    Central nervous system for the multi-agent procurement intelligence platform.
    
    Features:
    - Agent Registry: Knows all agents and their capabilities
    - Message Bus: Async pub/sub message passing
    - Knowledge Store: Shared facts that agents can read/write
    - Query Router: Routes questions to the right agent
    - Workflow Triggers: Chain agent executions
    - Status Monitoring: Check agent health
    """
    
    def __init__(self, db_session_factory=None):
        self._agents: Dict[str, AgentCapability] = {}
        self._agent_instances: Dict[str, Any] = {}
        self._subscriptions: Dict[str, List[str]] = defaultdict(list)  # agent_id → [subscribed message types]
        self._message_handlers: Dict[str, Callable] = {}
        self._knowledge_store: Dict[str, Any] = {}  # In-memory fast cache
        
        self.db = db_session_factory or get_session
        self._running = False
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._processing_task = None
        self._idle_task = None
        
        logger.info("🧠 Agent Brain initialized")
    
    # ── Agent Registry ──────────────────────────────────────────────────
    
    def register_agent(self, agent_id: str, instance: Any, 
                       name: str = "", description: str = "",
                       input_types: List[str] = None,
                       output_types: List[str] = None,
                       can_query: List[str] = None,
                       version: str = "1.0.0"):
        """Register an agent with the brain."""
        self._agent_instances[agent_id] = instance
        
        cap = AgentCapability(
            agent_id=agent_id,
            agent_name=name or getattr(instance, "agent_name", agent_id),
            description=description or getattr(instance, "description", ""),
            input_types=input_types or [],
            output_types=output_types or [],
            can_query=can_query or [],
            version=version or getattr(instance, "version", "1.0.0"),
        )
        self._agents[agent_id] = cap
        logger.info(f"  ✓ Agent registered: {cap.agent_name} ({agent_id}) v{cap.version}")
        
        # Auto-register default message handler for inter-agent communication
        async def _default_handler(msg):
            try:
                context = dict(msg.body) if msg.body else {}
                context["_message"] = msg
                context["tender_id"] = context.get("tender_id", "")
                result = await instance.run(context)
                if hasattr(result, 'output'):
                    return result.output if isinstance(result.output, dict) else {"result": str(result.output)}
                if isinstance(result, dict):
                    return result
                return {"result": str(result)}
            except Exception as e:
                logger.error(f"Default handler error for {agent_id}: {e}")
                return {"error": str(e)}
        
        self._message_handlers[agent_id] = _default_handler
        return cap
    
    def register_agents(self, *agents: Any):
        """Register multiple agents at once."""
        for agent in agents:
            agent_id = getattr(agent, "agent_id", None) or getattr(agent, "__class__").__name__
            self.register_agent(agent_id, agent)
    
    def get_agent(self, agent_id: str) -> Optional[Any]:
        """Get agent instance by ID."""
        return self._agent_instances.get(agent_id)
    
    def get_capability(self, agent_id: str) -> Optional[AgentCapability]:
        """Get agent capability info."""
        return self._agents.get(agent_id)
    
    def list_agents(self) -> List[AgentCapability]:
        """List all registered agents."""
        return list(self._agents.values())
    
    def find_agents_by_capability(self, query_type: str) -> List[AgentCapability]:
        """Find agents that can handle a specific query type."""
        return [
            a for a in self._agents.values()
            if query_type in a.can_query
        ]
    
    # ── Message Bus ─────────────────────────────────────────────────────
    
    async def send_message(self, message: BrainMessage) -> bool:
        """Send a message through the brain. Async with DB persistence."""
        # Persist to DB
        try:
            async with self.db() as session:
                # Ensure body is JSON-serializable
                import json as _json
                body_safe = message.body
                if not isinstance(body_safe, (dict, list, str, int, float, bool, type(None))):
                    body_safe = str(body_safe)
                elif isinstance(body_safe, dict):
                    try:
                        _json.dumps(body_safe)
                    except:
                        body_safe = {k: (str(v) if not isinstance(v, (dict, list, str, int, float, bool, type(None))) else v) for k, v in body_safe.items()}
                        # Try again with deeper serialization
                        try:
                            _json.dumps(body_safe)
                        except:
                            body_safe = _json.loads(_json.dumps(body_safe, default=str))
                db_msg = AgentBrainMessage(
                    id=message.id,
                    sender_id=message.sender_id,
                    recipient_id=message.recipient_id,
                    message_type=message.message_type.value if hasattr(message.message_type, "value") else str(message.message_type),
                    subject=message.subject,
                    body=body_safe,
                    thread_id=message.thread_id or message.id,
                    response_to=message.response_to,
                    status="sent",
                )
                session.add(db_msg)
                await session.commit()
        except Exception as e:
            logger.warning(f"Could not persist message to DB: {e}")
        
        # Queue for delivery
        await self._message_queue.put(message)
        return True
    
    async def broadcast(self, sender_id: str, subject: str, body: Dict, 
                        exclude: List[str] = None) -> List[str]:
        """Broadcast a message to all agents."""
        msg = BrainMessage(
            sender_id=sender_id,
            recipient_id="*",  # broadcast
            message_type=MessageType.BROADCAST,
            subject=subject,
            body=body,
        )
        msg.body = {
            **(body or {}),
            "_broadcast_exclude": list(exclude or []),
        }
        delivered = [
            agent_id
            for agent_id in self._agent_instances
            if agent_id != sender_id and agent_id not in (exclude or [])
        ]
        await self.send_message(msg)
        return delivered
    
    async def request(self, sender_id: str, recipient_id: str, 
                      subject: str, body: Dict, timeout: float = 30.0) -> Optional[Dict]:
        """Send a request to a specific agent and wait for response."""
        thread_id = str(uuid.uuid4())
        msg = BrainMessage(
            sender_id=sender_id,
            recipient_id=recipient_id,
            message_type=MessageType.REQUEST,
            subject=subject,
            body=body,
            thread_id=thread_id,
        )
        await self.send_message(msg)
        
        # If the agent has a handler, call it and return result
        if recipient_id in self._message_handlers:
            try:
                response = await asyncio.wait_for(
                    self._message_handlers[recipient_id](msg),
                    timeout=timeout
                )
                # Send response back to sender
                resp_msg = BrainMessage(
                    sender_id=recipient_id,
                    recipient_id=sender_id,
                    message_type=MessageType.RESPONSE,
                    subject=f"RE: {subject}",
                    body=response if isinstance(response, dict) else {"result": response},
                    thread_id=thread_id,
                    response_to=msg.id,
                )
                await self.send_message(resp_msg)
                return response
            except asyncio.TimeoutError:
                logger.warning(f"Request to {recipient_id} timed out after {timeout}s")
                return {"error": "timeout", "message": f"Agent {recipient_id} did not respond in {timeout}s"}
            except Exception as e:
                logger.error(f"Error handling request by {recipient_id}: {e}")
                return {"error": str(e)}
        else:
            logger.warning(f"No handler registered for {recipient_id}")
            return {"error": f"No handler for {recipient_id}"}
    
    def on_message(self, agent_id: str):
        """Decorator to register a message handler for an agent."""
        def decorator(func):
            self._message_handlers[agent_id] = func
            return func
        return decorator
    
    def subscribe(self, agent_id: str, message_types: List[str]):
        """Subscribe an agent to specific message types."""
        self._subscriptions[agent_id].extend(message_types)
    
    # ── Knowledge Store ─────────────────────────────────────────────────
    
    async def store_knowledge(self, agent_id: str, entry_type: str, 
                               tender_id: str, data: Dict,
                               summary: str = "", tags: List[str] = None) -> str:
        """Store a knowledge entry shared by an agent."""
        entry_id = str(uuid.uuid4())
        normalized_tender_id = tender_id or None
        
        # Also commit to DB
        if normalized_tender_id:
            try:
                async with self.db() as session:
                    ke = KnowledgeEntry(
                        id=entry_id,
                        tender_id=normalized_tender_id,
                        entry_type=entry_type,
                        data=data,
                        summary=summary or json.dumps(data)[:500],
                        source=agent_id,
                        tags=tags or [],
                    )
                    session.add(ke)
                    await session.commit()
            except Exception as e:
                logger.warning(f"Could not store knowledge in DB: {e}")
        
        # Cache in memory
        key = f"{entry_type}:{normalized_tender_id or '_global'}"
        self._knowledge_store[key] = {
            "entry_id": entry_id,
            "agent_id": agent_id,
            "entry_type": entry_type,
            "tender_id": normalized_tender_id,
            "data": data,
            "summary": summary,
            "tags": tags or [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        logger.info(f"  📚 Agent {agent_id} shared {entry_type} knowledge for {normalized_tender_id or 'global'}")
        return entry_id
    
    async def query_knowledge(self, entry_type: str = None, 
                               tender_id: str = None,
                               tags: List[str] = None,
                               limit: int = 100) -> List[Dict]:
        """Query the knowledge store."""
        results = []
        
        for key, entry in self._knowledge_store.items():
            if entry_type and entry["entry_type"] != entry_type:
                continue
            if tender_id and entry["tender_id"] != tender_id:
                continue
            if tags and not all(t in entry["tags"] for t in tags):
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        
        # If not in cache, try DB
        if not results:
            try:
                async with self.db() as session:
                    query = select(KnowledgeEntry)
                    if entry_type:
                        query = query.where(KnowledgeEntry.entry_type == entry_type)
                    if tender_id:
                        query = query.where(KnowledgeEntry.tender_id == tender_id)
                    
                    result = await session.execute(query.limit(limit))
                    for row in result.scalars():
                        results.append({
                            "entry_id": row.id,
                            "entry_type": row.entry_type,
                            "tender_id": row.tender_id,
                            "data": row.data,
                            "summary": row.summary,
                            "tags": row.tags,
                        })
            except Exception as e:
                logger.warning(f"Could not query knowledge DB: {e}")
        
        return results
    
    async def get_agent_result(self, agent_id: str, tender_id: str = None, 
                                request_id: str = None) -> Optional[Dict]:
        """Get the latest result from a specific agent."""
        try:
            async with self.db() as session:
                query = select(AgentResult).where(
                    AgentResult.agent_id == agent_id
                )
                if tender_id:
                    query = query.where(AgentResult.tender_id == tender_id)
                if request_id:
                    query = query.where(AgentResult.request_id == request_id)
                
                query = query.order_by(AgentResult.created_at.desc()).limit(1)
                result = await session.execute(query)
                row = result.scalar_one_or_none()
                if row:
                    return {
                        "agent_id": row.agent_id,
                        "tender_id": row.tender_id,
                        "status": row.status,
                        "output": row.output,
                        "execution_time_ms": row.execution_time_ms,
                        "created_at": str(row.created_at),
                    }
        except Exception as e:
            logger.warning(f"Could not query agent result: {e}")
        return None
    
    # ── Message Processing ──────────────────────────────────────────────
    
    async def _process_messages(self):
        """Background task to process queued messages."""
        while self._running:
            try:
                msg = await asyncio.wait_for(self._message_queue.get(), timeout=1.0)
                await self._deliver_message(msg)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing message: {e}")
    
    async def _deliver_message(self, msg: BrainMessage):
        """Deliver a message to its recipient(s)."""
        if msg.recipient_id == "*" or not msg.recipient_id:
            # Broadcast to all
            excluded = set((msg.body or {}).get("_broadcast_exclude", []) or [])
            for agent_id, handler in self._message_handlers.items():
                if agent_id != msg.sender_id and agent_id not in excluded:
                    try:
                        await handler(msg)
                    except Exception as e:
                        logger.error(f"Broadcast delivery error to {agent_id}: {e}")
        elif msg.recipient_id in self._message_handlers:
            try:
                await self._message_handlers[msg.recipient_id](msg)
            except Exception as e:
                logger.error(f"Delivery error to {msg.recipient_id}: {e}")
    
    async def start(self):
        """Start the brain's message processing loop."""
        if self._running:
            logger.warning("Agent Brain is already running")
            return
        
        self._running = True
        self._processing_task = asyncio.create_task(self._process_messages())
        self._idle_task = asyncio.create_task(self._idle_time_cycle())
        logger.info("🧠 Agent Brain started — message + idle processing active")
    
    async def stop(self):
        """Stop the brain."""
        self._running = False
        if self._idle_task:
            self._idle_task.cancel()
            self._idle_task = None
        if self._processing_task:
            self._processing_task.cancel()
            self._processing_task = None
        self._idle_task = None
        logger.info("🧠 Agent Brain stopped")
    
    # ── Workflow Orchestration ──────────────────────────────────────────
    
    async def run_workflow(self, workflow: List[Dict[str, Any]], 
                            context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Run a workflow of chained agent executions.
        
        workflow: [
            {"agent_id": "agent-001", "input": {...}, "depends_on": []},
            {"agent_id": "agent-005", "input": {...}, "depends_on": ["agent-001"]},
        ]
        """
        context = context or {}
        results = {}
        
        for step in workflow:
            agent_id = step["agent_id"]
            depends_on = step.get("depends_on", [])
            
            # Check dependencies
            for dep in depends_on:
                if dep not in results:
                    raise ValueError(f"Dependency {dep} not satisfied for {agent_id}")
            
            agent = self.get_agent(agent_id)
            if not agent:
                logger.warning(f"Agent {agent_id} not found in workflow")
                continue
            
            step_input = {**context, **step.get("input", {})}
            for dep in depends_on:
                step_input[dep] = results[dep]
            
            try:
                start = time.time()
                if hasattr(agent, "execute"):
                    if asyncio.iscoroutinefunction(agent.execute):
                        result = await agent.execute(step_input)
                    else:
                        result = agent.execute(step_input)
                else:
                    result = {"error": f"Agent {agent_id} has no execute method"}
                
                elapsed = int((time.time() - start) * 1000)
                results[agent_id] = result
                logger.info(f"  ⚡ {agent_id} completed in {elapsed}ms")
                
                # Store result
                if hasattr(result, "output") if not isinstance(result, dict) else True:
                    output = result if isinstance(result, dict) else getattr(result, "output", {})
                    try:
                        async with self.db() as session:
                            ar = AgentResult(
                                agent_id=agent_id,
                                request_id=step.get("request_id", context.get("request_id")),
                                tender_id=step.get("tender_id", context.get("tender_id")),
                                status="success",
                                output=output if isinstance(output, dict) else {},
                                execution_time_ms=elapsed,
                            )
                            session.add(ar)
                            await session.commit()
                    except Exception as e:
                        logger.warning(f"Could not store result: {e}")
                
            except Exception as e:
                logger.error(f"Workflow step {agent_id} failed: {e}")
                results[agent_id] = {"error": str(e)}
        
        return results
    
    # ── Utilities ───────────────────────────────────────────────────────
    
    async def _idle_time_cycle(self):
        """
        Background idle-time processing cycle.
        Runs pre-emptive intelligence agents during idle periods.
        
        Cycle:
          5 min: Quick check for new tenders
          15 min: Run pre-screener on tenders
          30 min: Run full MOAT/SLT/NPPI analysis  
          60 min: Full intelligence refresh + knowledge persistence
        """
        cycle_count = 0
        while self._running:
            try:
                cycle_count += 1
                elapsed_mins = cycle_count * 5
                
                if elapsed_mins % 60 == 5:  # Every ~60 min
                    logger.info("🧠 Idle cycle: Full intelligence refresh")
                    for aid in ["agent-038-tender-pre-screener", "agent-036-moat-slt-analyzer"]:
                        agent = self._agent_instances.get(aid)
                        if agent:
                            try:
                                if hasattr(agent, 'execute'):
                                    await agent.execute({"action": "full_analysis"})
                            except Exception as e:
                                logger.warning(f"Idle agent {aid} error: {e}")
                
                elif elapsed_mins % 30 == 5:  # Every ~30 min
                    logger.info("🧠 Idle cycle: MOAT/SLT/Pre-screen")
                    for aid in ["agent-038-tender-pre-screener", "agent-036-moat-slt-analyzer"]:
                        agent = self._agent_instances.get(aid)
                        if agent:
                            try:
                                await agent.execute({"action": "idle_cycle"})
                            except Exception as e:
                                logger.warning(f"Idle agent {aid} error: {e}")
                
                elif elapsed_mins % 15 == 5:  # Every ~15 min
                    logger.info("🧠 Idle cycle: Pre-screening tenders")
                    agent = self._agent_instances.get("agent-038-tender-pre-screener")
                    if agent:
                        try:
                            await agent.execute({"action": "pre_screen", "company_profile": {}})
                        except Exception as e:
                            logger.warning(f"Pre-screener error: {e}")
                
                # Sleep 5 minutes
                for _ in range(300):
                    if not self._running:
                        break
                    await asyncio.sleep(1)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"🧠 Idle cycle error: {e}")
                await asyncio.sleep(60)
    

    def get_stats(self) -> Dict:
        """Get brain statistics."""
        return {
            "registered_agents": len(self._agents),
            "active_handlers": len(self._message_handlers),
            "queue_size": self._message_queue.qsize(),
            "knowledge_entries": len(self._knowledge_store),
            "agents": [
                {"id": a.agent_id, "name": a.agent_name, "available": a.is_available}
                for a in self._agents.values()
            ],
        }
    
    async def get_system_memory(self) -> Dict:
        """Get system checkpoint/memory summary."""
        memory = {
            "agent_count": len(self._agents),
            "knowledge_count": len(self._knowledge_store),
            "uptime": "active",
            "last_idle_cycle": None,
            "agents": [
                {"id": a.agent_id, "name": a.agent_name}
                for a in self._agents.values()
            ],
        }
        # Get last knowledge entries for context
        recent = await self.query_knowledge(limit=5)
        if recent:
            memory["recent_knowledge"] = recent
        return memory
