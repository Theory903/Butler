"""Butler Session Store — Phase 11.

Postgres-backed conversation history store.
Wraps the existing ConversationTurn ORM model.

Provides:
  - append_turn()       — write a turn (user/assistant/tool/system)
  - get_history()       — fetch turns for a session, newest-first optional
  - search()            — pg_trgm similarity search across content
  - delete_session()    — GDPR-friendly wipe of a session's turns
  - session_count()     — how many turns in a session (for context budget)

Account-scoping:
  Every method takes account_id. Queries are always filtered by account_id
  so users can never read each other's sessions, even if they know a session_id.

Replaces Hermes's SQLite SessionDB (hermes_state.py) with Postgres.
Production: pg_trgm extension required for search(). Dev/test: falls back
to ILIKE when pg_trgm is not installed.

Design note:
  This store owns *only* the conversation-turn dimension of memory.
  Semantic memory (embeddings, recall) lives in ButlerMemoryStore.
  The split is intentional — conversation history is structured / auditable,
  semantic memory is probabilistic / recall-based.
"""

from __future__ import annotations

import uuid
from datetime import datetime, UTC
from typing import Literal

import structlog
from sqlalchemy import select, delete, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from domain.memory.models import ConversationTurn
from infrastructure.database import get_session as get_db_session

logger = structlog.get_logger(__name__)

Role = Literal["user", "assistant", "system", "tool"]


class ButlerSessionStore:
    """Postgres-backed conversation turn store.

    Usage:
        store = ButlerSessionStore()
        turn = await store.append_turn(
            account_id="acc_123",
            session_id="sess_abc",
            role="user",
            content="Book me a flight to Tokyo",
        )
        history = await store.get_history("acc_123", "sess_abc")
    """

    async def append_turn(
        self,
        account_id: str | uuid.UUID,
        session_id: str,
        role: Role,
        content: str,
        *,
        intent: str | None = None,
        tool_calls: dict | None = None,
        metadata: dict | None = None,
    ) -> ConversationTurn:
        """Write a conversation turn to Postgres.

        turn_index is auto-computed as (current max + 1).
        """
        _account_id = uuid.UUID(str(account_id)) if isinstance(account_id, str) else account_id

        async with get_db_session() as session:
            # Compute next turn_index atomically
            result = await session.execute(
                select(func.coalesce(func.max(ConversationTurn.turn_index), -1))
                .where(
                    ConversationTurn.account_id == _account_id,
                    ConversationTurn.session_id == session_id,
                )
            )
            last_index: int = result.scalar_one()
            next_index = last_index + 1

            turn = ConversationTurn(
                id=uuid.uuid4(),
                account_id=_account_id,
                session_id=session_id,
                role=role,
                content=content,
                turn_index=next_index,
                intent=intent,
                tool_calls=tool_calls,
                metadata_col=metadata or {},
                created_at=datetime.now(UTC),
            )
            session.add(turn)
            await session.commit()
            await session.refresh(turn)

        logger.debug(
            "session_turn_appended",
            account_id=str(account_id),
            session_id=session_id,
            role=role,
            turn_index=next_index,
        )
        return turn

    async def get_history(
        self,
        account_id: str | uuid.UUID,
        session_id: str,
        *,
        limit: int = 50,
        reverse: bool = False,
    ) -> list[ConversationTurn]:
        """Fetch conversation turns for a session.

        Args:
            account_id: Owner account (enforced — never cross-account).
            session_id: Session identifier.
            limit:      Maximum turns to return (default 50).
            reverse:    If True, return newest-first (default: chronological).

        Returns:
            List of ConversationTurn ORM objects ordered by turn_index.
        """
        _account_id = uuid.UUID(str(account_id)) if isinstance(account_id, str) else account_id

        async with get_db_session() as session:
            q = (
                select(ConversationTurn)
                .where(
                    ConversationTurn.account_id == _account_id,
                    ConversationTurn.session_id == session_id,
                )
                .order_by(
                    ConversationTurn.turn_index.desc()
                    if reverse
                    else ConversationTurn.turn_index.asc()
                )
                .limit(limit)
            )
            result = await session.execute(q)
            turns = list(result.scalars().all())

        return turns

    async def search(
        self,
        account_id: str | uuid.UUID,
        query: str,
        *,
        limit: int = 20,
        session_id: str | None = None,
    ) -> list[ConversationTurn]:
        """Full-text search across conversation history.

        Primary:  pg_trgm similarity search (requires pg_trgm extension).
        Fallback: ILIKE substring match (always available).

        Args:
            account_id: Owner account (enforced).
            query:      Search query string.
            limit:      Max results.
            session_id: Optionally restrict to a single session.
        """
        _account_id = uuid.UUID(str(account_id)) if isinstance(account_id, str) else account_id

        async with get_db_session() as session:
            try:
                # Try pg_trgm similarity search first
                filters = [
                    ConversationTurn.account_id == _account_id,
                    text("content % :q").bindparams(q=query),
                ]
                if session_id:
                    filters.append(ConversationTurn.session_id == session_id)

                q = (
                    select(ConversationTurn)
                    .where(*filters)
                    .order_by(text("similarity(content, :q) DESC").bindparams(q=query))
                    .limit(limit)
                )
                result = await session.execute(q)
                turns = list(result.scalars().all())

            except Exception:
                # Fallback: ILIKE (no pg_trgm required)
                logger.debug("session_search_trgm_unavailable_using_ilike")
                filters = [
                    ConversationTurn.account_id == _account_id,
                    ConversationTurn.content.ilike(f"%{query}%"),
                ]
                if session_id:
                    filters.append(ConversationTurn.session_id == session_id)

                q = (
                    select(ConversationTurn)
                    .where(*filters)
                    .order_by(ConversationTurn.created_at.desc())
                    .limit(limit)
                )
                result = await session.execute(q)
                turns = list(result.scalars().all())

        return turns

    async def delete_session(
        self,
        account_id: str | uuid.UUID,
        session_id: str,
    ) -> int:
        """Delete all turns for a session (GDPR wipe).

        Returns number of rows deleted.
        """
        _account_id = uuid.UUID(str(account_id)) if isinstance(account_id, str) else account_id

        async with get_db_session() as session:
            result = await session.execute(
                delete(ConversationTurn).where(
                    ConversationTurn.account_id == _account_id,
                    ConversationTurn.session_id == session_id,
                )
            )
            await session.commit()
            deleted = result.rowcount

        logger.info("session_deleted", account_id=str(account_id), session_id=session_id, rows=deleted)
        return deleted

    async def session_count(
        self,
        account_id: str | uuid.UUID,
        session_id: str,
    ) -> int:
        """Return total turn count for a session (for context budget estimation)."""
        _account_id = uuid.UUID(str(account_id)) if isinstance(account_id, str) else account_id

        async with get_db_session() as session:
            result = await session.execute(
                select(func.count(ConversationTurn.id)).where(
                    ConversationTurn.account_id == _account_id,
                    ConversationTurn.session_id == session_id,
                )
            )
            return result.scalar_one()

    async def list_sessions(
        self,
        account_id: str | uuid.UUID,
        *,
        limit: int = 100,
    ) -> list[dict]:
        """List all distinct session IDs for an account with last-activity timestamp."""
        _account_id = uuid.UUID(str(account_id)) if isinstance(account_id, str) else account_id

        async with get_db_session() as session:
            result = await session.execute(
                select(
                    ConversationTurn.session_id,
                    func.count(ConversationTurn.id).label("turn_count"),
                    func.max(ConversationTurn.created_at).label("last_active"),
                )
                .where(ConversationTurn.account_id == _account_id)
                .group_by(ConversationTurn.session_id)
                .order_by(text("last_active DESC"))
                .limit(limit)
            )
            rows = result.all()

        return [
            {
                "session_id": row.session_id,
                "turn_count": row.turn_count,
                "last_active": row.last_active.isoformat() if row.last_active else None,
            }
            for row in rows
        ]
