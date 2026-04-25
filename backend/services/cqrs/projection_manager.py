"""
Projection Manager - Read Model Projections

Manages projections for CQRS read models.
Projects events to maintain denormalized read models.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

from services.cqrs.event_store import DomainEvent

logger = structlog.get_logger(__name__)


class ProjectionStatus(StrEnum):
    """Projection status."""

    ACTIVE = "active"
    BUILDING = "building"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass(frozen=True, slots=True)
class ProjectionState:
    """Projection state."""

    projection_name: str
    last_event_id: str
    last_processed_at: datetime
    status: ProjectionStatus
    error_message: str | None


class ProjectionManager:
    """
    Projection manager for read model projections.

    Features:
    - Projection registration
    - Event projection
    - State tracking
    - Rebuild support
    """

    def __init__(self) -> None:
        """Initialize projection manager."""
        self._projections: dict[str, Callable[[DomainEvent], Awaitable[None]]] = {}
        self._states: dict[str, ProjectionState] = {}

    def register_projection(
        self,
        projection_name: str,
        handler: Callable[[DomainEvent], Awaitable[None]],
    ) -> None:
        """
        Register a projection.

        Args:
            projection_name: Projection name
            handler: Event handler
        """
        self._projections[projection_name] = handler

        # Initialize state
        self._states[projection_name] = ProjectionState(
            projection_name=projection_name,
            last_event_id="",
            last_processed_at=datetime.now(UTC),
            status=ProjectionStatus.ACTIVE,
            error_message=None,
        )

        logger.info(
            "projection_registered",
            projection_name=projection_name,
        )

    async def project_event(
        self,
        event: DomainEvent,
    ) -> None:
        """
        Project an event to all registered projections.

        Args:
            event: Domain event
        """
        for projection_name, handler in self._projections.items():
            state = self._states.get(projection_name)

            if state and state.status != ProjectionStatus.ACTIVE:
                continue

            try:
                await handler(event)

                # Update state
                self._states[projection_name] = ProjectionState(
                    projection_name=projection_name,
                    last_event_id=event.event_id,
                    last_processed_at=datetime.now(UTC),
                    status=ProjectionStatus.ACTIVE,
                    error_message=None,
                )

            except Exception as e:
                logger.error(
                    "projection_failed",
                    projection_name=projection_name,
                    event_id=event.event_id,
                    error=str(e),
                )

                # Update state to failed
                self._states[projection_name] = ProjectionState(
                    projection_name=projection_name,
                    last_event_id=state.last_event_id if state else "",
                    last_processed_at=state.last_processed_at if state else datetime.now(UTC),
                    status=ProjectionStatus.FAILED,
                    error_message=str(e),
                )

    async def rebuild_projection(
        self,
        projection_name: str,
        events: list[DomainEvent],
    ) -> bool:
        """
        Rebuild a projection from events.

        Args:
            projection_name: Projection name
            events: Events to replay

        Returns:
            True if rebuilt
        """
        if projection_name not in self._projections:
            logger.error(
                "projection_not_found",
                projection_name=projection_name,
            )
            return False

        handler = self._projections[projection_name]

        # Set status to building
        self._states[projection_name] = ProjectionState(
            projection_name=projection_name,
            last_event_id="",
            last_processed_at=datetime.now(UTC),
            status=ProjectionStatus.BUILDING,
            error_message=None,
        )

        try:
            for event in events:
                await handler(event)

            # Set status to active
            last_event = events[-1] if events else None
            self._states[projection_name] = ProjectionState(
                projection_name=projection_name,
                last_event_id=last_event.event_id if last_event else "",
                last_processed_at=datetime.now(UTC),
                status=ProjectionStatus.ACTIVE,
                error_message=None,
            )

            logger.info(
                "projection_rebuilt",
                projection_name=projection_name,
                events_processed=len(events),
            )

            return True

        except Exception as e:
            logger.error(
                "projection_rebuild_failed",
                projection_name=projection_name,
                error=str(e),
            )

            # Set status to failed
            self._states[projection_name] = ProjectionState(
                projection_name=projection_name,
                last_event_id="",
                last_processed_at=datetime.now(UTC),
                status=ProjectionStatus.FAILED,
                error_message=str(e),
            )

            return False

    def get_projection_state(
        self,
        projection_name: str,
    ) -> ProjectionState | None:
        """
        Get projection state.

        Args:
            projection_name: Projection name

        Returns:
            Projection state or None
        """
        return self._states.get(projection_name)

    def list_projections(
        self,
        status: ProjectionStatus | None = None,
    ) -> list[ProjectionState]:
        """
        List projections with optional filter.

        Args:
            status: Filter by status

        Returns:
            List of projection states
        """
        states = list(self._states.values())

        if status:
            states = [s for s in states if s.status == status]

        return states

    def pause_projection(self, projection_name: str) -> bool:
        """
        Pause a projection.

        Args:
            projection_name: Projection name

        Returns:
            True if paused
        """
        if projection_name not in self._states:
            return False

        state = self._states[projection_name]
        self._states[projection_name] = ProjectionState(
            projection_name=projection_name,
            last_event_id=state.last_event_id,
            last_processed_at=state.last_processed_at,
            status=ProjectionStatus.PAUSED,
            error_message=None,
        )

        logger.info(
            "projection_paused",
            projection_name=projection_name,
        )

        return True

    def resume_projection(self, projection_name: str) -> bool:
        """
        Resume a paused projection.

        Args:
            projection_name: Projection name

        Returns:
            True if resumed
        """
        if projection_name not in self._states:
            return False

        state = self._states[projection_name]
        self._states[projection_name] = ProjectionState(
            projection_name=projection_name,
            last_event_id=state.last_event_id,
            last_processed_at=state.last_processed_at,
            status=ProjectionStatus.ACTIVE,
            error_message=None,
        )

        logger.info(
            "projection_resumed",
            projection_name=projection_name,
        )

        return True

    def get_projection_stats(self) -> dict[str, Any]:
        """
        Get projection statistics.

        Returns:
            Projection statistics
        """
        total_projections = len(self._projections)

        status_counts: dict[str, int] = {}
        for state in self._states.values():
            status_counts[state.status] = status_counts.get(state.status, 0) + 1

        return {
            "total_projections": total_projections,
            "status_breakdown": status_counts,
        }
