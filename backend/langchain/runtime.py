"""
ButlerToolRuntime - Context propagation for LangChain tool execution.

This runtime provides tenant/account/session context to LangChain tools,
ensuring Butler's governance, audit, and multi-tenancy are preserved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ButlerToolContext:
    """Execution context for Butler tools in LangChain workflows.

    This context is passed through LangGraph's tool execution to ensure
    Butler's governance, audit, and multi-tenancy are preserved.

    Attributes:
        tenant_id: Tenant UUID for multi-tenant isolation
        account_id: Account UUID for user/account association
        session_id: Session UUID for conversation tracking
        trace_id: Trace UUID for distributed tracing
        user_id: Optional user UUID for user-level policies
        metadata: Additional context metadata
    """

    tenant_id: str
    account_id: str
    session_id: str
    trace_id: str
    user_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ButlerToolRuntime:
    """Runtime context manager for LangChain tool execution.

    This runtime:
    - Propagates tenant/account/session context through LangGraph
    - Provides context to ButlerToolSpec-based tools
    - Ensures governance checks have access to full context
    - Maintains audit trail with proper attribution

    Usage:
        runtime = ButlerToolRuntime(
            tenant_id="...",
            account_id="...",
            session_id="...",
            trace_id="...",
        )
        context = runtime.get_context()
    """

    tenant_id: str
    account_id: str
    session_id: str
    trace_id: str
    user_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_context(self) -> ButlerToolContext:
        """Get the current tool execution context."""
        return ButlerToolContext(
            tenant_id=self.tenant_id,
            account_id=self.account_id,
            session_id=self.session_id,
            trace_id=self.trace_id,
            user_id=self.user_id,
            metadata=dict(self.metadata),
        )

    def with_metadata(self, **kwargs: Any) -> ButlerToolRuntime:
        """Create a new runtime with additional metadata."""
        updated_metadata = {**self.metadata, **kwargs}
        return ButlerToolRuntime(
            tenant_id=self.tenant_id,
            account_id=self.account_id,
            session_id=self.session_id,
            trace_id=self.trace_id,
            user_id=self.user_id,
            metadata=updated_metadata,
        )

    def to_langgraph_config(self) -> dict[str, Any]:
        """Convert to LangGraph config format for state propagation.

        This config is passed to LangGraph nodes to ensure context
        is available throughout the graph execution.
        """
        return {
            "configurable": {
                "tenant_id": self.tenant_id,
                "account_id": self.account_id,
                "session_id": self.session_id,
                "trace_id": self.trace_id,
                "user_id": self.user_id,
                **self.metadata,
            }
        }


class ButlerToolRuntimeManager:
    """Factory and manager for ButlerToolRuntime instances.

    This manager:
    - Creates runtime contexts from Butler ExecutionContext
    - Provides context to LangGraph workflows
    - Manages context lifecycle across agent turns
    """

    @staticmethod
    def from_execution_context(
        tenant_id: str,
        account_id: str,
        session_id: str,
        trace_id: str,
        user_id: str | None = None,
        **metadata: Any,
    ) -> ButlerToolRuntime:
        """Create a ButlerToolRuntime from Butler ExecutionContext fields.

        Args:
            tenant_id: Tenant UUID
            account_id: Account UUID
            session_id: Session UUID
            trace_id: Trace UUID
            user_id: Optional user UUID
            **metadata: Additional context metadata

        Returns:
            Configured ButlerToolRuntime instance
        """
        return ButlerToolRuntime(
            tenant_id=tenant_id,
            account_id=account_id,
            session_id=session_id,
            trace_id=trace_id,
            user_id=user_id,
            metadata=metadata,
        )

    @staticmethod
    def extract_from_langgraph_config(config: dict[str, Any]) -> ButlerToolContext:
        """Extract ButlerToolContext from LangGraph config.

        Args:
            config: LangGraph config dictionary

        Returns:
            ButlerToolContext instance

        Raises:
            ValueError: If required context fields are missing
        """
        configurable = config.get("configurable", {})

        tenant_id = configurable.get("tenant_id")
        account_id = configurable.get("account_id")
        session_id = configurable.get("session_id")
        trace_id = configurable.get("trace_id")

        if not all([tenant_id, account_id, session_id, trace_id]):
            raise ValueError(
                "Missing required context fields in LangGraph config. "
                f"Got: tenant_id={tenant_id}, account_id={account_id}, "
                f"session_id={session_id}, trace_id={trace_id}"
            )

        return ButlerToolContext(
            tenant_id=tenant_id,
            account_id=account_id,
            session_id=session_id,
            trace_id=trace_id,
            user_id=configurable.get("user_id"),
            metadata={k: v for k, v in configurable.items() if k not in {"tenant_id", "account_id", "session_id", "trace_id", "user_id"}},
        )
