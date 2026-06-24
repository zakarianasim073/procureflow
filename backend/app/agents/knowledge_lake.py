"""
Agent 25 — Knowledge Lake Agent
Central data persistence and retrieval — stores all agent outputs, enables learning, and provides historical analysis.
"""

from __future__ import annotations

import json
import logging
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


class KnowledgeLakeAgent(BaseAgent):
    agent_id = "agent-025-knowledge-lake"
    agent_name = "Knowledge Lake Agent"
    description = "Central knowledge store that persists all agent outputs, enables historical analysis, and feeds the learning system."
    dependencies: List[str] = []
    version = "2.0.0"

    def __init__(self):
        super().__init__()

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        action = context.get("action", "store")
        tender_id = context.get("tender_id", "unknown")
        data = context.get("data", {})
        entry_type = context.get("entry_type", "tender")

        if action == "store":
            result = await self._store_knowledge(entry_type, tender_id, data)
        elif action == "retrieve":
            result = await self._retrieve_knowledge(entry_type, tender_id)
        elif action == "cleanup":
            result = await self._cleanup_old_data()
        elif action == "stats":
            result = await self._get_knowledge_stats()
        else:
            result = {"error": f"Unknown action: {action}"}

        return AgentResult(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            output=result,
        )

    async def _store_knowledge(self, entry_type: str, tender_id: str, data: Dict) -> Dict:
        """Store knowledge entry to the knowledge lake."""
        import hashlib
        from datetime import datetime
        from app.db.base import get_session_factory
        from app.models.intelligence import KnowledgeEntry
        from sqlalchemy import select
        import uuid

        # Create checksum for deduplication
        data_str = json.dumps(data, sort_keys=True, default=str)
        checksum = hashlib.md5(data_str.encode()).hexdigest()

        sf = get_session_factory()
        async with sf() as session:
            stmt = select(KnowledgeEntry).where(
                KnowledgeEntry.entry_type == entry_type,
                KnowledgeEntry.tender_id == tender_id
            )
            res = await session.execute(stmt)
            entry = res.scalar_one_or_none()

            if entry:
                entry.data = data
                entry.checksum = checksum
                entry.stored_at = datetime.utcnow()
            else:
                entry = KnowledgeEntry(
                    id=str(uuid.uuid4()),
                    entry_type=entry_type,
                    tender_id=tender_id,
                    data=data,
                    checksum=checksum,
                    stored_at=datetime.utcnow()
                )
                session.add(entry)
            
            await session.commit()

        return {
            "status": "stored",
            "entry_type": entry_type,
            "tender_id": tender_id,
            "checksum": checksum,
        }

    async def _retrieve_knowledge(self, entry_type: str, tender_id: str) -> Dict:
        """Retrieve knowledge entry from the knowledge lake."""
        from app.db.base import get_session_factory
        from app.models.intelligence import KnowledgeEntry
        from sqlalchemy import select

        sf = get_session_factory()
        async with sf() as session:
            stmt = select(KnowledgeEntry).where(
                KnowledgeEntry.entry_type == entry_type,
                KnowledgeEntry.tender_id == tender_id
            )
            res = await session.execute(stmt)
            entry = res.scalar_one_or_none()

            if not entry:
                # Try to find similar entries
                stmt_similar = select(KnowledgeEntry.tender_id).where(
                    KnowledgeEntry.entry_type == entry_type
                ).order_by(KnowledgeEntry.stored_at.desc()).limit(10)
                res_similar = await session.execute(stmt_similar)
                entries = [r[0] for r in res_similar.all()]
                return {
                    "status": "not_found",
                    "entry_type": entry_type,
                    "tender_id": tender_id,
                    "available_entries": len(entries),
                    "entries": entries,
                }

            return {
                "status": "found",
                "entry": {
                    "entry_type": entry.entry_type,
                    "tender_id": entry.tender_id,
                    "data": entry.data,
                    "stored_at": entry.stored_at.isoformat(),
                    "checksum": entry.checksum,
                },
            }

    async def _cleanup_old_data(self, max_age_days: int = 30) -> Dict:
        """Clean up old temporary knowledge entries."""
        from datetime import datetime, timedelta
        from app.db.base import get_session_factory
        from app.models.intelligence import KnowledgeEntry
        from sqlalchemy import delete

        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
        sf = get_session_factory()
        async with sf() as session:
            stmt = delete(KnowledgeEntry).where(KnowledgeEntry.stored_at < cutoff)
            res = await session.execute(stmt)
            cleaned = res.rowcount
            await session.commit()

        return {
            "status": "cleanup_completed",
            "entries_removed": cleaned,
            "max_age_days": max_age_days,
        }

    async def _get_knowledge_stats(self) -> Dict:
        """Get statistics about stored knowledge."""
        from app.db.base import get_session_factory
        from app.models.intelligence import KnowledgeEntry
        from sqlalchemy import select, func

        stats = {}
        total_entries = 0

        sf = get_session_factory()
        async with sf() as session:
            stmt = select(KnowledgeEntry.entry_type, func.count(KnowledgeEntry.id)).group_by(KnowledgeEntry.entry_type)
            res = await session.execute(stmt)
            for entry_type, count in res.all():
                stats[entry_type] = count
                total_entries += count

        return {
            "total_entries": total_entries,
            "by_type": stats,
            "storage_path": "postgresql",
        }

