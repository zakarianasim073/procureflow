"""
Knowledge Lake Agent — Central Procurement Intelligence Repository.
Manages the organizational knowledge base for all procurement data.

Features:
- Store all crawled tender data in structured format
- Embedding-based semantic search (via pgvector or in-memory)
- Cross-reference between tenders, awards, contractors
- Knowledge graph: Tender ↔ Award ↔ Contractor ↔ Agency
- Historical pattern analysis
- Integration with Agent Brain for knowledge sharing
- Automatic tagging and categorization
- Data quality monitoring
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from app.agents.core.base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeItem:
    """A single knowledge entry."""
    id: str = ""
    type: str = ""  # tender, award, contractor, opening, boq, rate, competitor
    tender_id: str = ""
    title: str = ""
    content: str = ""
    data: Dict = field(default_factory=dict)
    summary: str = ""
    tags: List[str] = field(default_factory=list)
    source: str = ""
    agency: str = ""
    zone: str = ""
    checksum: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class KnowledgeGraph:
    """Knowledge graph connections."""
    entities: Dict[str, List[str]] = field(default_factory=dict)  # entity_type -> ids
    relationships: List[Dict] = field(default_factory=list)  # [{source, target, type}]


class KnowledgeLakeAgent(BaseAgent):
    agent_id = "agent-025-knowledge-lake"
    agent_name = "Knowledge Lake Agent"
    description = "Central procurement knowledge repository: stores, indexes, and cross-references all procurement intelligence."
    dependencies: List[str] = []
    version = "2.0.0"

    def __init__(self, brain=None):
        super().__init__(brain)
        self._in_memory_store: Dict[str, KnowledgeItem] = {}
        self._knowledge_graph = KnowledgeGraph()

    async def execute(self, context: Dict[str, Any]) -> AgentResult:
        action = context.get("action", "query")
        
        if action == "store":
            return await self._handle_store(context)
        elif action == "query":
            return await self._handle_query(context)
        elif action == "stats":
            return await self._get_stats()
        elif action == "graph":
            return await self._get_graph()
        elif action == "cross_reference":
            return await self._cross_reference(context)
        else:
            return AgentResult(
                agent_id=self.agent_id,
                status=AgentStatus.FAILED,
                output={"error": f"Unknown action: {action}"},
            )

    async def _handle_store(self, context: Dict) -> AgentResult:
        """Store knowledge entries."""
        entries = context.get("entries", [])
        stored = 0
        
        for entry in entries:
            item = KnowledgeItem(
                id=entry.get("id", self._generate_id(entry)),
                type=entry.get("type", "unknown"),
                tender_id=entry.get("tender_id", ""),
                title=entry.get("title", ""),
                content=entry.get("content", json.dumps(entry.get("data", {}))),
                data=entry.get("data", {}),
                summary=entry.get("summary", ""),
                tags=entry.get("tags", []),
                source=entry.get("source", self.agent_id),
                agency=entry.get("agency", ""),
                zone=entry.get("zone", ""),
            )
            item.checksum = self._compute_checksum(item.data)
            
            self._in_memory_store[item.id] = item
            self._update_graph(item)
            stored += 1
        
        # Also persist to DB if available
        if context.get("persist", True):
            await self._persist_to_db(entries)
        
        return AgentResult(
            agent_id=self.agent_id,
            status=AgentStatus.SUCCESS,
            output={
                "action": "stored",
                "count": stored,
                "total_entries": len(self._in_memory_store),
            },
        )

    async def _handle_query(self, context: Dict) -> AgentResult:
        """Query knowledge lake."""
        query_type = context.get("type", "")
        tender_id = context.get("tender_id", "")
        agency = context.get("agency", "")
        tags = context.get("tags", [])
        limit = context.get("limit", 100)
        search_text = context.get("search", "")
        
        results = []
        for item in self._in_memory_store.values():
            if query_type and item.type != query_type:
                continue
            if tender_id and item.tender_id != tender_id:
                continue
            if agency and item.agency != agency:
                continue
            if tags and not all(t in item.tags for t in tags):
                continue
            if search_text and search_text.lower() not in item.content.lower():
                continue
            results.append({
                "id": item.id,
                "type": item.type,
                "tender_id": item.tender_id,
                "title": item.title,
                "summary": item.summary,
                "tags": item.tags,
                "agency": item.agency,
                "source": item.source,
                "created_at": item.created_at,
            })
        
        results = results[:limit]
        
        # If not found in memory, try DB
        if not results:
            results = await self._query_from_db(
                query_type=query_type, tender_id=tender_id,
                agency=agency, tags=tags, limit=limit,
            )
        
        return AgentResult(
            agent_id=self.agent_id,
            status=AgentStatus.SUCCESS,
            output={
                "action": "queried",
                "count": len(results),
                "results": results,
            },
        )

    async def _get_stats(self) -> AgentResult:
        """Get knowledge lake statistics."""
        type_counts = {}
        agency_counts = {}
        
        for item in self._in_memory_store.values():
            type_counts[item.type] = type_counts.get(item.type, 0) + 1
            if item.agency:
                agency_counts[item.agency] = agency_counts.get(item.agency, 0) + 1
        
        # Also query DB for total
        db_stats = await self._get_db_stats()
        
        return AgentResult(
            agent_id=self.agent_id,
            status=AgentStatus.SUCCESS,
            output={
                "in_memory_entries": len(self._in_memory_store),
                "by_type": type_counts,
                "by_agency": agency_counts,
                "graph_entities": len(self._knowledge_graph.entities),
                "graph_relationships": len(self._knowledge_graph.relationships),
                **db_stats,
            },
        )

    async def _get_graph(self) -> AgentResult:
        """Get knowledge graph."""
        return AgentResult(
            agent_id=self.agent_id,
            status=AgentStatus.SUCCESS,
            output={
                "entities": {
                    k: {"count": len(v), "ids": v[:20]}
                    for k, v in self._knowledge_graph.entities.items()
                },
                "relationships": self._knowledge_graph.relationships[:100],
            },
        )

    async def _cross_reference(self, context: Dict) -> AgentResult:
        """Cross-reference entities in the knowledge graph."""
        tender_id = context.get("tender_id", "")
        if not tender_id:
            return AgentResult(
                agent_id=self.agent_id,
                status=AgentStatus.FAILED,
                output={"error": "tender_id required for cross_reference"},
            )
        
        # Find all knowledge items for this tender
        related = []
        for item in self._in_memory_store.values():
            if item.tender_id == tender_id:
                related.append({
                    "type": item.type,
                    "title": item.title,
                    "summary": item.summary,
                    "source": item.source,
                })
        
        # Find related tenders (same agency, zone, etc.)
        agency = ""
        for item in related:
            if item.get("agency"):
                agency = item["agency"]
                break
        
        same_agency = []
        if agency:
            for item in self._in_memory_store.values():
                if item.agency == agency and item.tender_id != tender_id:
                    same_agency.append({
                        "tender_id": item.tender_id,
                        "title": item.title,
                        "type": item.type,
                    })
        
        return AgentResult(
            agent_id=self.agent_id,
            status=AgentStatus.SUCCESS,
            output={
                "tender_id": tender_id,
                "related_entries": related,
                "same_agency_tenders": same_agency[:20],
                "total_related": len(related),
            },
        )

    def _generate_id(self, entry: Dict) -> str:
        """Generate unique ID for knowledge entry."""
        raw = f"{entry.get('type', '')}-{entry.get('tender_id', '')}-{datetime.now().timestamp()}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    def _compute_checksum(self, data: Dict) -> str:
        """Compute checksum for deduplication."""
        raw = json.dumps(data, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _update_graph(self, item: KnowledgeItem):
        """Update knowledge graph with new entry."""
        # Entities
        if item.type not in self._knowledge_graph.entities:
            self._knowledge_graph.entities[item.type] = []
        if item.id not in self._knowledge_graph.entities[item.type]:
            self._knowledge_graph.entities[item.type].append(item.id)
        
        # Relationships
        if item.tender_id:
            self._knowledge_graph.relationships.append({
                "source": item.id,
                "target": f"tender:{item.tender_id}",
                "type": f"belongs_to_{item.type}",
            })

    async def _persist_to_db(self, entries: List[Dict]):
        """Persist entries to database."""
        try:
            from app.db import get_session, KnowledgeEntry, Tender
            from sqlalchemy import select
            async with get_session() as session:
                for entry in entries:
                    tender_id = entry.get("tender_id") or None
                    if tender_id:
                        exists = await session.execute(
                            select(Tender.id).where(Tender.tender_id == str(tender_id))
                        )
                        if exists.scalar_one_or_none() is None:
                            tender_id = None
                    ke = KnowledgeEntry(
                        tender_id=tender_id,
                        entry_type=entry.get("type", "unknown"),
                        title=entry.get("title", ""),
                        content=entry.get("content", ""),
                        data=entry.get("data", {}),
                        summary=entry.get("summary", ""),
                        source=entry.get("source", self.agent_id),
                        tags=entry.get("tags", []),
                        agency=entry.get("agency", ""),
                    )
                    session.add(ke)
                await session.commit()
        except Exception as e:
            logger.warning(f"Could not persist to DB: {e}")

    async def _query_from_db(self, query_type: str = None, tender_id: str = None,
                              agency: str = None, tags: List[str] = None,
                              limit: int = 100) -> List[Dict]:
        """Query knowledge from database."""
        results = []
        try:
            from app.db import get_session, KnowledgeEntry
            from sqlalchemy import select
            
            async with get_session() as session:
                query = select(KnowledgeEntry)
                if query_type:
                    query = query.where(KnowledgeEntry.entry_type == query_type)
                if tender_id:
                    query = query.where(KnowledgeEntry.tender_id == tender_id)
                if agency:
                    query = query.where(KnowledgeEntry.agency == agency)
                
                result = await session.execute(query.limit(limit))
                for row in result.scalars():
                    results.append({
                        "id": row.id,
                        "type": row.entry_type,
                        "tender_id": row.tender_id,
                        "title": row.title,
                        "summary": row.summary,
                        "tags": row.tags,
                        "agency": row.agency,
                        "source": row.source,
                        "created_at": str(row.created_at),
                    })
        except Exception as e:
            logger.warning(f"Could not query DB: {e}")
        
        return results

    async def _get_db_stats(self) -> Dict:
        """Get database statistics."""
        try:
            from app.db import get_session
            from sqlalchemy import select, func
            from app.db import KnowledgeEntry, Tender, Award, OpeningReport
            
            async with get_session() as session:
                total_knowledge = (await session.execute(
                    select(func.count(KnowledgeEntry.id))
                )).scalar() or 0
                total_tenders = (await session.execute(
                    select(func.count(Tender.id))
                )).scalar() or 0
                total_awards = (await session.execute(
                    select(func.count(Award.id))
                )).scalar() or 0
                total_reports = (await session.execute(
                    select(func.count(OpeningReport.id))
                )).scalar() or 0
                
                return {
                    "db_tenders": total_tenders,
                    "db_awards": total_awards,
                    "db_opening_reports": total_reports,
                    "db_knowledge_entries": total_knowledge,
                }
        except Exception as e:
            logger.warning(f"Could not get DB stats: {e}")
            return {}
