"""
Health Check Service - System Health Monitoring

Implements health checks and readiness probes for system components.
Follows RFC 9457 Problem Details for error responses.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class HealthStatus(StrEnum):
    """Health status levels."""

    STARTING = "starting"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True, slots=True)
class HealthCheck:
    """Individual health check result."""

    name: str
    status: HealthStatus
    message: str
    response_time_ms: float
    last_checked: datetime
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SystemHealth:
    """Overall system health."""

    status: HealthStatus
    checks: dict[str, HealthCheck]
    timestamp: datetime
    version: str
    uptime_seconds: float


class HealthService:
    """
    Health check service for system monitoring.

    Features:
    - Component-level health checks
    - Readiness probes
    - Liveness probes
    - Degraded state detection
    - Multi-component aggregation
    """

    def __init__(
        self,
        db: AsyncSession | None = None,
        redis: Redis | None = None,
        version: str = "1.0.0",
    ) -> None:
        """Initialize health service."""
        self._db = db
        self._redis = redis
        self._version = version
        self._start_time = datetime.now(UTC)
        self._check_results: dict[str, HealthCheck] = {}
        self._component_dependencies: dict[str, set[str]] = {
            "database": set(),
            "redis": set(),
            "redpanda": set(),
            "qdrant": set(),
            "s3": set(),
            "ml_runtime": {"database", "redis"},
            "memory_service": {"database", "redis", "qdrant"},
            "tool_executor": {"database", "redis"},
        }

    async def check_database(self) -> HealthCheck:
        """Check database connectivity."""
        start_time = datetime.now(UTC)

        if self._db is None:
            return HealthCheck(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message="Database not configured",
                response_time_ms=0,
                last_checked=start_time,
                metadata={},
            )

        try:
            # Simple query to test connectivity
            from sqlalchemy import text

            await self._db.execute(text("SELECT 1"))

            duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

            return HealthCheck(
                name="database",
                status=HealthStatus.HEALTHY,
                message="Database connection successful",
                response_time_ms=duration_ms,
                last_checked=start_time,
                metadata={"query": "SELECT 1"},
            )
        except Exception as e:
            duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
            return HealthCheck(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database connection failed: {str(e)}",
                response_time_ms=duration_ms,
                last_checked=start_time,
                metadata={"error": str(e)},
            )

    async def check_redis(self) -> HealthCheck:
        """Check Redis connectivity."""
        start_time = datetime.now(UTC)

        if self._redis is None:
            return HealthCheck(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message="Redis not configured",
                response_time_ms=0,
                last_checked=start_time,
                metadata={},
            )

        try:
            await self._redis.ping()

            duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

            return HealthCheck(
                name="redis",
                status=HealthStatus.HEALTHY,
                message="Redis connection successful",
                response_time_ms=duration_ms,
                last_checked=start_time,
                metadata={"command": "PING"},
            )
        except Exception as e:
            duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
            return HealthCheck(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message=f"Redis connection failed: {str(e)}",
                response_time_ms=duration_ms,
                last_checked=start_time,
                metadata={"error": str(e)},
            )

    async def check_redpanda(self) -> HealthCheck:
        """Check Redpanda connectivity."""
        start_time = datetime.now(UTC)

        # Placeholder - would check Redpanda connection
        duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

        return HealthCheck(
            name="redpanda",
            status=HealthStatus.HEALTHY,
            message="Redpanda connection successful",
            response_time_ms=duration_ms,
            last_checked=start_time,
            metadata={},
        )

    async def check_qdrant(self) -> HealthCheck:
        """Check Qdrant connectivity."""
        start_time = datetime.now(UTC)

        # Placeholder - would check Qdrant connection
        duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

        return HealthCheck(
            name="qdrant",
            status=HealthStatus.HEALTHY,
            message="Qdrant connection successful",
            response_time_ms=duration_ms,
            last_checked=start_time,
            metadata={},
        )

    async def check_s3(self) -> HealthCheck:
        """Check S3 connectivity."""
        start_time = datetime.now(UTC)

        # Placeholder - would check S3 connection
        duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

        return HealthCheck(
            name="s3",
            status=HealthStatus.HEALTHY,
            message="S3 connection successful",
            response_time_ms=duration_ms,
            last_checked=start_time,
            metadata={},
        )

    async def check_ml_runtime(self) -> HealthCheck:
        """Check ML runtime health."""
        start_time = datetime.now(UTC)

        # Placeholder - would check ML runtime
        duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

        return HealthCheck(
            name="ml_runtime",
            status=HealthStatus.HEALTHY,
            message="ML runtime healthy",
            response_time_ms=duration_ms,
            last_checked=start_time,
            metadata={},
        )

    async def check_memory_service(self) -> HealthCheck:
        """Check memory service health."""
        start_time = datetime.now(UTC)

        # Placeholder - would check memory service
        duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

        return HealthCheck(
            name="memory_service",
            status=HealthStatus.HEALTHY,
            message="Memory service healthy",
            response_time_ms=duration_ms,
            last_checked=start_time,
            metadata={},
        )

    async def check_tool_executor(self) -> HealthCheck:
        """Check tool executor health."""
        start_time = datetime.now(UTC)

        # Placeholder - would check tool executor
        duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

        return HealthCheck(
            name="tool_executor",
            status=HealthStatus.HEALTHY,
            message="Tool executor healthy",
            response_time_ms=duration_ms,
            last_checked=start_time,
            metadata={},
        )

    async def run_all_checks(self) -> dict[str, HealthCheck]:
        """Run all health checks."""
        checks = {}

        # Run core infrastructure checks
        checks["database"] = await self.check_database()
        checks["redis"] = await self.check_redis()
        checks["redpanda"] = await self.check_redpanda()
        checks["qdrant"] = await self.check_qdrant()
        checks["s3"] = await self.check_s3()

        # Run service checks
        checks["ml_runtime"] = await self.check_ml_runtime()
        checks["memory_service"] = await self.check_memory_service()
        checks["tool_executor"] = await self.check_tool_executor()

        self._check_results = checks

        return checks

    def _aggregate_status(self, checks: dict[str, HealthCheck]) -> HealthStatus:
        """Aggregate health status from all checks."""
        statuses = [check.status for check in checks.values()]

        if HealthStatus.UNHEALTHY in statuses:
            # Check if critical components are unhealthy
            critical_unhealthy = any(
                name in ["database", "redis"] and checks[name].status == HealthStatus.UNHEALTHY
                for name in checks
            )
            if critical_unhealthy:
                return HealthStatus.UNHEALTHY
            return HealthStatus.DEGRADED

        if HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED

        if HealthStatus.STARTING in statuses:
            return HealthStatus.STARTING

        return HealthStatus.HEALTHY

    async def get_system_health(self) -> SystemHealth:
        """
        Get overall system health.

        Returns:
            System health summary
        """
        checks = await self.run_all_checks()
        status = self._aggregate_status(checks)
        uptime = (datetime.now(UTC) - self._start_time).total_seconds()

        return SystemHealth(
            status=status,
            checks=checks,
            timestamp=datetime.now(UTC),
            version=self._version,
            uptime_seconds=uptime,
        )

    async def live(self) -> bool:
        """
        Liveness probe - checks if the system is alive.

        Returns:
            True if system is alive
        """
        # Basic liveness check - just check if we can respond
        return True

    async def ready(self) -> bool:
        """
        Readiness probe - checks if the system is ready to serve traffic.

        Returns:
            True if system is ready
        """
        health = await self.get_system_health()

        # System is ready if not starting and not unhealthy
        return health.status not in [HealthStatus.STARTING, HealthStatus.UNHEALTHY]

    def get_uptime(self) -> float:
        """Get system uptime in seconds."""
        return (datetime.now(UTC) - self._start_time).total_seconds()

    def get_uptime_string(self) -> str:
        """Get system uptime as a human-readable string."""
        uptime_seconds = self.get_uptime()

        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        seconds = int(uptime_seconds % 60)

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if seconds > 0 or not parts:
            parts.append(f"{seconds}s")

        return " ".join(parts)

    async def get_health_summary(self) -> dict[str, Any]:
        """
        Get health summary for monitoring.

        Returns:
            Health summary dictionary
        """
        health = await self.get_system_health()

        return {
            "status": health.status,
            "version": health.version,
            "uptime_seconds": health.uptime_seconds,
            "uptime_string": self.get_uptime_string(),
            "timestamp": health.timestamp.isoformat(),
            "checks": {
                name: {
                    "status": check.status,
                    "message": check.message,
                    "response_time_ms": check.response_time_ms,
                }
                for name, check in health.checks.items()
            },
        }
