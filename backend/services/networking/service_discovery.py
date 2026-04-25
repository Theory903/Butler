"""
Service Discovery - Service Discovery with Health Checking

Implements service discovery with health checking.
Supports service registration, health monitoring, and load balancing.
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


class HealthStatus(StrEnum):
    """Health status."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ServiceInstance:
    """Service instance."""

    instance_id: str
    service_name: str
    host: str
    port: int
    metadata: dict[str, str]
    registered_at: datetime
    last_heartbeat: datetime


@dataclass(frozen=True, slots=True)
class HealthCheck:
    """Health check result."""

    instance_id: str
    status: HealthStatus
    checked_at: datetime
    response_time_ms: float
    details: dict[str, Any]


class ServiceDiscovery:
    """
    Service discovery with health checking.

    Features:
    - Service registration
    - Health monitoring
    - Instance discovery
    - Load balancing support
    """

    def __init__(self) -> None:
        """Initialize service discovery."""
        self._services: dict[
            str, dict[str, ServiceInstance]
        ] = {}  # service_name -> instance_id -> instance
        self._health_checks: dict[str, list[HealthCheck]] = {}  # instance_id -> checks
        self._health_check_callback: Callable[[ServiceInstance], Awaitable[HealthCheck]] | None = (
            None
        )
        self._health_check_tasks: dict[str, asyncio.Task] = {}

    def set_health_check_callback(
        self,
        callback: Callable[[ServiceInstance], Awaitable[HealthCheck]],
    ) -> None:
        """
        Set health check callback.

        Args:
            callback: Async function to check health
        """
        self._health_check_callback = callback

    def register_service(
        self,
        instance_id: str,
        service_name: str,
        host: str,
        port: int,
        metadata: dict[str, str] | None = None,
    ) -> ServiceInstance:
        """
        Register a service instance.

        Args:
            instance_id: Instance identifier
            service_name: Service name
            host: Host address
            port: Port
            metadata: Optional metadata

        Returns:
            Service instance
        """
        now = datetime.now(UTC)

        instance = ServiceInstance(
            instance_id=instance_id,
            service_name=service_name,
            host=host,
            port=port,
            metadata=metadata or {},
            registered_at=now,
            last_heartbeat=now,
        )

        if service_name not in self._services:
            self._services[service_name] = {}

        self._services[service_name][instance_id] = instance

        logger.info(
            "service_registered",
            instance_id=instance_id,
            service_name=service_name,
            host=host,
            port=port,
        )

        return instance

    def deregister_service(
        self,
        instance_id: str,
        service_name: str,
    ) -> bool:
        """
        Deregister a service instance.

        Args:
            instance_id: Instance identifier
            service_name: Service name

        Returns:
            True if deregistered
        """
        if service_name in self._services and instance_id in self._services[service_name]:
            del self._services[service_name][instance_id]

            # Stop health check task
            if instance_id in self._health_check_tasks:
                self._health_check_tasks[instance_id].cancel()
                del self._health_check_tasks[instance_id]

            logger.info(
                "service_deregistered",
                instance_id=instance_id,
                service_name=service_name,
            )

            return True
        return False

    def discover_service(
        self,
        service_name: str,
        healthy_only: bool = True,
    ) -> list[ServiceInstance]:
        """
        Discover service instances.

        Args:
            service_name: Service name
            healthy_only: Only return healthy instances

        Returns:
            List of service instances
        """
        instances = list(self._services.get(service_name, {}).values())

        if healthy_only:
            instances = [inst for inst in instances if self._is_healthy(inst.instance_id)]

        return instances

    def _is_healthy(self, instance_id: str) -> bool:
        """
        Check if instance is healthy.

        Args:
            instance_id: Instance identifier

        Returns:
            True if healthy
        """
        checks = self._health_checks.get(instance_id, [])

        if not checks:
            return True  # Assume healthy if no checks

        # Check most recent check
        latest_check = max(checks, key=lambda c: c.checked_at)

        # Check if check is recent (within 30 seconds)
        if (datetime.now(UTC) - latest_check.checked_at).total_seconds() > 30:
            return False

        return latest_check.status == HealthStatus.HEALTHY

    async def heartbeat(
        self,
        instance_id: str,
        service_name: str,
    ) -> bool:
        """
        Update heartbeat for instance.

        Args:
            instance_id: Instance identifier
            service_name: Service name

        Returns:
            True if updated
        """
        if service_name in self._services and instance_id in self._services[service_name]:
            instance = self._services[service_name][instance_id]

            updated_instance = ServiceInstance(
                instance_id=instance.instance_id,
                service_name=instance.service_name,
                host=instance.host,
                port=instance.port,
                metadata=instance.metadata,
                registered_at=instance.registered_at,
                last_heartbeat=datetime.now(UTC),
            )

            self._services[service_name][instance_id] = updated_instance

            return True
        return False

    async def start_health_checks(
        self,
        interval_seconds: int = 10,
    ) -> None:
        """
        Start health checking for all instances.

        Args:
            interval_seconds: Check interval
        """
        for _service_name, instances in self._services.items():
            for instance_id, _instance in instances.items():
                if (
                    instance_id not in self._health_check_tasks
                    or self._health_check_tasks[instance_id].done()
                ):
                    self._health_check_tasks[instance_id] = asyncio.create_task(
                        self._health_check_loop(instance_id, interval_seconds)
                    )

    async def _health_check_loop(
        self,
        instance_id: str,
        interval_seconds: int,
    ) -> None:
        """
        Run health check loop for instance.

        Args:
            instance_id: Instance identifier
            interval_seconds: Check interval
        """
        while True:
            # Find instance
            instance = None
            for service_instances in self._services.values():
                if instance_id in service_instances:
                    instance = service_instances[instance_id]
                    break

            if not instance:
                # Instance deregistered, stop checking
                break

            # Perform health check
            if self._health_check_callback:
                try:
                    check = await self._health_check_callback(instance)

                    if instance_id not in self._health_checks:
                        self._health_checks[instance_id] = []

                    self._health_checks[instance_id].append(check)

                    # Keep only last 10 checks
                    if len(self._health_checks[instance_id]) > 10:
                        self._health_checks[instance_id] = self._health_checks[instance_id][-10:]

                except Exception as e:
                    logger.error(
                        "health_check_failed",
                        instance_id=instance_id,
                        error=str(e),
                    )

            # Wait for next check
            await asyncio.sleep(interval_seconds)

    def get_health_checks(
        self,
        instance_id: str | None = None,
        limit: int = 100,
    ) -> list[HealthCheck]:
        """
        Get health check results.

        Args:
            instance_id: Filter by instance
            limit: Maximum number of results

        Returns:
            List of health checks
        """
        if instance_id:
            checks = self._health_checks.get(instance_id, [])
            return sorted(checks, key=lambda c: c.checked_at, reverse=True)[:limit]

        # Get all checks
        all_checks = []
        for checks in self._health_checks.values():
            all_checks.extend(checks)

        return sorted(all_checks, key=lambda c: c.checked_at, reverse=True)[:limit]

    def cleanup_stale_instances(
        self,
        heartbeat_timeout_seconds: int = 60,
    ) -> int:
        """
        Clean up stale instances.

        Args:
            heartbeat_timeout_seconds: Heartbeat timeout

        Returns:
            Number of instances cleaned up
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=heartbeat_timeout_seconds)
        cleaned = 0

        for service_name, instances in list(self._services.items()):
            for instance_id, instance in list(instances.items()):
                if instance.last_heartbeat < cutoff:
                    self.deregister_service(instance_id, service_name)
                    cleaned += 1

        if cleaned > 0:
            logger.info(
                "stale_instances_cleaned",
                count=cleaned,
            )

        return cleaned

    def get_discovery_stats(self) -> dict[str, Any]:
        """
        Get service discovery statistics.

        Returns:
            Discovery statistics
        """
        total_services = len(self._services)
        total_instances = sum(len(instances) for instances in self._services.values())

        healthy_instances = 0
        for instance_id in self._health_checks:
            if self._is_healthy(instance_id):
                healthy_instances += 1

        return {
            "total_services": total_services,
            "total_instances": total_instances,
            "healthy_instances": healthy_instances,
            "unhealthy_instances": total_instances - healthy_instances,
            "total_health_checks": sum(len(checks) for checks in self._health_checks.values()),
        }
