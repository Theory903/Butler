from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import DateTime, Integer, String, UniqueConstraint, delete, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, declarative_base, mapped_column

from services.memory.twin_projection import DigitalTwinProjection
from services.memory.twin_repository_contracts import TwinProjectionRepository
from services.memory.twin_snapshot_models import (
    TwinProjectionCheckpoint,
    TwinProjectionSnapshot,
)

logger = structlog.get_logger(__name__)

Base = declarative_base()


class TwinProjectionSnapshotRow(Base):
    """Materialized digital twin snapshot storage row.

    One row per user. The full projection is stored as JSONB so projection
    structure can evolve without requiring schema churn for every new field.
    """

    __tablename__ = "twin_projection_snapshots"
    __table_args__ = (UniqueConstraint("user_id", name="uq_twin_projection_snapshots_user_id"),)

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
    )

    projection_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    last_event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    last_event_recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    event_count_applied: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    last_rebuild_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    projection_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    checkpoint_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    status: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        default="active",
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
    )


@dataclass(slots=True, frozen=True)
class TwinSnapshotRepositoryConfig:
    """Config for the snapshot repository."""

    auto_commit: bool = False
    auto_flush: bool = True
    reject_stale_writes: bool = True

    def __post_init__(self) -> None:
        if self.auto_commit and not self.auto_flush:
            raise ValueError("auto_commit=True requires auto_flush=True")


class PostgresTwinProjectionRepository(TwinProjectionRepository):
    """PostgreSQL-backed snapshot repository for materialized twin projections.

    Design goals:
    - one canonical snapshot row per user
    - async-safe request/task-scoped session lifecycle
    - idempotent upsert semantics
    - optional stale-write rejection so older projector workers do not clobber
      newer snapshots
    """

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        config: TwinSnapshotRepositoryConfig | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._config = config or TwinSnapshotRepositoryConfig()

    async def get_snapshot(self, user_id: UUID) -> TwinProjectionSnapshot | None:
        async with self._session_scope() as session:
            stmt = select(TwinProjectionSnapshotRow).where(
                TwinProjectionSnapshotRow.user_id == user_id
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None

            snapshot = self._row_to_snapshot(row)

            logger.debug(
                "twin_snapshot_loaded",
                user_id=str(user_id),
                projection_version=snapshot.projection.version,
                last_event_id=(
                    str(snapshot.checkpoint.last_event_id)
                    if snapshot.checkpoint.last_event_id is not None
                    else None
                ),
            )
            return snapshot

    async def upsert_snapshot(self, snapshot: TwinProjectionSnapshot) -> None:
        projection = snapshot.projection
        checkpoint = snapshot.checkpoint
        now = datetime.now(UTC)

        payload = {
            "user_id": projection.user_id,
            "projection_version": projection.version,
            "last_event_id": checkpoint.last_event_id,
            "last_event_recorded_at": checkpoint.last_event_recorded_at,
            "event_count_applied": checkpoint.event_count_applied,
            "last_rebuild_at": checkpoint.last_rebuild_at,
            "projection_json": projection.model_dump(mode="json"),
            "checkpoint_metadata": checkpoint.metadata,
            "status": projection.status.value,
            "updated_at": now,
        }

        async with self._session_scope() as session:
            stmt = insert(TwinProjectionSnapshotRow).values(
                {
                    **payload,
                    "created_at": now,
                }
            )

            update_set = {
                "projection_version": stmt.excluded.projection_version,
                "last_event_id": stmt.excluded.last_event_id,
                "last_event_recorded_at": stmt.excluded.last_event_recorded_at,
                "event_count_applied": stmt.excluded.event_count_applied,
                "last_rebuild_at": stmt.excluded.last_rebuild_at,
                "projection_json": stmt.excluded.projection_json,
                "checkpoint_metadata": stmt.excluded.checkpoint_metadata,
                "status": stmt.excluded.status,
                "updated_at": stmt.excluded.updated_at,
            }

            if self._config.reject_stale_writes:
                stmt = stmt.on_conflict_do_update(
                    index_elements=[TwinProjectionSnapshotRow.user_id],
                    set_=update_set,
                    where=(
                        (
                            TwinProjectionSnapshotRow.projection_version
                            < stmt.excluded.projection_version
                        )
                        | (
                            (
                                TwinProjectionSnapshotRow.projection_version
                                == stmt.excluded.projection_version
                            )
                            & (
                                (TwinProjectionSnapshotRow.last_event_recorded_at is None)
                                | (
                                    TwinProjectionSnapshotRow.last_event_recorded_at
                                    < stmt.excluded.last_event_recorded_at
                                )
                            )
                        )
                    ),
                )
            else:
                stmt = stmt.on_conflict_do_update(
                    index_elements=[TwinProjectionSnapshotRow.user_id],
                    set_=update_set,
                )

            result = await session.execute(stmt)

            if result.rowcount == 0:
                # If we got here, it means ON CONFLICT happened but the WHERE clause failed.
                # This is a specific "stale update" case.
                logger.warning(
                    "twin_snapshot_upsert_rejected_stale",
                    user_id=str(projection.user_id),
                    incoming_version=projection.version,
                    incoming_event_at=(
                        checkpoint.last_event_recorded_at.isoformat()
                        if checkpoint.last_event_recorded_at
                        else None
                    ),
                    reason="Database row has higher version or newer timestamp",
                )
            else:
                logger.info(
                    "twin_snapshot_upserted",
                    user_id=str(projection.user_id),
                    projection_version=projection.version,
                    status=projection.status.value,
                    last_event_id=(
                        str(checkpoint.last_event_id)
                        if checkpoint.last_event_id is not None
                        else None
                    ),
                )

    async def delete_snapshot(self, user_id: UUID) -> None:
        async with self._session_scope() as session:
            stmt = delete(TwinProjectionSnapshotRow).where(
                TwinProjectionSnapshotRow.user_id == user_id
            )
            await session.execute(stmt)

            logger.info(
                "twin_snapshot_deleted",
                user_id=str(user_id),
            )

    async def exists(self, user_id: UUID) -> bool:
        async with self._session_scope() as session:
            stmt = select(TwinProjectionSnapshotRow.user_id).where(
                TwinProjectionSnapshotRow.user_id == user_id
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    async def get_projection_version(self, user_id: UUID) -> int | None:
        async with self._session_scope() as session:
            stmt = select(TwinProjectionSnapshotRow.projection_version).where(
                TwinProjectionSnapshotRow.user_id == user_id
            )
            result = await session.execute(stmt)
            value = result.scalar_one_or_none()
            return int(value) if value is not None else None

    async def get_checkpoint(self, user_id: UUID) -> TwinProjectionCheckpoint | None:
        snapshot = await self.get_snapshot(user_id)
        return snapshot.checkpoint if snapshot is not None else None

    async def list_users(
        self,
        *,
        limit: int = 100,
        after_user_id: UUID | None = None,
    ) -> list[UUID]:
        async with self._session_scope() as session:
            stmt = select(TwinProjectionSnapshotRow.user_id).order_by(
                TwinProjectionSnapshotRow.user_id.asc()
            )

            if after_user_id is not None:
                stmt = stmt.where(TwinProjectionSnapshotRow.user_id > after_user_id)

            stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    def _row_to_snapshot(
        self,
        row: TwinProjectionSnapshotRow,
    ) -> TwinProjectionSnapshot:
        projection_payload = dict(row.projection_json or {})
        checkpoint_metadata = dict(row.checkpoint_metadata or {})

        projection = DigitalTwinProjection.model_validate(projection_payload)

        checkpoint = TwinProjectionCheckpoint(
            user_id=row.user_id,
            projection_version=row.projection_version,
            last_event_id=row.last_event_id,
            last_event_recorded_at=row.last_event_recorded_at,
            event_count_applied=row.event_count_applied,
            last_rebuild_at=row.last_rebuild_at,
            updated_at=row.updated_at,
            metadata=checkpoint_metadata,
        )

        return TwinProjectionSnapshot(
            projection=projection,
            checkpoint=checkpoint,
        )

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
            logger.exception("twin_snapshot_repo_session_failed")
            raise
        finally:
            await session.close()
