"""
CQRS Bus - Command/Query Separation

Implements CQRS pattern with separate command and query buses.
Separates write operations (commands) from read operations (queries).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")
R = TypeVar("R")


class CommandStatus(StrEnum):
    """Command status."""

    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Result of command execution."""

    command_id: str
    status: CommandStatus
    result: Any | None
    error: str | None
    executed_at: datetime
    duration_ms: float


@dataclass(frozen=True, slots=True)
class QueryResult:
    """Result of query execution."""

    query_id: str
    result: Any | None
    error: str | None
    executed_at: datetime
    duration_ms: float


class CommandBus:
    """
    Command bus for write operations.

    Features:
    - Command registration
    - Command execution
    - Result tracking
    - Error handling
    """

    def __init__(self) -> None:
        """Initialize command bus."""
        self._handlers: dict[str, Callable[[Any], Awaitable[Any]]] = {}
        self._results: dict[str, CommandResult] = {}

    def register_command(
        self,
        command_type: str,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> None:
        """
        Register a command handler.

        Args:
            command_type: Command type
            handler: Command handler
        """
        self._handlers[command_type] = handler

        logger.info(
            "command_handler_registered",
            command_type=command_type,
        )

    async def execute(
        self,
        command_type: str,
        payload: Any,
    ) -> CommandResult:
        """
        Execute a command.

        Args:
            command_type: Command type
            payload: Command payload

        Returns:
            Command result
        """
        command_id = f"{command_type}-{datetime.now(UTC).timestamp()}"
        started_at = datetime.now(UTC)

        if command_type not in self._handlers:
            result = CommandResult(
                command_id=command_id,
                status=CommandStatus.FAILED,
                result=None,
                error=f"No handler registered for command type: {command_type}",
                executed_at=started_at,
                duration_ms=0,
            )

            self._results[command_id] = result
            return result

        try:
            result_value = await self._handlers[command_type](payload)

            completed_at = datetime.now(UTC)
            duration_ms = (completed_at - started_at).total_seconds() * 1000

            result = CommandResult(
                command_id=command_id,
                status=CommandStatus.COMPLETED,
                result=result_value,
                error=None,
                executed_at=completed_at,
                duration_ms=duration_ms,
            )

            logger.info(
                "command_executed",
                command_id=command_id,
                command_type=command_type,
                duration_ms=duration_ms,
            )

        except Exception as e:
            completed_at = datetime.now(UTC)
            duration_ms = (completed_at - started_at).total_seconds() * 1000

            result = CommandResult(
                command_id=command_id,
                status=CommandStatus.FAILED,
                result=None,
                error=str(e),
                executed_at=completed_at,
                duration_ms=duration_ms,
            )

            logger.error(
                "command_execution_failed",
                command_id=command_id,
                command_type=command_type,
                error=str(e),
            )

        self._results[command_id] = result
        return result

    def get_command_result(self, command_id: str) -> CommandResult | None:
        """
        Get command result by ID.

        Args:
            command_id: Command identifier

        Returns:
            Command result or None
        """
        return self._results.get(command_id)


class QueryBus:
    """
    Query bus for read operations.

    Features:
    - Query registration
    - Query execution
    - Result caching
    - Error handling
    """

    def __init__(self) -> None:
        """Initialize query bus."""
        self._handlers: dict[str, Callable[[Any], Awaitable[Any]]] = {}
        self._cache: dict[str, tuple[Any, datetime]] = {}
        self._cache_ttl_seconds = 60

    def register_query(
        self,
        query_type: str,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> None:
        """
        Register a query handler.

        Args:
            query_type: Query type
            handler: Query handler
        """
        self._handlers[query_type] = handler

        logger.info(
            "query_handler_registered",
            query_type=query_type,
        )

    async def execute(
        self,
        query_type: str,
        payload: Any,
        use_cache: bool = True,
    ) -> QueryResult:
        """
        Execute a query.

        Args:
            query_type: Query type
            payload: Query payload
            use_cache: Whether to use cache

        Returns:
            Query result
        """
        query_id = f"{query_type}-{datetime.now(UTC).timestamp()}"
        started_at = datetime.now(UTC)

        if query_type not in self._handlers:
            return QueryResult(
                query_id=query_id,
                result=None,
                error=f"No handler registered for query type: {query_type}",
                executed_at=started_at,
                duration_ms=0,
            )

        # Check cache
        cache_key = f"{query_type}:{str(payload)}"
        if use_cache and cache_key in self._cache:
            cached_result, cached_at = self._cache[cache_key]
            age = (datetime.now(UTC) - cached_at).total_seconds()

            if age < self._cache_ttl_seconds:
                completed_at = datetime.now(UTC)
                duration_ms = (completed_at - started_at).total_seconds() * 1000

                result = QueryResult(
                    query_id=query_id,
                    result=cached_result,
                    error=None,
                    executed_at=completed_at,
                    duration_ms=duration_ms,
                )

                logger.debug(
                    "query_cache_hit",
                    query_id=query_id,
                    query_type=query_type,
                )

                return result

        try:
            result_value = await self._handlers[query_type](payload)

            # Cache result
            self._cache[cache_key] = (result_value, datetime.now(UTC))

            completed_at = datetime.now(UTC)
            duration_ms = (completed_at - started_at).total_seconds() * 1000

            result = QueryResult(
                query_id=query_id,
                result=result_value,
                error=None,
                executed_at=completed_at,
                duration_ms=duration_ms,
            )

            logger.debug(
                "query_executed",
                query_id=query_id,
                query_type=query_type,
                duration_ms=duration_ms,
            )

        except Exception as e:
            completed_at = datetime.now(UTC)
            duration_ms = (completed_at - started_at).total_seconds() * 1000

            result = QueryResult(
                query_id=query_id,
                result=None,
                error=str(e),
                executed_at=completed_at,
                duration_ms=duration_ms,
            )

            logger.error(
                "query_execution_failed",
                query_id=query_id,
                query_type=query_type,
                error=str(e),
            )

        return result

    def clear_cache(self, query_type: str | None = None) -> int:
        """
        Clear query cache.

        Args:
            query_type: Query type to clear (None for all)

        Returns:
            Number of cache entries cleared
        """
        if query_type:
            to_remove = [key for key in self._cache if key.startswith(f"{query_type}:")]
            for key in to_remove:
                del self._cache[key]
            return len(to_remove)
        count = len(self._cache)
        self._cache.clear()
        return count

    def set_cache_ttl(self, ttl_seconds: int) -> None:
        """
        Set cache TTL.

        Args:
            ttl_seconds: TTL in seconds
        """
        self._cache_ttl_seconds = ttl_seconds


class CQRSBus:
    """
    Combined CQRS bus for command/query separation.

    Features:
    - Command bus integration
    - Query bus integration
    - Unified interface
    - Statistics tracking
    """

    def __init__(
        self,
        command_bus: CommandBus | None = None,
        query_bus: QueryBus | None = None,
    ) -> None:
        """Initialize CQRS bus."""
        self._command_bus = command_bus or CommandBus()
        self._query_bus = query_bus or QueryBus()

    def get_command_bus(self) -> CommandBus:
        """Get the command bus."""
        return self._command_bus

    def get_query_bus(self) -> QueryBus:
        """Get the query bus."""
        return self._query_bus

    async def execute_command(
        self,
        command_type: str,
        payload: Any,
    ) -> CommandResult:
        """
        Execute a command.

        Args:
            command_type: Command type
            payload: Command payload

        Returns:
            Command result
        """
        return await self._command_bus.execute(command_type, payload)

    async def execute_query(
        self,
        query_type: str,
        payload: Any,
        use_cache: bool = True,
    ) -> QueryResult:
        """
        Execute a query.

        Args:
            query_type: Query type
            payload: Query payload
            use_cache: Whether to use cache

        Returns:
            Query result
        """
        return await self._query_bus.execute(query_type, payload, use_cache)

    def get_cqrs_stats(self) -> dict[str, Any]:
        """
        Get CQRS statistics.

        Returns:
            CQRS statistics
        """
        return {
            "command_bus": {
                "registered_handlers": len(self._command_bus._handlers),
                "total_executions": len(self._command_bus._results),
            },
            "query_bus": {
                "registered_handlers": len(self._query_bus._handlers),
                "cache_entries": len(self._query_bus._cache),
                "cache_ttl_seconds": self._query_bus._cache_ttl_seconds,
            },
        }
