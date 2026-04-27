"""ML Runtime health-gated routing and fallback chains."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HealthStatus(str, Enum):
    """Health status for ML runtime components."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    """Health status for a model provider."""

    provider_name: str
    status: HealthStatus
    latency_ms: float | None
    error_rate: float
    last_check_timestamp: float

    def is_available(self) -> bool:
        """Check if provider is available for routing."""
        return self.status in {HealthStatus.HEALTHY, HealthStatus.DEGRADED}

    def is_preferred(self) -> bool:
        """Check if provider is preferred (healthy, low latency)."""
        return (
            self.status == HealthStatus.HEALTHY
            and self.latency_ms is not None
            and self.latency_ms < 1000
        )


@dataclass(frozen=True, slots=True)
class FallbackChain:
    """Fallback chain for model routing.

    Rule: Never route to unhealthy providers without fallback.
    """

    primary_provider: str
    fallback_providers: tuple[str, ...]
    max_retries: int = 3

    def get_routing_order(self, health_checks: dict[str, ProviderHealth]) -> list[str]:
        """Get ordered list of providers based on health."""
        providers = [self.primary_provider] + list(self.fallback_providers)
        available = [p for p in providers if p in health_checks and health_checks[p].is_available()]
        return available[: self.max_retries + 1]

    def has_fallback(self) -> bool:
        """Check if fallback providers exist."""
        return len(self.fallback_providers) > 0


@dataclass(frozen=True, slots=True)
class RoutingPolicy:
    """Routing policy for ML runtime."""

    enable_health_gating: bool
    enable_fallback: bool
    require_healthy_primary: bool = True

    @classmethod
    def default(cls) -> RoutingPolicy:
        """Default routing policy with health gating enabled."""
        return cls(
            enable_health_gating=True,
            enable_fallback=True,
            require_healthy_primary=True,
        )

    @classmethod
    def permissive(cls) -> RoutingPolicy:
        """Permissive routing policy (no health gating)."""
        return cls(
            enable_health_gating=False,
            enable_fallback=False,
            require_healthy_primary=False,
        )
