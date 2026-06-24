"""
Thought Engine — Human-in-the-Loop Approval System.
Agents propose insights → User approves once → System auto-executes forever.

Flow:
  1. Agent discovers pattern/insight/warning
  2. Thought Engine checks: "Has user approved this type of thought before?"
  3. If YES → agent auto-executes (no user interruption)
  4. If NO → thought saved as "pending" for user review
  5. User approves → system stores the approval signature
  6. Next time same pattern → auto-executes (step 3)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.db import get_session
from app.db.models import AgentThought

logger = logging.getLogger(__name__)


class ThoughtSignature:
    """
    Creates a unique signature for a thought type so we can 
    check if user already approved similar thoughts.
    
    Signature = hash(agent_id + thought_type + key_pattern)
    """
    
    @staticmethod
    def create(agent_id: str, thought_type: str, key_data: Dict) -> str:
        """Create a unique signature for a thought pattern."""
        raw = f"{agent_id}|{thought_type}|{json.dumps(key_data, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
    
    @staticmethod
    def create_pattern(agent_id: str, thought_type: str) -> str:
        """Create a pattern-level signature (ignoring specific data)."""
        raw = f"{agent_id}|{thought_type}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


class ThoughtEngine:
    """
    Manages the propose → approve → auto-execute cycle.
    
    Key concept: "Approval signatures" are stored patterns.
    If an agent's thought matches an approved signature, it auto-executes.
    """
    
    def __init__(self, brain=None):
        self.brain = brain
        self._auto_approve_cache: Dict[str, bool] = {}  # memory cache for speed
    
    async def propose(self, agent_id: str, agent_name: str, thought_type: str,
                       title: str, description: str, evidence: Dict = None,
                       tender_id: str = "", impact: str = "medium",
                       confidence: float = 0.0, key_data: Dict = None) -> Dict:
        """
        Agent proposes a thought.
        
        Returns:
          - If approved before: {"status": "auto_approved", "action": "execute"}
          - If new: {"status": "pending_review", "thought_id": "..."}
        """
        evidence = evidence or {}
        key_data = key_data or {}
        
        # Create signatures
        specific_sig = ThoughtSignature.create(agent_id, thought_type, key_data)
        pattern_sig = ThoughtSignature.create_pattern(agent_id, thought_type)
        
        # Check cache first
        if specific_sig in self._auto_approve_cache:
            logger.info(f"⚡ Auto-execute (cached): {agent_id} → {thought_type}")
            return {
                "status": "auto_approved",
                "signature": specific_sig,
                "action": "execute",
                "reason": "Previously approved (cached)",
            }
        
        if pattern_sig in self._auto_approve_cache:
            logger.info(f"⚡ Auto-execute (pattern cached): {agent_id} → {thought_type}")
            return {
                "status": "auto_approved",
                "signature": specific_sig,
                "action": "execute",
                "reason": "Pattern previously approved (cached)",
            }
        
        # Check database for existing approvals
        session = get_session()
        async with session as s:
            from sqlalchemy import select
            
            # Check specific approval
            result = await s.execute(
                select(AgentThought).where(
                    AgentThought.status == "approved",
                    AgentThought.agent_id == agent_id,
                    AgentThought.thought_type == thought_type,
                ).limit(1)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                # Cache for next time
                self._auto_approve_cache[specific_sig] = True
                self._auto_approve_cache[pattern_sig] = True
                logger.info(f"⚡ Auto-execute (DB): {agent_id} → {thought_type}")
                return {
                    "status": "auto_approved",
                    "signature": specific_sig,
                    "action": "execute",
                    "reason": f"Previously approved on {existing.created_at.isoformat() if hasattr(existing.created_at, 'isoformat') else existing.created_at}",
                }
            
            # Check if any thought of this type was approved before (pattern match)
            result = await s.execute(
                select(AgentThought).where(
                    AgentThought.status == "approved",
                    AgentThought.agent_id == agent_id,
                ).limit(5)
            )
            approved_thoughts = result.scalars().all()
            
            # Check if this specific thought type was approved
            type_approved = any(t.thought_type == thought_type for t in approved_thoughts)
            if type_approved:
                self._auto_approve_cache[specific_sig] = True
                self._auto_approve_cache[pattern_sig] = True
                return {
                    "status": "auto_approved",
                    "signature": specific_sig,
                    "action": "execute",
                    "reason": f"Thought type '{thought_type}' previously approved",
                }
            
            # New thought — save for user review
            thought = AgentThought(
                agent_id=agent_id,
                agent_name=agent_name,
                tender_id=tender_id,
                thought_type=thought_type,
                title=title,
                description=description,
                evidence=evidence,
                impact=impact,
                confidence=confidence,
                status="pending",
            )
            s.add(thought)
            await s.flush()
            thought_id = thought.id
            await s.commit()
            
            logger.info(f"💡 New thought from {agent_name}: '{title}' (impact: {impact})")
            
            # Notify brain about new pending thought
            if self.brain:
                asyncio.create_task(
                    self.brain.broadcast(
                        sender_id="thought-engine",
                        subject="new_pending_thought",
                        body={
                            "thought_id": thought_id,
                            "agent_id": agent_id,
                            "agent_name": agent_name,
                            "title": title,
                            "thought_type": thought_type,
                            "impact": impact,
                            "confidence": confidence,
                        }
                    )
                )
            
            return {
                "status": "pending_review",
                "thought_id": thought_id,
                "action": "waiting_for_approval",
                "message": f"New insight saved for your review: {title}",
            }
    
    async def approve(self, thought_id: str, comment: str = "") -> Dict:
        """User approves a thought — stores the approval signature."""
        session = get_session()
        async with session as s:
            from sqlalchemy import select
            result = await s.execute(
                select(AgentThought).where(AgentThought.id == thought_id)
            )
            thought = result.scalar_one_or_none()
            if not thought:
                return {"status": "error", "message": "Thought not found"}
            
            thought.status = "approved"
            thought.reviewer_comment = comment
            thought.approved_at = datetime.now(timezone.utc)
            await s.commit()
            
            # Cache the approval signature
            sig = ThoughtSignature.create_pattern(thought.agent_id, thought.thought_type)
            self._auto_approve_cache[sig] = True
            
            logger.info(f"✅ Thought approved: {thought.title}")
            
            # Notify agents that approval was granted
            if self.brain:
                asyncio.create_task(
                    self.brain.broadcast(
                        sender_id="thought-engine",
                        subject="thought_approved",
                        body={
                            "thought_id": thought_id,
                            "agent_id": thought.agent_id,
                            "agent_name": thought.agent_name,
                            "thought_type": thought.thought_type,
                            "title": thought.title,
                            "signature": sig,
                        }
                    )
                )
            
            return {
                "status": "approved",
                "thought_id": thought_id,
                "signature": sig,
                "message": f"✅ '{thought.title}' approved. Similar future insights will auto-execute.",
            }
    
    async def reject(self, thought_id: str, comment: str = "") -> Dict:
        """User rejects a thought."""
        session = get_session()
        async with session as s:
            from sqlalchemy import select
            result = await s.execute(
                select(AgentThought).where(AgentThought.id == thought_id)
            )
            thought = result.scalar_one_or_none()
            if not thought:
                return {"status": "error", "message": "Thought not found"}
            
            thought.status = "rejected"
            thought.reviewer_comment = comment
            await s.commit()
            
            logger.info(f"❌ Thought rejected: {thought.title}")
            return {
                "status": "rejected",
                "thought_id": thought_id,
                "message": f"Thought '{thought.title}' rejected.",
            }
    
    async def get_pending(self, agent_id: str = None) -> List[Dict]:
        """Get all pending thoughts awaiting approval."""
        session = get_session()
        async with session as s:
            from sqlalchemy import select
            query = select(AgentThought).where(AgentThought.status == "pending").order_by(AgentThought.created_at.desc())
            if agent_id:
                query = query.where(AgentThought.agent_id == agent_id)
            result = await s.execute(query.limit(50))
            thoughts = []
            for t in result.scalars():
                thoughts.append({
                    "id": t.id,
                    "agent_id": t.agent_id,
                    "agent_name": t.agent_name,
                    "thought_type": t.thought_type,
                    "title": t.title,
                    "description": t.description,
                    "impact": t.impact,
                    "confidence": t.confidence,
                    "evidence": t.evidence,
                    "tender_id": t.tender_id,
                    "created_at": str(t.created_at) if t.created_at else "",
                })
            return thoughts
    
    async def get_history(self, status: str = "approved", limit: int = 20) -> List[Dict]:
        """Get thought history."""
        session = get_session()
        async with session as s:
            from sqlalchemy import select
            result = await s.execute(
                select(AgentThought).where(AgentThought.status == status)
                .order_by(AgentThought.updated_at.desc()).limit(limit)
            )
            thoughts = []
            for t in result.scalars():
                thoughts.append({
                    "id": t.id,
                    "agent_id": t.agent_id,
                    "agent_name": t.agent_name,
                    "thought_type": t.thought_type,
                    "title": t.title,
                    "impact": t.impact,
                    "status": t.status,
                    "reviewer_comment": t.reviewer_comment,
                    "created_at": str(t.created_at) if t.created_at else "",
                    "approved_at": str(t.approved_at) if t.approved_at else "",
                })
            return thoughts
    
    def get_stats(self) -> Dict:
        """Get thought engine statistics."""
        return {
            "cached_approvals": len(self._auto_approve_cache),
        }
