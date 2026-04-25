"""
Connection Pool - Advanced Connection Pooling

Implements advanced connection pooling for network resources.
Supports connection reuse, health monitoring, and dynamic sizing.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class PoolStatus(StrEnum):
    """Pool status."""

    IDLE = "idle"
    ACTIVE = "active"
    EXHAUSTED = "exhausted"
    CLOSING = "closing"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class Connection:
    """Connection object."""

    connection_id: str
    created_at: datetime
    last_used_at: datetime
    in_use: bool
    healthy: bool
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PoolConfig:
    """Connection pool configuration."""

    pool_name: str
    min_connections: int
    max_connections: int
    idle_timeout_seconds: int
    connection_timeout_seconds: int
    health_check_interval_seconds: int


class ConnectionPool:
    """
    Advanced connection pool.

    Features:
    - Connection reuse
    - Dynamic sizing
    - Health monitoring
    - Timeout management
    """

    def __init__(
        self,
        config: PoolConfig,
    ) -> None:
        """Initialize connection pool."""
        self._config = config
        self._connections: dict[str, Connection] = {}
        self._status = PoolStatus.IDLE
        self._connection_callback: Callable[[], Awaitable[str]] | None = None
        self._close_callback: Callable[[str], Awaitable[bool]] | None = None
        self._health_check_callback: Callable[[str], Awaitable[bool]] | None = None
        self._health_check_task: asyncio.Task | None = None
        self._acquire_semaphore = asyncio.Semaphore(config.max_connections)

    def set_connection_callback(
        self,
        callback: Callable[[], Awaitable[str]],
    ) -> None:
        """
        Set callback to create new connections.

        Args:
            callback: Async function to create connection
        """
        self._connection_callback = callback

    def set_close_callback(
        self,
        callback: Callable[[str], Awaitable[bool]],
    ) -> None:
        """
        Set callback to close connections.

        Args:
            callback: Async function to close connection
        """
        self._close_callback = callback

    def set_health_check_callback(
        self,
        callback: Callable[[str], Awaitable[bool]],
    ) -> None:
        """
        Set callback to check connection health.

        Args:
            callback: Async function to check health
        """
        self._health_check_callback = callback

    async def initialize(self) -> None:
        """Initialize pool with minimum connections."""
        self._status = PoolStatus.ACTIVE

        for _ in range(self._config.min_connections):
            await self._create_connection()

        # Start health check task
        self._health_check_task = asyncio.create_task(self._health_check_loop())

        logger.info(
            "pool_initialized",
            pool_name=self._config.pool_name,
            min_connections=self._config.min_connections,
        )

    async def acquire(self, timeout_seconds: int | None = None) -> str | None:
        """
        Acquire a connection from the pool.

        Args:
            timeout_seconds: Optional timeout

        Returns:
            Connection ID or None
        """
        timeout = timeout_seconds or self._config.connection_timeout_seconds

        try:
            async with asyncio.timeout(timeout):
                await self._acquire_semaphore.acquire()

                # Try to get idle connection
                connection_id = self._get_idle_connection()

                if not connection_id:
                    connection_id = await self._create_connection()

                if connection_id:
                    # Mark as in use
                    conn = self._connections[connection_id]
                    updated_conn = Connection(
                        connection_id=conn.connection_id,
                        created_at=conn.created_at,
                        last_used_at=datetime.now(UTC),
                        in_use=True,
                        healthy=conn.healthy,
                        metadata=conn.metadata,
                    )
                    self._connections[connection_id] = updated_conn

                    logger.debug(
                        "connection_acquired",
                        connection_id=connection_id,
                    )

                    return connection_id

                self._acquire_semaphore.release()
                return None

        except TimeoutError:
            logger.warning(
                "connection_acquire_timeout",
                pool_name=self._config.pool_name,
                timeout_seconds=timeout,
            )
            return None

    async def release(self, connection_id: str) -> bool:
        """
        Release a connection back to the pool.

        Args:
            connection_id: Connection identifier

        Returns:
            True if released
        """
        if connection_id not in self._connections:
            return False

        conn = self._connections[connection_id]

        updated_conn = Connection(
            connection_id=conn.connection_id,
            created_at=conn.created_at,
            last_used_at=datetime.now(UTC),
            in_use=False,
            healthy=conn.healthy,
            metadata=conn.metadata,
        )

        self._connections[connection_id] = updated_conn
        self._acquire_semaphore.release()

        logger.debug(
            "connection_released",
            connection_id=connection_id,
        )

        return True

    def _get_idle_connection(self) -> str | None:
        """
        Get an idle connection.

        Returns:
            Connection ID or None
        """
        for conn_id, conn in self._connections.items():
            if not conn.in_use and conn.healthy:
                return conn_id
        return None

    async def _create_connection(self) -> str | None:
        """
        Create a new connection.

        Returns:
            Connection ID or None
        """
        if not self._connection_callback:
            return None

        try:
            connection_id = await self._connection_callback()

            now = datetime.now(UTC)

            conn = Connection(
                connection_id=connection_id,
                created_at=now,
                last_used_at=now,
                in_use=False,
                healthy=True,
                metadata={},
            )

            self._connections[connection_id] = conn

            logger.debug(
                "connection_created",
                connection_id=connection_id,
            )

            return connection_id

        except Exception as e:
            logger.error(
                "connection_creation_failed",
                pool_name=self._config.pool_name,
                error=str(e),
            )
            return None

    async def close_connection(self, connection_id: str) -> bool:
        """
        Close a specific connection.

        Args:
            connection_id: Connection identifier

        Returns:
            True if closed
        """
        if connection_id not in self._connections:
            return False

        if self._close_callback:
            try:
                success = await self._close_callback(connection_id)

                if success:
                    del self._connections[connection_id]

                    logger.debug(
                        "connection_closed",
                        connection_id=connection_id,
                    )

                    return True
            except Exception as e:
                logger.error(
                    "connection_close_failed",
                    connection_id=connection_id,
                    error=str(e),
                )

        return False

    async def _health_check_loop(self) -> None:
        """Run health check loop for connections."""
        while self._status == PoolStatus.ACTIVE:
            await asyncio.sleep(self._config.health_check_interval_seconds)

            for conn_id, conn in list(self._connections.items()):
                if self._health_check_callback:
                    try:
                        healthy = await self._health_check_callback(conn_id)

                        updated_conn = Connection(
                            connection_id=conn.connection_id,
                            created_at=conn.created_at,
                            last_used_at=conn.last_used_at,
                            in_use=conn.in_use,
                            healthy=healthy,
                            metadata=conn.metadata,
                        )

                        self._connections[conn_id] = updated_conn

                        if not healthy and not conn.in_use:
                            await self.close_connection(conn_id)

                    except Exception as e:
                        logger.error(
                            "health_check_failed",
                            connection_id=conn_id,
                            error=str(e),
                        )

    async def cleanup_idle_connections(self) -> int:
        """
        Clean up idle connections.

        Returns:
            Number of connections cleaned up
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=self._config.idle_timeout_seconds)
        cleaned = 0

        for conn_id, conn in list(self._connections.items()):
            if not conn.in_use and conn.last_used_at < cutoff:
                if len(self._connections) > self._config.min_connections:
                    await self.close_connection(conn_id)
                    cleaned += 1

        if cleaned > 0:
            logger.info(
                "idle_connections_cleaned",
                count=cleaned,
            )

        return cleaned

    async def close_all(self) -> int:
        """
        Close all connections.

        Returns:
            Number of connections closed
        """
        self._status = PoolStatus.CLOSING

        if self._health_check_task:
            self._health_check_task.cancel()

        closed = 0
        for conn_id in list(self._connections.keys()):
            if await self.close_connection(conn_id):
                closed += 1

        self._status = PoolStatus.CLOSED

        logger.info(
            "pool_closed",
            pool_name=self._config.pool_name,
            connections_closed=closed,
        )

        return closed

    def get_pool_stats(self) -> dict[str, Any]:
        """
        Get pool statistics.

        Returns:
            Pool statistics
        """
        total_connections = len(self._connections)
        in_use_connections = sum(1 for conn in self._connections.values() if conn.in_use)
        idle_connections = total_connections - in_use_connections
        healthy_connections = sum(1 for conn in self._connections.values() if conn.healthy)

        return {
            "pool_name": self._config.pool_name,
            "status": self._status,
            "total_connections": total_connections,
            "in_use_connections": in_use_connections,
            "idle_connections": idle_connections,
            "healthy_connections": healthy_connections,
            "unhealthy_connections": total_connections - healthy_connections,
            "min_connections": self._config.min_connections,
            "max_connections": self._config.max_connections,
        }
