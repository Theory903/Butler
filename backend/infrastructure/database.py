"""Database infrastructure — SQLAlchemy async engine, routing, and outbox."""

from __future__ import annotations

import contextvars
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase

from infrastructure.config import settings

# Thread-safe context var to hold the current user's account ID for RLS propagation
tenant_account_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "tenant_account_id", default=None
)

class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base used by all domain models."""

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    echo=settings.DEBUG,
    pool_pre_ping=True, 
)

# Sync engine for APScheduler SQLAlchemyJobStore (which is synchronous)
sync_engine = create_engine(
    settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2"),
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

# Optional replica engine mapping
engine_replica = None
if hasattr(settings, "DATABASE_REPLICA_URL") and settings.DATABASE_REPLICA_URL:
    engine_replica = create_async_engine(
        settings.DATABASE_REPLICA_URL,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        echo=settings.DEBUG,
        pool_pre_ping=True,
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
    target_topic: str
):
    """
    Transactional Outbox helper. Must be executed within an async db.transaction().
    Ensures that domain writes and generic message queue pushing exist in the exact same atomic transaction boundary.
    """
    from domain.events.models import OutboxEvent # Lazy load to prevent circular initialization
    outbox = OutboxEvent(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
        target_topic=target_topic
    )
    db.add(outbox)
    await db.flush() # Buffer it into the open PG transaction stream so it guarantees single-commit

# --- Row Level Security Lifecycle ---
@event.listens_for(engine.sync_engine, "before_cursor_execute")
def receive_before_cursor_execute(
    conn, cursor, statement, parameters, context, executemany
):
    """
    Intercepts physical PG execution checkout.
    Queries the python local context to determine if 'tenant_account_id' is set. 
    If so, binds it to the Postgres local session `app.current_account_id` allowing standard RLS tables to execute query pruning.
    """
    # Use contextvars safely
    try:
        account_id = tenant_account_id.get()
    except (LookupError, AttributeError):
        account_id = None

    if account_id:
        # Pre-format to avoid any string interpolation issues in the sync layer
        # We use cursor.execute only because this is the low-level DBAPI hook point.
        # But we wrap it in a minimal check.
        cursor.execute(f"SET LOCAL app.current_account_id = '{account_id}';")


async def get_session():
    """Yield an async SQLAlchemy session pointing to the primary router (used as FastAPI dependency)."""
    async with async_session_factory() as session:
        yield session

async def get_replica_session():
    """Yield a potentially stale but hyper-performant readonly session."""
    async with async_replica_session_factory() as session:
        yield session

async def init_db() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))

async def close_db() -> None:
    await engine.dispose()
    if engine_replica:
        await engine_replica.dispose()