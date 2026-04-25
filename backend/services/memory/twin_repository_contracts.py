from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from services.memory.twin_events import EventEnvelope
from services.memory.twin_snapshot_models import (
    TwinProjectionCheckpoint,
    TwinProjectionSnapshot,
)


class ClaimedEventBatch(Protocol):
    """Protocol for claimed projector work batches.

    Concrete implementations may use a dataclass or Pydantic model, but they
    must expose a claim token and a stable ordered list of events.
    """

    claim_token: UUID
    events: list[EventEnvelope]


class TwinProjectionRepository(Protocol):
    """Persistence contract for materialized digital twin snapshots.

    Responsibilities:
    - load the latest snapshot for a user
    - upsert the snapshot atomically
    - delete the snapshot for forget/reset flows
    - expose helper reads for orchestration and admin surfaces
    """

    async def get_snapshot(self, user_id: UUID) -> TwinProjectionSnapshot | None:
        """Return the latest stored snapshot for a user, if any."""

    async def upsert_snapshot(self, snapshot: TwinProjectionSnapshot) -> None:
        """Insert or replace the latest snapshot for a user."""

    async def delete_snapshot(self, user_id: UUID) -> None:
        """Delete the stored snapshot for a user."""

    async def exists(self, user_id: UUID) -> bool:
        """Return whether a snapshot exists for the given user."""

    async def get_projection_version(self, user_id: UUID) -> int | None:
        """Return the latest stored projection version for a user."""

    async def get_checkpoint(
        self,
        user_id: UUID,
    ) -> TwinProjectionCheckpoint | None:
        """Return the checkpoint embedded in the stored snapshot, if any."""

    async def list_users(
        self,
        *,
        limit: int = 100,
        after_user_id: UUID | None = None,
    ) -> list[UUID]:
        """List user IDs that currently have materialized snapshots."""


class TwinCheckpointRepository(Protocol):
    """Optional dedicated checkpoint persistence contract.

    This is only needed if checkpoints are stored separately from snapshots.
    If your snapshot already embeds the checkpoint, you usually do not need a
    separate implementation for this protocol.
    """

    async def get_checkpoint(
        self,
        user_id: UUID,
    ) -> TwinProjectionCheckpoint | None:
        """Return the checkpoint for a user."""

    async def upsert_checkpoint(
        self,
        checkpoint: TwinProjectionCheckpoint,
    ) -> None:
        """Insert or replace a checkpoint for a user."""

    async def delete_checkpoint(self, user_id: UUID) -> None:
        """Delete the checkpoint for a user."""

    async def exists(self, user_id: UUID) -> bool:
        """Return whether a checkpoint exists for the given user."""

    async def get_projection_version(self, user_id: UUID) -> int | None:
        """Return the latest checkpoint projection version for a user."""


class TwinEventStore(Protocol):
    """Canonical event-source contract for Butler twin replay.

    Responsibilities:
    - append validated twin events
    - support idempotent event writes
    - read user-scoped ordered timelines
    - support replay from a known boundary
    - expose point lookups and purge paths where explicitly required
    """

    async def append(self, event: EventEnvelope) -> UUID:
        """Append one event and return its canonical event ID."""

    async def append_many(self, events: Sequence[EventEnvelope]) -> list[UUID]:
        """Append multiple events in one logical batch."""

    async def get_event(self, event_id: UUID) -> EventEnvelope | None:
        """Return one event by ID."""

    async def list_events_for_user(
        self,
        user_id: UUID,
        *,
        after_event_id: UUID | None = None,
        after_recorded_at: datetime | None = None,
        limit: int = 500,
        projected: bool | None = None,
    ) -> list[EventEnvelope]:
        """Return user events in stable append/replay order."""

    async def get_unprojected_count(self, *, user_id: UUID | None = None) -> int:
        """Return the number of unprojected events."""

    async def get_last_projected_event(
        self,
        user_id: UUID,
    ) -> EventEnvelope | None:
        """Return the newest successfully projected event for a user."""

    async def delete_for_user(self, user_id: UUID) -> int:
        """Hard-delete all events for a user.

        This is only for explicit purge/forget flows.
        """


class TwinProjectorEventStore(TwinEventStore, Protocol):
    """Extended event-store contract for distributed projector workers.

    This is the operational interface used when projector workers need to claim,
    acknowledge, retry, and recover batches safely across processes.
    """

    async def claim_unprojected(
        self,
        *,
        batch_size: int = 100,
        user_id: UUID | None = None,
    ) -> ClaimedEventBatch:
        """Claim a batch of unprojected events for one worker."""

    async def acknowledge_projected(
        self,
        claim_token: UUID,
        event_ids: Sequence[UUID],
    ) -> int:
        """Mark claimed events as successfully projected."""

    async def release_claim(
        self,
        claim_token: UUID,
        *,
        error: str | None = None,
    ) -> int:
        """Release a claim without marking events as projected."""

    async def mark_failed(
        self,
        claim_token: UUID,
        event_id: UUID,
        error: str,
    ) -> bool:
        """Mark one claimed event as failed and return it to retryable state."""

    async def vacuum_stale_claims(self) -> int:
        """Release expired claims left behind by crashed or stalled workers."""


class TwinProjectorLock(Protocol):
    """Cross-process or in-process lock abstraction for per-user projection updates."""

    async def acquire(self, key: str, ttl_seconds: int = 30) -> bool:
        """Acquire a lock for the given projector key."""

    async def release(self, key: str) -> None:
        """Release a previously acquired lock."""


class TwinOutboxRepository(Protocol):
    """Optional outbox contract for reliable event dispatch before canonical append.

    Use this when the write path persists outgoing domain events into an outbox
    before they are appended or published elsewhere.
    """

    async def enqueue(self, event: EventEnvelope) -> UUID:
        """Store one outbox event."""

    async def enqueue_many(self, events: Sequence[EventEnvelope]) -> list[UUID]:
        """Store multiple outbox events."""

    async def claim_pending(
        self,
        *,
        batch_size: int = 100,
    ) -> list[EventEnvelope]:
        """Claim pending outbox events for dispatch."""

    async def mark_dispatched(self, event_ids: Sequence[UUID]) -> int:
        """Mark outbox events as dispatched."""

    async def mark_failed(
        self,
        event_id: UUID,
        error: str,
    ) -> bool:
        """Mark one outbox event as failed."""


class TwinReadRepository(Protocol):
    """Read-only convenience contract for query/profile services.

    Useful when you want to inject only read capabilities into API/query
    surfaces without exposing mutation methods.
    """

    async def get_snapshot(self, user_id: UUID) -> TwinProjectionSnapshot | None:
        """Return the latest materialized snapshot for a user."""

    async def exists(self, user_id: UUID) -> bool:
        """Return whether a materialized snapshot exists."""

    async def get_projection_version(self, user_id: UUID) -> int | None:
        """Return the latest projection version, if any."""
