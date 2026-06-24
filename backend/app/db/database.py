"""
Database connection and session management.
PostgreSQL-only backend.
"""
import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager, contextmanager
from urllib.parse import quote_plus
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncEngine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import event, Engine, text

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(Path(_PROJECT_ROOT).parent / ".env")


def _build_postgres_urls() -> tuple[str, str]:
    user = os.getenv("POSTGRES_USER", os.getenv("PGUSER", "postgres"))
    password = os.getenv("POSTGRES_PASSWORD", os.getenv("PGPASSWORD", "procurementflow"))
    host = os.getenv("POSTGRES_HOST", os.getenv("PGHOST", "localhost"))
    port = os.getenv("POSTGRES_PORT", os.getenv("PGPORT", "5432"))
    database = os.getenv("POSTGRES_DB", os.getenv("PGDATABASE", "procureflow_bd"))
    safe_password = quote_plus(password)
    async_url = f"postgresql+asyncpg://{user}:{safe_password}@{host}:{port}/{database}"
    sync_url = f"postgresql+psycopg2://{user}:{safe_password}@{host}:{port}/{database}"
    return async_url, sync_url


def _resolve_database_urls() -> tuple[str, str]:
    explicit_async = os.getenv("DATABASE_URL")
    explicit_sync = os.getenv("SYNC_DATABASE_URL")
    if explicit_async and explicit_sync:
        return explicit_async, explicit_sync
    if explicit_async and not explicit_sync:
        return explicit_async, explicit_async.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    if explicit_sync and not explicit_async:
        return explicit_sync.replace("postgresql+psycopg2://", "postgresql+asyncpg://"), explicit_sync
    return _build_postgres_urls()


DATABASE_URL, SYNC_DATABASE_URL = _resolve_database_urls()

_engine: AsyncEngine | None = None
_sync_engine: Engine | None = None
_session_factory = None
_sync_session_factory = None


def get_database_backend() -> str:
    if DATABASE_URL.startswith("postgresql"):
        return "postgresql"
    return "unknown"


def get_database_summary() -> dict:
    return {
        "backend": "postgresql",
        "host": os.getenv("POSTGRES_HOST", os.getenv("PGHOST", "localhost")),
        "port": os.getenv("POSTGRES_PORT", os.getenv("PGPORT", "5432")),
        "database": os.getenv("POSTGRES_DB", os.getenv("PGDATABASE", "procureflow_bd")),
        "user": os.getenv("POSTGRES_USER", os.getenv("PGUSER", "postgres")),
    }


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            DATABASE_URL,
            echo=os.getenv("SQL_ECHO", "false").lower() == "true",
            future=True,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        logger.info("Database engine created: %s", get_database_summary())
    return _engine


def get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        from sqlalchemy import create_engine as sync_create
        _sync_engine = sync_create(
            SYNC_DATABASE_URL,
            echo=os.getenv("SQL_ECHO", "false").lower() == "true",
            future=True,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
    return _sync_engine


def get_sync_session():
    """Return a reusable synchronous SQLAlchemy Session."""
    global _sync_session_factory
    if _sync_session_factory is None:
        _sync_session_factory = sessionmaker(
            get_sync_engine(),
            expire_on_commit=False,
        )
    return _sync_session_factory()


@contextmanager
def session_scope():
    """Provide a transactional scope around a synchronous session."""
    session = get_sync_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def init_db():
    from .models import Base
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")


async def close_db():
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
        logger.info("Database connections closed")


def get_session() -> AsyncSession:
    """Get a new async session."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory()


@asynccontextmanager
async def get_async_session():
    session = get_session()
    try:
        yield session
    finally:
        await session.close()


async def check_database_health() -> dict:
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "healthy", "backend": "postgresql"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e), "backend": "postgresql"}


@event.listens_for(Engine, "connect")
def _set_pg_connection_options(dbapi_connection, connection_record):
    """Set PostgreSQL session options on new connections."""
    if hasattr(dbapi_connection, "cursor"):
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("SET statement_timeout = '300s'")
            cursor.close()
        except Exception as e:
            logger.warning("Failed to set PG connection options: %s", e)
