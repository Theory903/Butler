"""Audit Logging.

Phase L: Audit logging for compliance and security.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class AuditEvent:
    """An audit event for compliance tracking."""

    event_id: str
    event_type: str
    user_id: str
    tenant_id: str
    resource_type: str
    resource_id: str
    action: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    ip_address: str | None = None
    user_agent: str | None = None
    success: bool = True
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AuditLogger:
    """Audit logger for compliance and security.

    This logger:
    - Records audit events
    - Tracks user actions
    - Provides compliance reports
    - Supports audit trail queries
    """

    def __init__(self):
        """Initialize the audit logger."""
        self._events: dict[str, AuditEvent] = {}

    def log_event(self, event: AuditEvent) -> None:
        """Log an audit event.

        Args:
            event: Audit event to log
        """
        self._events[event.event_id] = event
        logger.info("audit_event_logged", event_id=event.event_id, event_type=event.event_type)

    def log_action(
        self,
        event_type: str,
        user_id: str,
        tenant_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        success: bool = True,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Log an action as an audit event.

        Args:
            event_type: Type of event
            user_id: User identifier
            tenant_id: Tenant identifier
            resource_type: Resource type
            resource_id: Resource identifier
            action: Action performed
            success: Whether action succeeded
            error_message: Error message if failed
            metadata: Additional metadata

        Returns:
            Created audit event
        """
        event_id = str(uuid4())
        event = AuditEvent(
            event_id=event_id,
            event_type=event_type,
            user_id=user_id,
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            success=success,
            error_message=error_message,
            metadata=metadata or {},
        )
        self.log_event(event)
        return event

    def get_event(self, event_id: str) -> AuditEvent | None:
        """Get an audit event.

        Args:
            event_id: Event identifier

        Returns:
            Audit event or None
        """
        return self._events.get(event_id)

    def query_events(
        self,
        user_id: str | None = None,
        tenant_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        event_type: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[AuditEvent]:
        """Query audit events with filters.

        Args:
            user_id: Optional user filter
            tenant_id: Optional tenant filter
            resource_type: Optional resource type filter
            resource_id: Optional resource ID filter
            event_type: Optional event type filter
            start_time: Optional start time filter
            end_time: Optional end time filter

        Returns:
            List of matching events
        """
        events = list(self._events.values())

        if user_id:
            events = [e for e in events if e.user_id == user_id]

        if tenant_id:
            events = [e for e in events if e.tenant_id == tenant_id]

        if resource_type:
            events = [e for e in events if e.resource_type == resource_type]

        if resource_id:
            events = [e for e in events if e.resource_id == resource_id]

        if event_type:
            events = [e for e in events if e.event_type == event_type]

        if start_time:
            events = [e for e in events if e.timestamp >= start_time]

        if end_time:
            events = [e for e in events if e.timestamp <= end_time]

        return events

    def get_user_audit_trail(self, user_id: str) -> list[AuditEvent]:
        """Get audit trail for a user.

        Args:
            user_id: User identifier

        Returns:
            List of user's audit events
        """
        return self.query_events(user_id=user_id)

    def get_tenant_audit_trail(self, tenant_id: str) -> list[AuditEvent]:
        """Get audit trail for a tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            List of tenant's audit events
        """
        return self.query_events(tenant_id=tenant_id)
