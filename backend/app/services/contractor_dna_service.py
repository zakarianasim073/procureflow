"""
Contractor DNA Service — DB-backed, replaces JSON file reads.
Queries PostgreSQL via IntelligenceDataService for all contractor profiles.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.services.intelligence_data_service import IntelligenceDataService

logger = logging.getLogger(__name__)

# Module-level cache for fast access without DB in every request
_cache: Dict[str, Any] = {"contractors": None, "stats": None}


def invalidate_cache() -> None:
    _cache["contractors"] = None
    _cache["stats"] = None


async def load_contractors(db=None) -> List[Dict[str, Any]]:
    """Return all contractor profiles from DB (cached)."""
    if _cache["contractors"] is not None:
        return _cache["contractors"]
    if db is None:
        logger.warning("No DB session provided, returning empty list")
        return []
    svc = IntelligenceDataService(db)
    contractors = await svc.list_contractors(limit=5000)
    _cache["contractors"] = contractors
    return contractors


async def get_contractor(identifier: str, db=None) -> Optional[Dict[str, Any]]:
    """Find a contractor by name or ID from DB."""
    if db is None:
        return None
    svc = IntelligenceDataService(db)
    return await svc.get_contractor(identifier)


async def search_contractors(query: str, limit: int = 20, db=None) -> List[Dict[str, Any]]:
    """Search contractors by name from DB."""
    if db is None:
        return []
    svc = IntelligenceDataService(db)
    return await svc.search_contractors(query, limit)


async def get_contractor_stats(db=None) -> Dict[str, Any]:
    """Compute aggregate stats from DB."""
    if _cache["stats"] is not None:
        return _cache["stats"]
    if db is None:
        return {}
    svc = IntelligenceDataService(db)
    stats = await svc.get_contractor_stats()
    # Enhance with top contractors
    top = await svc.list_contractors(limit=5)
    stats["top_by_amount"] = [
        {"name": c.get("contractor_name", ""), "amount": c.get("total_amount_bdt", 0)}
        for c in top
    ]
    _cache["stats"] = stats
    return stats
