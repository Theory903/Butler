"""
Service Mesh Integration - Service Mesh Patterns

Implements service mesh integration patterns for gateway.
Supports service discovery, load balancing, and observability integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class LoadBalancingStrategy(StrEnum):
    """Load balancing strategy."""

    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    RANDOM = "random"
    WEIGHTED = "weighted"


@dataclass(frozen=True, slots=True)
class ServiceEndpoint:
    """Service endpoint."""

    service_name: str
    endpoint_id: str
    host: str
    port: int
    weight: int
    healthy: bool
    last_health_check: datetime


@dataclass(frozen=True, slots=True)
class MeshConfig:
    """Service mesh configuration."""

    service_name: str
    namespace: str
    load_balancing: LoadBalancingStrategy
    circuit_breaker_enabled: bool
    retry_attempts: int
    timeout_seconds: int


class ServiceMeshIntegration:
    """
    Service mesh integration for gateway.

    Features:
    - Service discovery
    - Load balancing
    - Health checking
    - Observability integration
    """

    def __init__(self) -> None:
        """Initialize service mesh integration."""
        self._endpoints: dict[str, list[ServiceEndpoint]] = {}  # service_name -> endpoints
        self._configs: dict[str, MeshConfig] = {}  # service_name -> config
        self._round_robin_indices: dict[str, int] = {}
        self._connection_counts: dict[str, int] = {}

    def register_endpoint(
        self,
        service_name: str,
        endpoint_id: str,
        host: str,
        port: int,
        weight: int = 1,
    ) -> ServiceEndpoint:
        """
        Register a service endpoint.

        Args:
            service_name: Service name
            endpoint_id: Endpoint identifier
            host: Endpoint host
            port: Endpoint port
            weight: Endpoint weight for load balancing

        Returns:
            Service endpoint
        """
        endpoint = ServiceEndpoint(
            service_name=service_name,
            endpoint_id=endpoint_id,
            host=host,
            port=port,
            weight=weight,
            healthy=True,
            last_health_check=datetime.now(UTC),
        )

        if service_name not in self._endpoints:
            self._endpoints[service_name] = []
            self._round_robin_indices[service_name] = 0

        self._endpoints[service_name].append(endpoint)

        logger.info(
            "service_endpoint_registered",
            service_name=service_name,
            endpoint_id=endpoint_id,
            host=host,
            port=port,
        )

        return endpoint

    def set_mesh_config(
        self,
        config: MeshConfig,
    ) -> None:
        """
        Set service mesh configuration.

        Args:
            config: Mesh configuration
        """
        self._configs[config.service_name] = config

        logger.info(
            "mesh_config_set",
            service_name=config.service_name,
            load_balancing=config.load_balancing,
        )

    async def select_endpoint(
        self,
        service_name: str,
    ) -> ServiceEndpoint | None:
        """
        Select an endpoint using load balancing.

        Args:
            service_name: Service name

        Returns:
            Selected endpoint or None
        """
        if service_name not in self._endpoints:
            logger.warning(
                "service_not_found",
                service_name=service_name,
            )
            return None

        endpoints = self._endpoints[service_name]
        healthy_endpoints = [e for e in endpoints if e.healthy]

        if not healthy_endpoints:
            logger.warning(
                "no_healthy_endpoints",
                service_name=service_name,
            )
            return None

        config = self._configs.get(service_name)
        strategy = config.load_balancing if config else LoadBalancingStrategy.ROUND_ROBIN

        if strategy == LoadBalancingStrategy.ROUND_ROBIN:
            return self._round_robin_select(service_name, healthy_endpoints)
        if strategy == LoadBalancingStrategy.LEAST_CONNECTIONS:
            return self._least_connections_select(healthy_endpoints)
        if strategy == LoadBalancingStrategy.RANDOM:
            return self._random_select(healthy_endpoints)
        if strategy == LoadBalancingStrategy.WEIGHTED:
            return self._weighted_select(healthy_endpoints)

        return healthy_endpoints[0]

    def _round_robin_select(
        self,
        service_name: str,
        endpoints: list[ServiceEndpoint],
    ) -> ServiceEndpoint:
        """Select endpoint using round-robin."""
        index = self._round_robin_indices[service_name]
        endpoint = endpoints[index % len(endpoints)]
        self._round_robin_indices[service_name] = (index + 1) % len(endpoints)
        return endpoint

    def _least_connections_select(
        self,
        endpoints: list[ServiceEndpoint],
    ) -> ServiceEndpoint:
        """Select endpoint with least connections."""
        min_connections = float("inf")
        selected = endpoints[0]

        for endpoint in endpoints:
            connections = self._connection_counts.get(endpoint.endpoint_id, 0)
            if connections < min_connections:
                min_connections = connections
                selected = endpoint

        return selected

    def _random_select(
        self,
        endpoints: list[ServiceEndpoint],
    ) -> ServiceEndpoint:
        """Select endpoint randomly."""
        import random

        return random.choice(endpoints)

    def _weighted_select(
        self,
        endpoints: list[ServiceEndpoint],
    ) -> ServiceEndpoint:
        """Select endpoint using weighted selection."""
        import random

        total_weight = sum(e.weight for e in endpoints)
        if total_weight == 0:
            return endpoints[0]

        rand = random.uniform(0, total_weight)
        cumulative = 0

        for endpoint in endpoints:
            cumulative += endpoint.weight
            if rand <= cumulative:
                return endpoint

        return endpoints[-1]

    async def health_check(
        self,
        service_name: str,
        endpoint_id: str,
    ) -> bool:
        """
        Perform health check on endpoint.

        Args:
            service_name: Service name
            endpoint_id: Endpoint identifier

        Returns:
            True if healthy
        """
        if service_name not in self._endpoints:
            return False

        for i, endpoint in enumerate(self._endpoints[service_name]):
            if endpoint.endpoint_id == endpoint_id:
                # In production, this would perform actual health check
                # For now, assume healthy
                healthy = True

                # Update endpoint
                self._endpoints[service_name][i] = ServiceEndpoint(
                    service_name=endpoint.service_name,
                    endpoint_id=endpoint.endpoint_id,
                    host=endpoint.host,
                    port=endpoint.port,
                    weight=endpoint.weight,
                    healthy=healthy,
                    last_health_check=datetime.now(UTC),
                )

                return healthy

        return False

    def increment_connections(self, endpoint_id: str) -> None:
        """Increment connection count for endpoint."""
        self._connection_counts[endpoint_id] = self._connection_counts.get(endpoint_id, 0) + 1

    def decrement_connections(self, endpoint_id: str) -> None:
        """Decrement connection count for endpoint."""
        if endpoint_id in self._connection_counts:
            self._connection_counts[endpoint_id] = max(0, self._connection_counts[endpoint_id] - 1)

    def get_service_endpoints(
        self,
        service_name: str,
    ) -> list[ServiceEndpoint]:
        """
        Get all endpoints for a service.

        Args:
            service_name: Service name

        Returns:
            List of endpoints
        """
        return self._endpoints.get(service_name, [])

    def get_mesh_stats(self) -> dict[str, Any]:
        """
        Get service mesh statistics.

        Returns:
            Mesh statistics
        """
        total_services = len(self._endpoints)
        total_endpoints = sum(len(endpoints) for endpoints in self._endpoints.values())
        healthy_endpoints = sum(
            len([e for e in endpoints if e.healthy]) for endpoints in self._endpoints.values()
        )

        return {
            "total_services": total_services,
            "total_endpoints": total_endpoints,
            "healthy_endpoints": healthy_endpoints,
            "unhealthy_endpoints": total_endpoints - healthy_endpoints,
            "active_connections": sum(self._connection_counts.values()),
        }
