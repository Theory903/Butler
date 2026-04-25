from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from services.memory.twin_projection import DigitalTwinProjection, ProjectionStatus


class TwinProjectionCheckpoint(BaseModel):
    """Projector checkpoint describing the last committed replay position.

    This is the operational cursor for projector resume/rebuild logic.

    Invariants:
    - projection_version is monotonic and non-negative
    - event_count_applied is monotonic and non-negative
    - last_event_recorded_at cannot be after updated_at
    - last_rebuild_at cannot be after updated_at
    - if event_count_applied > 0 then last_event_id must be present
    """

    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    projection_version: int = Field(default=0, ge=0)
    last_event_id: UUID | None = None
    last_event_recorded_at: datetime | None = None
    event_count_applied: int = Field(default=0, ge=0)
    last_rebuild_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "updated_at",
        "last_event_recorded_at",
        "last_rebuild_at",
        mode="before",
    )
    @classmethod
    def _normalize_datetime(cls, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return (
                parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
            )
        raise TypeError(f"Invalid datetime value: {value!r}")

    @field_validator("metadata", mode="before")
    @classmethod
    def _normalize_metadata(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise TypeError("metadata must be a dictionary")
        return dict(value)

    @model_validator(mode="after")
    def _validate_temporal_consistency(self) -> TwinProjectionCheckpoint:
        if (
            self.last_event_recorded_at is not None
            and self.last_event_recorded_at > self.updated_at
        ):
            raise ValueError("last_event_recorded_at cannot be after updated_at")

        if self.last_rebuild_at is not None and self.last_rebuild_at > self.updated_at:
            raise ValueError("last_rebuild_at cannot be after updated_at")

        if self.last_event_id is None and self.event_count_applied > 0:
            raise ValueError("last_event_id must be present when event_count_applied > 0")

        if self.projection_version == 0 and self.event_count_applied > 0:
            raise ValueError("projection_version must be > 0 when event_count_applied > 0")

        return self


class TwinProjectionSnapshot(BaseModel):
    """Materialized twin snapshot plus replay checkpoint.

    This is the canonical persisted read-model payload used by:
    - query services
    - projector resume logic
    - rebuild jobs
    - admin/debug tooling

    Invariants:
    - forgotten projections are not valid persisted snapshots
    - projection.user_id must equal checkpoint.user_id
    - checkpoint.projection_version must match projection.version
    - checkpoint.updated_at must not be earlier than projection.updated_at
    """

    model_config = ConfigDict(extra="forbid")

    projection: DigitalTwinProjection
    checkpoint: TwinProjectionCheckpoint

    @field_validator("projection")
    @classmethod
    def _validate_projection_status(cls, value: DigitalTwinProjection) -> DigitalTwinProjection:
        if value.status == ProjectionStatus.FORGOTTEN:
            raise ValueError("Projection snapshot cannot be created for a forgotten user")
        return value

    @model_validator(mode="after")
    def _validate_snapshot_consistency(self) -> TwinProjectionSnapshot:
        if self.projection.user_id != self.checkpoint.user_id:
            raise ValueError("projection.user_id and checkpoint.user_id must match")

        if self.projection.version != self.checkpoint.projection_version:
            raise ValueError("projection.version and checkpoint.projection_version must match")

        if self.checkpoint.updated_at < self.projection.updated_at:
            raise ValueError("checkpoint.updated_at cannot be earlier than projection.updated_at")

        if (
            self.checkpoint.last_event_recorded_at is not None
            and self.checkpoint.last_event_recorded_at > self.checkpoint.updated_at
        ):
            raise ValueError(
                "checkpoint.last_event_recorded_at cannot be after checkpoint.updated_at"
            )

        return self


class TwinProjectionSummary(BaseModel):
    """Lightweight summary view of a snapshot for admin/listing surfaces."""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    projection_version: int = Field(ge=0)
    status: ProjectionStatus
    event_count_applied: int = Field(ge=0)
    last_event_id: UUID | None = None
    last_event_recorded_at: datetime | None = None
    last_rebuild_at: datetime | None = None
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_snapshot(cls, snapshot: TwinProjectionSnapshot) -> TwinProjectionSummary:
        return cls(
            user_id=snapshot.projection.user_id,
            projection_version=snapshot.projection.version,
            status=snapshot.projection.status,
            event_count_applied=snapshot.checkpoint.event_count_applied,
            last_event_id=snapshot.checkpoint.last_event_id,
            last_event_recorded_at=snapshot.checkpoint.last_event_recorded_at,
            last_rebuild_at=snapshot.checkpoint.last_rebuild_at,
            updated_at=snapshot.checkpoint.updated_at,
            metadata=dict(snapshot.checkpoint.metadata),
        )
