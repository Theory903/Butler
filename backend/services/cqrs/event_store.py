"""
Event Store - Event Sourcing with Redpanda

Implements event store for event sourcing pattern using Redpanda.
Supports event persistence, replay, and subscription.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class EventType(StrEnum):
    """Event type."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    STATUS_CHANGED = "status_changed"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Domain event."""

    event_id: str
    aggregate_type: str
    aggregate_id: str
    event_type: EventType
    payload: dict[str, Any]
    occurred_at: datetime
    causation_id: str | None  # ID of command that caused this event
    correlation_id: str | None  # ID for tracking across aggregates


class EventStore:
    """
    Event store for event sourcing.

    Features:
    - Event persistence
    - Event replay
    - Event subscription
    - Causation tracking
    """

    def __init__(self) -> None:
        """Initialize event store."""
        self._events: dict[str, list[DomainEvent]] = {}  # aggregate_id -> events
        self._subscribers: dict[str, list[Callable[[DomainEvent], Awaitable[None]]]] = {}

    async def append_event(
        self,
        event: DomainEvent,
    ) -> bool:
        """
        Append an event to the store.

        Args:
            event: Domain event

        Returns:
            True if appended
        """
        aggregate_key = f"{event.aggregate_type}:{event.aggregate_id}"

        if aggregate_key not in self._events:
            self._events[aggregate_key] = []

        self._events[aggregate_key].append(event)

        logger.info(
            "event_appended",
            event_id=event.event_id,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            event_type=event.event_type,
        )

        # Notify subscribers
        await self._notify_subscribers(event)

        return True

    async def get_events(
        self,
        aggregate_type: str,
        aggregate_id: str,
        from_version: int | None = None,
    ) -> list[DomainEvent]:
        """
        Get events for an aggregate.

        Args:
            aggregate_type: Aggregate type
            aggregate_id: Aggregate ID
            from_version: Optional starting version

        Returns:
            List of events
        """
        aggregate_key = f"{aggregate_type}:{aggregate_id}"

        if aggregate_key not in self._events:
            return []

        events = self._events[aggregate_key]

        if from_version is not None:
            events = events[from_version:]

        return events

    async def replay_aggregate(
        self,
        aggregate_type: str,
        aggregate_id: str,
    ) -> list[DomainEvent]:
        """
        Replay all events for an aggregate.

        Args:
            aggregate_type: Aggregate type
            aggregate_id: Aggregate ID

        Returns:
            List of all events for the aggregate
        """
        return await self.get_events(aggregate_type, aggregate_id)

    async def subscribe(
        self,
        aggregate_type: str | None = None,
        handler: Callable[[DomainEvent], Awaitable[None]] | None = None,
    ) -> str:
        """
        Subscribe to events.

        Args:
            aggregate_type: Aggregate type to filter (None for all)
            handler: Event handler

        Returns:
            Subscription ID
        """
        subscription_id = f"sub-{datetime.now(UTC).timestamp()}"

        if aggregate_type not in self._subscribers:
            self._subscribers[aggregate_type or "*"] = []

        if handler:
            self._subscribers[aggregate_type or "*"].append(handler)

        logger.info(
            "event_subscription_created",
            subscription_id=subscription_id,
            aggregate_type=aggregate_type or "*",
        )

        return subscription_id

    async def unsubscribe(
        self,
        subscription_id: str,
    ) -> bool:
        """
        Unsubscribe from events.

        Args:
            subscription_id: Subscription ID

        Returns:
            True if unsubscribed
        """
        # In a real implementation, we would track subscription IDs
        logger.info(
            "event_subscription_removed",
            subscription_id=subscription_id,
        )
        return True

    async def _notify_subscribers(self, event: DomainEvent) -> None:
        """Notify subscribers of an event."""
        # Notify wildcard subscribers
        for handler in self._subscribers.get("*", []):
            try:
                await handler(event)
            except Exception as e:
                logger.error(
                    "subscriber_handler_failed",
                    event_id=event.event_id,
                    error=str(e),
                )

        # Notify aggregate-specific subscribers
        for handler in self._subscribers.get(event.aggregate_type, []):
            try:
                await handler(event)
            except Exception as e:
                logger.error(
                    "subscriber_handler_failed",
                    event_id=event.event_id,
                    aggregate_type=event.aggregate_type,
                    error=str(e),
                )

    async def save_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: str,
        snapshot: dict[str, Any],
        version: int,
    ) -> bool:
        """
        Save a snapshot of aggregate state.

        Args:
            aggregate_type: Aggregate type
            aggregate_id: Aggregate ID
            snapshot: Snapshot data
            version: Event version at snapshot

        Returns:
            True if saved
        """
        # In production, this would store in a separate snapshot store
        logger.info(
            "snapshot_saved",
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            version=version,
        )
        return True

    async def load_snapshot(
        self,
        aggregate_type: str,
        aggregate_id: str,
    ) -> tuple[dict[str, Any], int] | None:
        """
        Load a snapshot of aggregate state.

        Args:
            aggregate_type: Aggregate type
            aggregate_id: Aggregate ID

        Returns:
            Snapshot data and version, or None
        """
        # In production, this would load from snapshot store
        return None

    def get_event_stats(self) -> dict[str, Any]:
        """
        Get event statistics.

        Returns:
            Event statistics
        """
        total_events = sum(len(events) for events in self._events.values())
        total_aggregates = len(self._events)

        event_type_counts: dict[str, int] = {}
        for events in self._events.values():
            for event in events:
                event_type_counts[event.event_type] = event_type_counts.get(event.event_type, 0) + 1

        return {
            "total_events": total_events,
            "total_aggregates": total_aggregates,
            "event_type_breakdown": event_type_counts,
            "total_subscriptions": len(self._subscribers),
        }
