"""
Legacy-compatibility shim for the database layer.

All 40+ consumers that import from ``app.db.base`` continue to work unchanged.
Under the hood, these functions delegate to ``app.db.database`` (PostgreSQL-only),
and ``init_db`` creates tables from BOTH the main ORM models (``app.db.models``)
and the intelligence models (``app.models``).
"""

from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from dotenv import load_dotenv
from pathlib import Path


class Base(DeclarativeBase):
    """Kept for backward compat — no models are mapped to this Base."""
    pass


# ---------------------------------------------------------------------------
# Lazy-forward to the canonical database module
# ---------------------------------------------------------------------------
def _canonical():
    from app.db import database
    return database


def get_database_url() -> str:
    """Return the resolved async database URL (PostgreSQL)."""
    return _canonical().DATABASE_URL


engine = None
_session_factory = None


def get_engine():
    """Return the singleton async engine from the canonical module."""
    global engine
    if engine is None:
        engine = _canonical().get_engine()
    return engine


def get_session_factory():
    """Return an async session factory bound to the canonical engine."""
    global _session_factory
    if _session_factory is None:
        eng = get_engine()
        _session_factory = async_sessionmaker(
            eng,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def init_db():
    """
    Create all tables from BOTH model sets:
      - app.db.models.Base  (33+ tables: Tendors, Awards, APP, Users, …)
      - app.models.Base      (intelligence tables: ContractorDNA, …)
    """
    # 1. Main ORM models
    from app.db import database
    await database.init_db()

    # 2. Intelligence models
    from app.models import Base as IntelBase
    eng = get_engine()
    async with eng.begin() as conn:
        await conn.run_sync(IntelBase.metadata.create_all)


async def close_db():
    """Dispose the engine via the canonical module."""
    global engine, _session_factory
    engine = None
    _session_factory = None
    await _canonical().close_db()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async session."""
    sf = get_session_factory()
    async with sf() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db() -> AsyncSession:
    """Alias for get_async_session (returns first session)."""
    async for session in get_async_session():
        return session
