"""Tool Execution Ledger Service - Phase T6.

Service layer implementation for ToolExecutionLedger.

Implements PostgreSQL storage with Redis cache for hot queries.
OpenTelemetry span for each ledger write.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import structlog
from opentelemetry import trace
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from domain.tools.ledger import (
    ExecutionStatus,
    PolicyDecision,
    ToolExecutionLedger,
    ToolExecutionLedgerEntry,
)

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


class ToolExecutionLedgerService(ToolExecutionLedger):
    """Service layer implementation for tool execution ledger."""

    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
    ):
        """Initialize ToolExecutionLedgerService.

        Args:
            db: Database session
            redis: Redis client for caching
        """
        self._db = db
        self._redis = redis

    def _hash_input(self, input_data: dict) -> str:
        """Hash input data for ledger.

        Args:
            input_data: Input data dictionary

        Returns:
            SHA256 hash string
        """
        input_str = json.dumps(input_data, sort_keys=True)
        return hashlib.sha256(input_str.encode()).hexdigest()

    def _hash_output(self, output_data: dict | None) -> str | None:
        """Hash output data for ledger.

        Args:
            output_data: Output data dictionary

        Returns:
            SHA256 hash string or None
        """
        if output_data is None:
            return None
        output_str = json.dumps(output_data, sort_keys=True)
        return hashlib.sha256(output_str.encode()).hexdigest()

    def _cache_key(self, execution_id: UUID) -> str:
        """Generate Redis cache key for ledger entry.

        Args:
            execution_id: Execution ID

        Returns:
            Cache key string
        """
        return f"tool_ledger:{execution_id}"

    async def create_entry(
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
        with tracer.start_as_current_span("tool_ledger.create_entry") as span:
            execution_id = uuid4()
            now = datetime.now(UTC)

            entry = ToolExecutionLedgerEntry(
                execution_id=execution_id,
                tenant_id=tenant_id,
                account_id=account_id,
                session_id=session_id,
                tool_name=tool_name,
                tool_spec_version=tool_spec_version,
                input_hash=input_hash,
                status=ExecutionStatus.PENDING,
                created_at=now,
                updated_at=now,
                workflow_id=workflow_id,
                task_id=task_id,
            )

            span.set_attributes({
                "execution_id": str(execution_id),
                "tenant_id": tenant_id,
                "account_id": account_id,
                "tool_name": tool_name,
            })

            # Store in PostgreSQL
            # TODO: Implement actual PostgreSQL storage
            # For now, cache in Redis
            await self._redis.set(
                self._cache_key(execution_id),
                json.dumps({
                    "execution_id": str(execution_id),
                    "tenant_id": tenant_id,
                    "account_id": account_id,
                    "session_id": session_id,
                    "tool_name": tool_name,
                    "tool_spec_version": tool_spec_version,
                    "input_hash": input_hash,
                    "status": entry.status.value,
                    "created_at": entry.created_at.isoformat(),
                    "updated_at": entry.updated_at.isoformat(),
                    "workflow_id": workflow_id,
                    "task_id": task_id,
                }),
                ex=3600,  # 1 hour TTL
            )

            logger.info(
                "tool_ledger_entry_created",
                execution_id=str(execution_id),
                tenant_id=tenant_id,
                account_id=account_id,
                tool_name=tool_name,
            )

            return entry

    async def update_entry_status(
        self,
        execution_id: UUID,
        status: ExecutionStatus,
    ) -> None:
        """Update ledger entry status.

        Args:
            execution_id: Execution ID
            status: New status
        """
        with tracer.start_as_current_span("tool_ledger.update_status") as span:
            span.set_attributes({
                "execution_id": str(execution_id),
                "status": status.value,
            })

            # Update in PostgreSQL
            # TODO: Implement actual PostgreSQL update
            # For now, update in Redis cache
            cache_key = self._cache_key(execution_id)
            cached = await self._redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                data["status"] = status.value
                data["updated_at"] = datetime.now(UTC).isoformat()
                await self._redis.set(cache_key, json.dumps(data), ex=3600)

            logger.info(
                "tool_ledger_status_updated",
                execution_id=str(execution_id),
                status=status.value,
            )

    async def finalize_entry(
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
        with tracer.start_as_current_span("tool_ledger.finalize") as span:
            span.set_attributes({
                "execution_id": str(execution_id),
                "status": status.value,
            })
            if latency_ms is not None:
                span.set_attribute("latency_ms", latency_ms)
            span.set_attribute("sandbox_used", sandbox_used)

            # Update in PostgreSQL
            # TODO: Implement actual PostgreSQL update
            # For now, update in Redis cache
            cache_key = self._cache_key(execution_id)
            cached = await self._redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                data["status"] = status.value
                data["updated_at"] = datetime.now(UTC).isoformat()
                data["output_hash"] = output_hash
                data["latency_ms"] = latency_ms
                data["error_code"] = error_code
                data["error_message"] = error_message
                data["policy_decision"] = policy_decision.value if policy_decision else None
                data["sandbox_used"] = sandbox_used
                data["approval_id"] = approval_id
                data["degraded_mode"] = degraded_mode
                data["compensation_handler_id"] = compensation_handler_id
                await self._redis.set(cache_key, json.dumps(data), ex=3600)

            logger.info(
                "tool_ledger_entry_finalized",
                execution_id=str(execution_id),
                status=status.value,
                latency_ms=latency_ms,
            )

    async def query_by_tenant(
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
        # TODO: Implement PostgreSQL query
        # For now, return empty list
        return []

    async def query_by_account(
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
        # TODO: Implement PostgreSQL query
        # For now, return empty list
        return []

    async def query_by_session(
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
        # TODO: Implement PostgreSQL query
        # For now, return empty list
        return []

    async def query_by_tool(
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
        # TODO: Implement PostgreSQL query
        # For now, return empty list
        return []

    async def aggregate_by_tool(
        self,
        time_range: tuple[datetime, datetime] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Aggregate ledger entries by tool.

        Args:
            time_range: Optional time range filter

        Returns:
            Dictionary with tool names as keys and aggregation stats as values
        """
        # TODO: Implement PostgreSQL aggregation
        # For now, return empty dict
        return {}
