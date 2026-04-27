"""Database infrastructure — SQLAlchemy async engine, routing, and outbox.
Production-ready for 1M user scale with enhanced connection pooling.
"""

from __future__ import annotations

import contextvars
import logging
from collections.abc import Mapping
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import QueuePool

from infrastructure.config import settings

import structlog

logger = structlog.get_logger(__name__)

# Thread-safe context var to hold the current tenant_id for RLS propagation
# This is set by TenantContextMiddleware and used for tenant isolation
tenant_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("tenant_id", default=None)

# Legacy context var for account_id (deprecated, use tenant_id)
tenant_account_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "tenant_account_id", default=None
)


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base used by all domain models."""


# Enhanced connection pooling for 1M user scale
# Pool configuration optimized for high concurrency (10K RPS)
engine = create_async_engine(
    settings.DATABASE_URL,
    # Pool size: 100 connections per pod for high concurrency
    pool_size=getattr(settings, "DATABASE_POOL_SIZE", 100),
    # Max overflow: 200 additional connections during spikes
    max_overflow=getattr(settings, "DATABASE_MAX_OVERFLOW", 200),
    # Pool timeout: 30 seconds to get a connection
    pool_timeout=getattr(settings, "DATABASE_POOL_TIMEOUT", 30),
    # Pool recycle: 1 hour to recycle connections
    pool_recycle=getattr(settings, "DATABASE_POOL_RECYCLE", 3600),
    # Pool pre-ping: Verify connections before use
    pool_pre_ping=True,
    # Echo: Only in debug mode
    echo=settings.DEBUG,
    # Note: Async engine uses AsyncAdaptedQueuePool by default, do not specify poolclass
)

# Sync engine for APScheduler SQLAlchemyJobStore (which is synchronous)
# Enhanced pooling for 1M user scale
sync_engine = create_engine(
    settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2"),
    pool_size=getattr(settings, "DATABASE_POOL_SIZE", 100),
    max_overflow=getattr(settings, "DATABASE_MAX_OVERFLOW", 200),
    pool_timeout=getattr(settings, "DATABASE_POOL_TIMEOUT", 30),
    pool_recycle=getattr(settings, "DATABASE_POOL_RECYCLE", 3600),
    pool_pre_ping=True,
    echo=settings.DEBUG,
    poolclass=QueuePool,
)

# Optional replica engine mapping with enhanced pooling
engine_replica = None
if hasattr(settings, "DATABASE_REPLICA_URL") and settings.DATABASE_REPLICA_URL:
    engine_replica = create_async_engine(
        settings.DATABASE_REPLICA_URL,
        pool_size=getattr(settings, "DATABASE_POOL_SIZE", 100),
        max_overflow=getattr(settings, "DATABASE_MAX_OVERFLOW", 200),
        pool_timeout=getattr(settings, "DATABASE_POOL_TIMEOUT", 30),
        pool_recycle=getattr(settings, "DATABASE_POOL_RECYCLE", 3600),
        pool_pre_ping=True,
        echo=settings.DEBUG,
        # Note: Async engine uses AsyncAdaptedQueuePool by default, do not specify poolclass
    )

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async_replica_session_factory = async_sessionmaker(
    engine_replica if engine_replica else engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# --- Replica Routing ---
class ReplicaRouter:
    """Intelligently routes reads to Replica vs Primary based on Query Context."""

    def __init__(self, primary_engine, replica_engine=None):
        self.primary = primary_engine
        self.replica = replica_engine

    def resolve_target(self, query_context: Mapping[str, Any]) -> str:
        """Returns 'primary' or 'replica' based on consistency properties."""
        if not self.replica:
            return "primary"

        if query_context.get("consistency") == "strong":
            return "primary"

        if query_context.get("read_after_write") is True:
            return "primary"

        if query_context.get("allow_stale") is True:
            return "replica"

        # Default fallback
        return "primary"


global_router = ReplicaRouter(engine, engine_replica)


# --- Outbox Transactional Support ---
async def write_with_outbox(
    db: AsyncSession,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: dict,
    target_topic: str,
):
    """
    Transactional Outbox helper. Must be executed within an async db.transaction().
    Ensures that domain writes and generic message queue pushing exist in the exact same atomic transaction boundary.
    """
    from domain.events.models import OutboxEvent  # Lazy load to prevent circular initialization

    outbox = OutboxEvent(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
        target_topic=target_topic,
    )
    db.add(outbox)
    await db.flush()  # Buffer it into the open PG transaction stream so it guarantees single-commit


# --- Row Level Security Lifecycle ---
@event.listens_for(engine.sync_engine, "before_cursor_execute")
def receive_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """
    Intercepts physical PG execution checkout.
    Queries the python local context to determine if 'tenant_id' or 'tenant_account_id' is set.
    If so, binds it to the Postgres local session for RLS:
    - app.tenant_id for new multi-tenant isolation
    - app.current_account_id for legacy compatibility
    """
    # Use contextvars safely
    try:
        tid = tenant_id.get()
    except (LookupError, AttributeError):
        tid = None

    try:
        aid = tenant_account_id.get()
    except (LookupError, AttributeError):
        aid = None

    if tid:
        # Set tenant_id for new RLS policies
        cursor.execute(f"SET LOCAL app.tenant_id = '{tid}';")

    if aid:
        # Set account_id for legacy RLS policies (deprecated)
        cursor.execute(f"SET LOCAL app.current_account_id = '{aid}';")


async def get_session():
    """Yield an async SQLAlchemy session pointing to the primary router (used as FastAPI dependency)."""
    async with async_session_factory() as session:
        yield session


async def get_replica_session():
    """Yield a potentially stale but hyper-performant readonly session."""
    async with async_replica_session_factory() as session:
        yield session


async def init_db() -> None:
    """Initialize database connection and log pool status for 1M scale monitoring."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))

    # Log connection pool status for monitoring
    pool = engine.pool
    pool_size = pool.size()
    checked_out = pool.checkedout()
    logger.info(f"database_pool_initialized: size={pool_size}, checked_out={checked_out}")

    if engine_replica:
        replica_pool = engine_replica.pool
        replica_size = replica_pool.size()
        replica_checked = replica_pool.checkedout()
        logger.info(
            f"database_replica_pool_initialized: size={replica_size}, checked_out={replica_checked}"
        )


async def close_db() -> None:
    """Close database connections gracefully."""
    await engine.dispose()
    if engine_replica:
        await engine_replica.dispose()


async def get_pool_status() -> dict:
    """Get connection pool status for monitoring at 1M scale."""
    pool = engine.pool
    status = {
        "primary": {
            "size": pool.size(),
            "checked_out": pool.checkedout(),
            "available": pool.size() - pool.checkedout(),
        }
    }

    if engine_replica:
        replica_pool = engine_replica.pool
        status["replica"] = {
            "size": replica_pool.size(),
            "checked_out": replica_pool.checkedout(),
            "available": replica_pool.size() - replica_pool.checkedout(),
        }

    return status
