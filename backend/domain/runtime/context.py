"""RuntimeContext - canonical runtime context carrying all request-scoped information."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping


class RuntimeContextError(Exception):
    """Raised when RuntimeContext is invalid or missing required fields."""

    pass


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    """Canonical runtime context for all Butler operations.

    This dataclass carries all request-scoped information that must be propagated
    through tool execution, memory access, model calls, workflow execution, and
    any other runtime operation.

    Rule: No RuntimeContext = no tool execution, no memory access, no model call,
    no workflow execution.
    """

    tenant_id: str
    account_id: str
    user_id: str | None
    session_id: str
    request_id: str
    trace_id: str
    workflow_id: str | None
    task_id: str | None
    agent_id: str | None
    device_id: str | None
    channel: str
    locale: str
    timezone: str
    permissions: frozenset[str]
    roles: frozenset[str]
    region: str
    cell: str
    environment: str
    created_at: datetime
    metadata: Mapping[str, str]

    def require_tenant_scope(self) -> None:
        """Ensure tenant/account/session scope is present.

        Raises:
            RuntimeContextError: If required tenant/account/session fields are missing.
        """
        if not self.tenant_id or not self.account_id or not self.session_id:
            raise RuntimeContextError(
                "Missing tenant/account/session scope for runtime operation."
            )

    def require_workflow_scope(self) -> None:
        """Ensure workflow/task scope is present.

        Raises:
            RuntimeContextError: If required workflow/task fields are missing.
        """
        if not self.workflow_id:
            raise RuntimeContextError(
                "Missing workflow_id for workflow operation."
            )

    def require_agent_scope(self) -> None:
        """Ensure agent scope is present.

        Raises:
            RuntimeContextError: If required agent_id field is missing.
        """
        if not self.agent_id:
            raise RuntimeContextError(
                "Missing agent_id for agent operation."
            )

    @classmethod
    def create(
        cls,
        tenant_id: str,
        account_id: str,
        session_id: str,
        request_id: str,
        trace_id: str,
        channel: str = "api",
        locale: str = "en",
        timezone: str = "UTC",
        region: str = "default",
        cell: str = "default",
        environment: str = "production",
        user_id: str | None = None,
        workflow_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        device_id: str | None = None,
        permissions: frozenset[str] | None = None,
        roles: frozenset[str] | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> RuntimeContext:
        """Factory method to create a RuntimeContext with sensible defaults.

        Args:
            tenant_id: Tenant UUID for multi-tenant isolation
            account_id: Account UUID
            session_id: Session UUID
            request_id: Request UUID
            trace_id: Trace UUID for distributed tracing
            channel: Channel name (e.g., "api", "slack", "discord")
            locale: User locale (e.g., "en", "en-US", "hi-IN")
            timezone: User timezone (e.g., "UTC", "Asia/Kolkata")
            region: Deployment region (e.g., "us-east-1", "eu-west-1")
            cell: Deployment cell (e.g., "cell-1", "cell-2")
            environment: Environment name (e.g., "production", "staging")
            user_id: Optional user UUID
            workflow_id: Optional workflow UUID
            task_id: Optional task UUID
            agent_id: Optional agent UUID
            device_id: Optional device UUID
            permissions: Optional set of permission strings
            roles: Optional set of role strings
            metadata: Optional additional metadata

        Returns:
            RuntimeContext instance
        """
        return cls(
            tenant_id=tenant_id,
            account_id=account_id,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            trace_id=trace_id,
            workflow_id=workflow_id,
            task_id=task_id,
            agent_id=agent_id,
            device_id=device_id,
            channel=channel,
            locale=locale,
            timezone=timezone,
            permissions=permissions or frozenset(),
            roles=roles or frozenset(),
            region=region,
            cell=cell,
            environment=environment,
            created_at=datetime.utcnow(),
            metadata=metadata or {},
        )
