"""
Request Router - Load Balancing and Request Routing

Routes requests to appropriate backend services.
Implements load balancing strategies and service discovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class RoutingStrategy(StrEnum):
    """Load balancing strategies."""

    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    RANDOM = "random"
    IP_HASH = "ip_hash"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"


@dataclass(frozen=True, slots=True)
class Backend:
    """Backend service instance."""

    id: str
    host: str
    port: int
    weight: int
    healthy: bool
    active_connections: int
    last_health_check: datetime


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """Routing decision for a request."""

    backend: Backend
    strategy: RoutingStrategy
    timestamp: datetime


class RequestRouter:
    """
    Request router for load balancing.

    Features:
    - Multiple load balancing strategies
    - Health-aware routing
    - Connection tracking
    - Circuit breaker integration
    """

    def __init__(
        self,
        strategy: RoutingStrategy = RoutingStrategy.ROUND_ROBIN,
    ) -> None:
        """Initialize request router."""
        self._strategy = strategy
        self._backends: dict[str, Backend] = {}
        self._round_robin_index = 0
        self._random_seed = 0

    def register_backend(
        self,
        backend_id: str,
        host: str,
        port: int,
        weight: int = 1,
    ) -> None:
        """
        Register a backend service.

        Args:
            backend_id: Backend identifier
            host: Backend host
            port: Backend port
            weight: Backend weight for weighted strategies
        """
        backend = Backend(
            id=backend_id,
            host=host,
            port=port,
            weight=weight,
            healthy=True,
            active_connections=0,
            last_health_check=datetime.now(UTC),
        )

        self._backends[backend_id] = backend

        logger.info(
            "backend_registered",
            backend_id=backend_id,
            host=host,
            port=port,
            weight=weight,
        )

    def unregister_backend(self, backend_id: str) -> None:
        """
        Unregister a backend service.

        Args:
            backend_id: Backend identifier
        """
        if backend_id in self._backends:
            del self._backends[backend_id]

            logger.info(
                "backend_unregistered",
                backend_id=backend_id,
            )

    def update_backend_health(
        self,
        backend_id: str,
        healthy: bool,
    ) -> None:
        """
        Update backend health status.

        Args:
            backend_id: Backend identifier
            healthy: Health status
        """
        if backend_id in self._backends:
            backend = self._backends[backend_id]
            self._backends[backend_id] = Backend(
                id=backend.id,
                host=backend.host,
                port=backend.port,
                weight=backend.weight,
                healthy=healthy,
                active_connections=backend.active_connections,
                last_health_check=datetime.now(UTC),
            )

            logger.debug(
                "backend_health_updated",
                backend_id=backend_id,
                healthy=healthy,
            )

    def increment_connections(self, backend_id: str) -> None:
        """Increment active connections for backend."""
        if backend_id in self._backends:
            backend = self._backends[backend_id]
            self._backends[backend_id] = Backend(
                id=backend.id,
                host=backend.host,
                port=backend.port,
                weight=backend.weight,
                healthy=backend.healthy,
                active_connections=backend.active_connections + 1,
                last_health_check=backend.last_health_check,
            )

    def decrement_connections(self, backend_id: str) -> None:
        """Decrement active connections for backend."""
        if backend_id in self._backends:
            backend = self._backends[backend_id]
            self._backends[backend_id] = Backend(
                id=backend.id,
                host=backend.host,
                port=backend.port,
                weight=backend.weight,
                healthy=backend.healthy,
                active_connections=max(0, backend.active_connections - 1),
                last_health_check=backend.last_health_check,
            )

    def get_healthy_backends(self) -> list[Backend]:
        """Get all healthy backends."""
        return [b for b in self._backends.values() if b.healthy]

    def route_request(
        self,
        client_ip: str | None = None,
    ) -> RoutingDecision | None:
        """
        Route a request to a backend.

        Args:
            client_ip: Client IP address for hash-based routing

        Returns:
            Routing decision or None if no healthy backends
        """
        healthy_backends = self.get_healthy_backends()

        if not healthy_backends:
            logger.warning("no_healthy_backends_available")
            return None

        backend = self._select_backend(healthy_backends, client_ip)

        if not backend:
            return None

        decision = RoutingDecision(
            backend=backend,
            strategy=self._strategy,
            timestamp=datetime.now(UTC),
        )

        logger.debug(
            "request_routed",
            backend_id=backend.id,
            strategy=self._strategy,
        )

        return decision

    def _select_backend(
        self,
        backends: list[Backend],
        client_ip: str | None,
    ) -> Backend | None:
        """Select backend based on routing strategy."""
        if not backends:
            return None

        if self._strategy == RoutingStrategy.ROUND_ROBIN:
            return self._round_robin_select(backends)
        if self._strategy == RoutingStrategy.LEAST_CONNECTIONS:
            return self._least_connections_select(backends)
        if self._strategy == RoutingStrategy.RANDOM:
            return self._random_select(backends)
        if self._strategy == RoutingStrategy.IP_HASH:
            return self._ip_hash_select(backends, client_ip)
        if self._strategy == RoutingStrategy.WEIGHTED_ROUND_ROBIN:
            return self._weighted_round_robin_select(backends)
        return backends[0]

    def _round_robin_select(self, backends: list[Backend]) -> Backend:
        """Select backend using round-robin strategy."""
        backend = backends[self._round_robin_index % len(backends)]
        self._round_robin_index += 1
        return backend

    def _least_connections_select(self, backends: list[Backend]) -> Backend:
        """Select backend with least active connections."""
        return min(backends, key=lambda b: b.active_connections)

    def _random_select(self, backends: list[Backend]) -> Backend:
        """Select backend randomly."""
        import random

        return random.choice(backends)

    def _ip_hash_select(
        self,
        backends: list[Backend],
        client_ip: str | None,
    ) -> Backend:
        """Select backend using IP hash."""
        if not client_ip:
            return self._random_select(backends)

        hash_val = hash(client_ip) % len(backends)
        return backends[hash_val]

    def _weighted_round_robin_select(self, backends: list[Backend]) -> Backend:
        """Select backend using weighted round-robin."""
        total_weight = sum(b.weight for b in backends)
        if total_weight == 0:
            return backends[0]

        import random

        target = random.uniform(0, total_weight)

        current_weight = 0
        for backend in backends:
            current_weight += backend.weight
            if current_weight >= target:
                return backend

        return backends[-1]

    def get_backend_stats(self) -> dict[str, Any]:
        """
        Get statistics for all backends.

        Returns:
            Backend statistics
        """
        stats = {
            "total_backends": len(self._backends),
            "healthy_backends": len(self.get_healthy_backends()),
            "strategy": self._strategy,
            "backends": [],
        }

        for backend in self._backends.values():
            stats["backends"].append(
                {
                    "id": backend.id,
                    "host": backend.host,
                    "port": backend.port,
                    "weight": backend.weight,
                    "healthy": backend.healthy,
                    "active_connections": backend.active_connections,
                    "last_health_check": backend.last_health_check.isoformat(),
                }
            )

        return stats
