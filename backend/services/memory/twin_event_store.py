from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
    and_,
    delete,
    func,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, declarative_base, mapped_column

from services.memory.twin_events import EventEnvelope
from services.memory.twin_repository_contracts import TwinProjectorEventStore

logger = structlog.get_logger(__name__)

Base = declarative_base()


class TwinEventRow(Base):
    """Append-only canonical event log row for the digital twin."""

    __tablename__ = "twin_event_log"

    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    session_id: Mapped[str | None] = mapped_column(
        String(length=255),
        nullable=True,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(
        String(length=128),
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(length=256),
        nullable=True,
        unique=True,
        index=True,
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )

    causation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    correlation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    provenance_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    schema_version: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        default="1.0",
    )

    projected: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )
    projected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    claim_token: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    claim_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    projection_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    last_error: Mapped[str | None] = mapped_column(
        String(length=4000),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


@dataclass(slots=True, frozen=True)
class TwinEventStoreConfig:
    """Config for event store behavior."""

    auto_commit: bool = False
    auto_flush: bool = True
    claim_ttl_seconds: int = 300
    max_batch_size: int = 500


@dataclass(slots=True, frozen=True)
class ClaimedEventBatch:
    """A batch of claimed events for projector workers."""

    claim_token: UUID
    events: list[EventEnvelope]


class PostgresTwinEventStore(TwinProjectorEventStore):
    """PostgreSQL-backed canonical event store for Butler twin events."""

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        config: TwinEventStoreConfig | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._config = config or TwinEventStoreConfig()

    async def append(self, event: EventEnvelope) -> UUID:
        """Append one event idempotently."""
        async with self._session_scope() as session:
            existing = None
            idempotency_key = self._extract_idempotency_key(event)
            if idempotency_key:
                existing = await self._get_by_idempotency_key(session, idempotency_key)

            if existing is not None:
                logger.info(
                    "twin_event_append_deduplicated",
                    event_id=str(existing.event_id),
                    idempotency_key=idempotency_key,
                    user_id=str(existing.user_id),
                )
                return existing.event_id

            row = TwinEventRow(
                event_id=event.event_id,
                user_id=event.user_id,
                session_id=event.session_id,
                event_type=event.event_type.value,
                idempotency_key=idempotency_key,
                occurred_at=self._normalize_dt(event.occurred_at),
                recorded_at=self._normalize_dt(event.recorded_at),
                causation_id=event.causation_id,
                correlation_id=event.correlation_id,
                payload_json=dict(event.payload or {}),
                provenance_json=event.provenance.model_dump(mode="json"),
                metadata_json=dict(event.metadata or {}),
                schema_version=event.schema_version,
                projected=False,
                projection_attempts=0,
            )
            session.add(row)

            logger.info(
                "twin_event_appended",
                event_id=str(event.event_id),
                event_type=event.event_type.value,
                user_id=str(event.user_id),
            )
            return event.event_id

    async def append_many(self, events: Sequence[EventEnvelope]) -> list[UUID]:
        """Append multiple events in one logical transaction."""
        appended: list[UUID] = []

        async with self._session_scope() as session:
            for event in events:
                existing = None
                idempotency_key = self._extract_idempotency_key(event)
                if idempotency_key:
                    existing = await self._get_by_idempotency_key(session, idempotency_key)

                if existing is not None:
                    appended.append(existing.event_id)
                    continue

                row = TwinEventRow(
                    event_id=event.event_id,
                    user_id=event.user_id,
                    session_id=event.session_id,
                    event_type=event.event_type.value,
                    idempotency_key=idempotency_key,
                    occurred_at=self._normalize_dt(event.occurred_at),
                    recorded_at=self._normalize_dt(event.recorded_at),
                    causation_id=event.causation_id,
                    correlation_id=event.correlation_id,
                    payload_json=dict(event.payload or {}),
                    provenance_json=event.provenance.model_dump(mode="json"),
                    metadata_json=dict(event.metadata or {}),
                    schema_version=event.schema_version,
                    projected=False,
                    projection_attempts=0,
                )
                session.add(row)
                appended.append(event.event_id)

            logger.info("twin_events_appended_batch", count=len(appended))
            return appended

    async def get_event(self, event_id: UUID) -> EventEnvelope | None:
        async with self._session_scope() as session:
            row = await session.get(TwinEventRow, event_id)
            return self._row_to_event(row) if row is not None else None

    async def list_events_for_user(
        self,
        user_id: UUID,
        *,
        after_event_id: UUID | None = None,
        after_recorded_at: datetime | None = None,
        limit: int = 500,
        projected: bool | None = None,
    ) -> list[EventEnvelope]:
        """Return user events in stable replay order."""
        async with self._session_scope() as session:
            stmt = select(TwinEventRow).where(TwinEventRow.user_id == user_id)

            if after_recorded_at is not None:
                stmt = stmt.where(TwinEventRow.recorded_at > self._normalize_dt(after_recorded_at))

            if after_event_id is not None:
                ref_row = await session.get(TwinEventRow, after_event_id)
                if ref_row is not None:
                    stmt = stmt.where(
                        (TwinEventRow.recorded_at > ref_row.recorded_at)
                        | (
                            (TwinEventRow.recorded_at == ref_row.recorded_at)
                            & (TwinEventRow.event_id > ref_row.event_id)
                        )
                    )

            if projected is not None:
                stmt = stmt.where(TwinEventRow.projected.is_(projected))

            stmt = stmt.order_by(
                TwinEventRow.recorded_at.asc(),
                TwinEventRow.event_id.asc(),
            ).limit(min(limit, self._config.max_batch_size))

            result = await session.execute(stmt)
            rows = list(result.scalars().all())
            return [self._row_to_event(row) for row in rows]

    async def claim_unprojected(
        self,
        *,
        batch_size: int = 100,
        user_id: UUID | None = None,
    ) -> ClaimedEventBatch:
        """Claim unprojected events safely for one worker."""
        claim_token = uuid4()
        now = datetime.now(UTC)
        claim_expires_at = now + timedelta(seconds=self._config.claim_ttl_seconds)

        async with self._session_scope() as session:
            filters = [
                TwinEventRow.projected.is_(False),
                (
                    (TwinEventRow.claim_token.is_(None))
                    | (TwinEventRow.claim_expires_at.is_(None))
                    | (TwinEventRow.claim_expires_at < now)
                ),
            ]
            if user_id is not None:
                filters.append(TwinEventRow.user_id == user_id)

            stmt = (
                select(TwinEventRow)
                .where(and_(*filters))
                .order_by(TwinEventRow.recorded_at.asc(), TwinEventRow.event_id.asc())
                .limit(min(batch_size, self._config.max_batch_size))
                .with_for_update(skip_locked=True)
            )

            result = await session.execute(stmt)
            rows = list(result.scalars().all())

            if not rows:
                return ClaimedEventBatch(claim_token=claim_token, events=[])

            for row in rows:
                row.claim_token = claim_token
                row.claimed_at = now
                row.claim_expires_at = claim_expires_at
                row.projection_attempts += 1
                row.updated_at = now

            logger.info(
                "twin_events_claimed",
                claim_token=str(claim_token),
                count=len(rows),
                user_id=str(user_id) if user_id else None,
            )

            return ClaimedEventBatch(
                claim_token=claim_token,
                events=[self._row_to_event(row) for row in rows],
            )

    async def acknowledge_projected(
        self,
        claim_token: UUID,
        event_ids: Sequence[UUID],
    ) -> int:
        """Mark a claimed batch as successfully projected."""
        if not event_ids:
            return 0

        now = datetime.now(UTC)

        async with self._session_scope() as session:
            stmt = (
                update(TwinEventRow)
                .where(
                    TwinEventRow.claim_token == claim_token,
                    TwinEventRow.event_id.in_(list(event_ids)),
                )
                .values(
                    projected=True,
                    projected_at=now,
                    claim_token=None,
                    claimed_at=None,
                    claim_expires_at=None,
                    last_error=None,
                    updated_at=now,
                )
            )
            result = await session.execute(stmt)
            affected = int(result.rowcount or 0)

            logger.info(
                "twin_events_acknowledged",
                claim_token=str(claim_token),
                affected=affected,
            )
            return affected

    async def release_claim(
        self,
        claim_token: UUID,
        *,
        error: str | None = None,
    ) -> int:
        """Release a claim without marking rows projected."""
        now = datetime.now(UTC)

        async with self._session_scope() as session:
            stmt = (
                update(TwinEventRow)
                .where(TwinEventRow.claim_token == claim_token)
                .values(
                    claim_token=None,
                    claimed_at=None,
                    claim_expires_at=None,
                    last_error=(error[:4000] if error else None),
                    updated_at=now,
                )
            )
            result = await session.execute(stmt)
            affected = int(result.rowcount or 0)

            logger.warning(
                "twin_event_claim_released",
                claim_token=str(claim_token),
                affected=affected,
                error=error,
            )
            return affected

    async def mark_failed(
        self,
        claim_token: UUID,
        event_id: UUID,
        error: str,
    ) -> bool:
        """Mark one claimed event as failed and return it to retryable state."""
        now = datetime.now(UTC)

        async with self._session_scope() as session:
            stmt = (
                update(TwinEventRow)
                .where(
                    TwinEventRow.claim_token == claim_token,
                    TwinEventRow.event_id == event_id,
                )
                .values(
                    claim_token=None,
                    claimed_at=None,
                    claim_expires_at=None,
                    last_error=error[:4000],
                    updated_at=now,
                )
            )
            result = await session.execute(stmt)
            affected = int(result.rowcount or 0)

            if affected:
                logger.warning(
                    "twin_event_marked_failed",
                    claim_token=str(claim_token),
                    event_id=str(event_id),
                    error=error,
                )
            return affected > 0

    async def get_unprojected_count(self, *, user_id: UUID | None = None) -> int:
        async with self._session_scope() as session:
            stmt = (
                select(func.count())
                .select_from(TwinEventRow)
                .where(TwinEventRow.projected.is_(False))
            )
            if user_id is not None:
                stmt = stmt.where(TwinEventRow.user_id == user_id)

            result = await session.execute(stmt)
            return int(result.scalar_one() or 0)

    async def get_last_projected_event(self, user_id: UUID) -> EventEnvelope | None:
        async with self._session_scope() as session:
            stmt = (
                select(TwinEventRow)
                .where(
                    TwinEventRow.user_id == user_id,
                    TwinEventRow.projected.is_(True),
                )
                .order_by(TwinEventRow.recorded_at.desc(), TwinEventRow.event_id.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return self._row_to_event(row) if row is not None else None

    async def delete_for_user(self, user_id: UUID) -> int:
        """Hard-delete all events for explicit purge flows."""
        async with self._session_scope() as session:
            stmt = delete(TwinEventRow).where(TwinEventRow.user_id == user_id)
            result = await session.execute(stmt)
            affected = int(result.rowcount or 0)

            logger.warning(
                "twin_events_deleted_for_user",
                user_id=str(user_id),
                affected=affected,
            )
            return affected

    async def vacuum_stale_claims(self) -> int:
        """Release expired worker claims."""
        now = datetime.now(UTC)

        async with self._session_scope() as session:
            stmt = (
                update(TwinEventRow)
                .where(
                    TwinEventRow.projected.is_(False),
                    TwinEventRow.claim_expires_at.is_not(None),
                    TwinEventRow.claim_expires_at < now,
                )
                .values(
                    claim_token=None,
                    claimed_at=None,
                    claim_expires_at=None,
                    updated_at=now,
                )
            )
            result = await session.execute(stmt)
            affected = int(result.rowcount or 0)

            if affected:
                logger.info("twin_stale_claims_released", affected=affected)
            return affected

    async def _get_by_idempotency_key(
        self,
        session: AsyncSession,
        idempotency_key: str,
    ) -> TwinEventRow | None:
        stmt = select(TwinEventRow).where(TwinEventRow.idempotency_key == idempotency_key)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    def _row_to_event(self, row: TwinEventRow) -> EventEnvelope:
        return EventEnvelope.model_validate(
            {
                "event_id": row.event_id,
                "user_id": row.user_id,
                "session_id": row.session_id,
                "event_type": row.event_type,
                "occurred_at": row.occurred_at,
                "recorded_at": row.recorded_at,
                "causation_id": row.causation_id,
                "correlation_id": row.correlation_id,
                "payload": row.payload_json or {},
                "provenance": row.provenance_json or {},
                "schema_version": row.schema_version,
                "metadata": row.metadata_json or {},
            }
        )

    def _extract_idempotency_key(self, event: EventEnvelope) -> str | None:
        raw = event.metadata.get("idempotency_key")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return None

    def _normalize_dt(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @asynccontextmanager
    async def _session_scope(self) -> AsyncIterator[AsyncSession]:
        session = self._session_factory()
        try:
            yield session

            if self._config.auto_flush:
                await session.flush()
            if self._config.auto_commit:
                await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("twin_event_store_session_failed")
            raise
        finally:
            await session.close()
