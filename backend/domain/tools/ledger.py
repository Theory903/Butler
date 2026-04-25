"""Tool Execution Ledger - Phase T6.

ToolExecutionLedger tracks all tool executions for audit and observability.

Stores:
- tenant_id, account_id, session_id
- tool_name, tool_spec_version
- input_hash, output_hash
- status, latency_ms
- error_code, error_message
- policy_decision
- sandbox_used, approval_id
- degraded_mode, compensation_handler_id

Provides:
- Create row before execution
- Update row during execution
- Finalize row after execution
- Query by tenant_id, account_id, session_id, tool_name, status, time_range
- Aggregate by tool_name, status, error_code, latency
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class ExecutionStatus(str, Enum):
    """Tool execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class PolicyDecision(str, Enum):
    """Policy decision for tool execution."""

    ALLOWED = "allowed"
    DENIED = "denied"
    REQUIRE_APPROVAL = "require_approval"
    REQUIRE_SANDBOX = "require_sandbox"
    DEGRADED = "degraded"


@dataclass
class ToolExecutionLedgerEntry:
    """Tool execution ledger entry."""

    execution_id: UUID
    tenant_id: str
    account_id: str
    session_id: str
    tool_name: str
    tool_spec_version: str
    input_hash: str
    status: ExecutionStatus
    created_at: datetime
    updated_at: datetime
    latency_ms: int | None = None
    output_hash: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    policy_decision: PolicyDecision | None = None
    sandbox_used: bool = False
    approval_id: str | None = None
    degraded_mode: str | None = None
    compensation_handler_id: str | None = None
    workflow_id: str | None = None
    task_id: str | None = None


class ToolExecutionLedger:
    """Tool execution ledger for audit and observability.

    This is the domain interface. The actual implementation
    is in services/tools/ledger.py.
    """

    def create_entry(
        self,
        tenant_id: str,
        account_id: str,
        session_id: str,
        tool_name: str,
        tool_spec_version: str,
        input_hash: str,
        workflow_id: str | None = None,
        task_id: str | None = None,
    ) -> ToolExecutionLedgerEntry:
        """Create a new ledger entry before execution.

        Args:
            tenant_id: Tenant ID
            account_id: Account ID
            session_id: Session ID
            tool_name: Tool name
            tool_spec_version: Tool spec version
            input_hash: Hash of input parameters
            workflow_id: Workflow ID (if applicable)
            task_id: Task ID (if applicable)

        Returns:
            ToolExecutionLedgerEntry
        """
        raise NotImplementedError

    def update_entry_status(
        self,
        execution_id: UUID,
        status: ExecutionStatus,
    ) -> None:
        """Update ledger entry status.

        Args:
            execution_id: Execution ID
            status: New status
        """
        raise NotImplementedError

    def finalize_entry(
        self,
        execution_id: UUID,
        status: ExecutionStatus,
        output_hash: str | None = None,
        latency_ms: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        policy_decision: PolicyDecision | None = None,
        sandbox_used: bool = False,
        approval_id: str | None = None,
        degraded_mode: str | None = None,
        compensation_handler_id: str | None = None,
    ) -> None:
        """Finalize ledger entry after execution.

        Args:
            execution_id: Execution ID
            status: Final status
            output_hash: Hash of output
            latency_ms: Execution latency in ms
            error_code: Error code (if failed)
            error_message: Error message (if failed)
            policy_decision: Policy decision
            sandbox_used: Whether sandbox was used
            approval_id: Approval ID (if required)
            degraded_mode: Degraded mode (if applicable)
            compensation_handler_id: Compensation handler ID (if applicable)
        """
        raise NotImplementedError

    def query_by_tenant(
        self,
        tenant_id: str,
        limit: int = 100,
    ) -> list[ToolExecutionLedgerEntry]:
        """Query ledger entries by tenant.

        Args:
            tenant_id: Tenant ID
            limit: Maximum number of entries

        Returns:
            List of ledger entries
        """
        raise NotImplementedError

    def query_by_account(
        self,
        tenant_id: str,
        account_id: str,
        limit: int = 100,
    ) -> list[ToolExecutionLedgerEntry]:
        """Query ledger entries by account.

        Args:
            tenant_id: Tenant ID
            account_id: Account ID
            limit: Maximum number of entries

        Returns:
            List of ledger entries
        """
        raise NotImplementedError

    def query_by_session(
        self,
        tenant_id: str,
        session_id: str,
        limit: int = 100,
    ) -> list[ToolExecutionLedgerEntry]:
        """Query ledger entries by session.

        Args:
            tenant_id: Tenant ID
            session_id: Session ID
            limit: Maximum number of entries

        Returns:
            List of ledger entries
        """
        raise NotImplementedError

    def query_by_tool(
        self,
        tool_name: str,
        limit: int = 100,
    ) -> list[ToolExecutionLedgerEntry]:
        """Query ledger entries by tool.

        Args:
            tool_name: Tool name
            limit: Maximum number of entries

        Returns:
            List of ledger entries
        """
        raise NotImplementedError

    def aggregate_by_tool(
        self,
        time_range: tuple[datetime, datetime] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Aggregate ledger entries by tool.

        Args:
            time_range: Optional time range filter

        Returns:
            Dictionary with tool names as keys and aggregation stats as values
        """
        raise NotImplementedError
