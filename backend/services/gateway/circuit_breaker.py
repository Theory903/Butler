"""
Circuit Breaker - Circuit Breaker Patterns for Service Resilience

Implements circuit breaker patterns for service resilience.
Supports state management, failure tracking, and automatic recovery.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class CircuitState(StrEnum):
    """Circuit breaker state."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True, slots=True)
class CircuitBreakerConfig:
    """Circuit breaker configuration."""

    failure_threshold: int
    success_threshold: int
    timeout_seconds: int
    half_open_max_calls: int


@dataclass(frozen=True, slots=True)
class CircuitBreakerState:
    """Circuit breaker state."""

    service_name: str
    state: CircuitState
    failures: int
    successes: int
    last_failure_time: datetime | None
    last_state_change: datetime


class CircuitBreaker:
    """
    Circuit breaker for service resilience.

    Features:
    - Automatic circuit breaking
    - Failure tracking
    - Automatic recovery
    - Half-open state testing
    """

    def __init__(
        self,
        service_name: str,
        config: CircuitBreakerConfig,
    ) -> None:
        """Initialize circuit breaker."""
        self._service_name = service_name
        self._config = config
        self._state = CircuitBreakerState(
            service_name=service_name,
            state=CircuitState.CLOSED,
            failures=0,
            successes=0,
            last_failure_time=None,
            last_state_change=datetime.now(UTC),
        )

    async def execute(
        self,
        operation: Callable[[], Awaitable[Any]],
        fallback: Callable[[], Awaitable[Any]] | None = None,
    ) -> Any:
        """
        Execute operation with circuit breaker protection.

        Args:
            operation: Async operation to execute
            fallback: Fallback operation if circuit is open

        Returns:
            Operation result or fallback result
        """
        if not await self.allow_request():
            logger.warning(
                "circuit_open",
                service_name=self._service_name,
            )

            if fallback:
                return await fallback()

            raise Exception(f"Circuit breaker open for service: {self._service_name}")

        try:
            result = await operation()
            await self.record_success()
            return result

        except Exception as e:
            await self.record_failure()

            logger.error(
                "operation_failed",
                service_name=self._service_name,
                error=str(e),
            )

            if fallback:
                return await fallback()

            raise

    async def allow_request(self) -> bool:
        """
        Check if request is allowed through circuit.

        Returns:
            True if request allowed
        """
        state = self._state

        if state.state == CircuitState.CLOSED:
            return True

        if state.state == CircuitState.OPEN:
            # Check if timeout has passed
            if state.last_failure_time:
                elapsed = datetime.now(UTC) - state.last_failure_time
                if elapsed.total_seconds() >= self._config.timeout_seconds:
                    await self._transition_to_half_open()
                    return True
            return False

        if state.state == CircuitState.HALF_OPEN:
            return state.successes < self._config.half_open_max_calls

        return False

    async def record_success(self) -> None:
        """Record successful operation."""
        state = self._state

        if state.state == CircuitState.HALF_OPEN:
            self._state = CircuitBreakerState(
                service_name=self._service_name,
                state=CircuitState.CLOSED,
                failures=0,
                successes=state.successes + 1,
                last_failure_time=None,
                last_state_change=datetime.now(UTC),
            )

            logger.info(
                "circuit_closed",
                service_name=self._service_name,
            )
        else:
            self._state = CircuitBreakerState(
                service_name=self._service_name,
                state=state.state,
                failures=0,
                successes=state.successes + 1,
                last_failure_time=state.last_failure_time,
                last_state_change=state.last_state_change,
            )

    async def record_failure(self) -> None:
        """Record failed operation."""
        state = self._state

        if state.state == CircuitState.CLOSED:
            new_failures = state.failures + 1

            if new_failures >= self._config.failure_threshold:
                await self._transition_to_open()
            else:
                self._state = CircuitBreakerState(
                    service_name=self._service_name,
                    state=CircuitState.CLOSED,
                    failures=new_failures,
                    successes=0,
                    last_failure_time=datetime.now(UTC),
                    last_state_change=datetime.now(UTC),
                )

        elif state.state == CircuitState.HALF_OPEN:
            await self._transition_to_open()

    async def _transition_to_open(self) -> None:
        """Transition circuit to open state."""
        self._state = CircuitBreakerState(
            service_name=self._service_name,
            state=CircuitState.OPEN,
            failures=self._state.failures,
            successes=0,
            last_failure_time=datetime.now(UTC),
            last_state_change=datetime.now(UTC),
        )

        logger.warning(
            "circuit_opened",
            service_name=self._service_name,
            failures=self._state.failures,
        )

    async def _transition_to_half_open(self) -> None:
        """Transition circuit to half-open state."""
        self._state = CircuitBreakerState(
            service_name=self._service_name,
            state=CircuitState.HALF_OPEN,
            failures=0,
            successes=0,
            last_failure_time=None,
            last_state_change=datetime.now(UTC),
        )

        logger.info(
            "circuit_half_open",
            service_name=self._service_name,
        )

    def get_state(self) -> CircuitBreakerState:
        """Get current circuit breaker state."""
        return self._state

    def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        self._state = CircuitBreakerState(
            service_name=self._service_name,
            state=CircuitState.CLOSED,
            failures=0,
            successes=0,
            last_failure_time=None,
            last_state_change=datetime.now(UTC),
        )

        logger.info(
            "circuit_reset",
            service_name=self._service_name,
        )


class CircuitBreakerRegistry:
    """
    Registry for multiple circuit breakers.

    Features:
    - Circuit breaker management
    - Service registration
    - Bulk operations
    """

    def __init__(self) -> None:
        """Initialize circuit breaker registry."""
        self._breakers: dict[str, CircuitBreaker] = {}

    def register_breaker(
        self,
        service_name: str,
        config: CircuitBreakerConfig,
    ) -> CircuitBreaker:
        """
        Register a circuit breaker for a service.

        Args:
            service_name: Service name
            config: Circuit breaker configuration

        Returns:
            Circuit breaker
        """
        breaker = CircuitBreaker(service_name, config)
        self._breakers[service_name] = breaker

        logger.info(
            "circuit_breaker_registered",
            service_name=service_name,
        )

        return breaker

    def get_breaker(self, service_name: str) -> CircuitBreaker | None:
        """
        Get circuit breaker for a service.

        Args:
            service_name: Service name

        Returns:
            Circuit breaker or None
        """
        return self._breakers.get(service_name)

    def remove_breaker(self, service_name: str) -> bool:
        """
        Remove circuit breaker for a service.

        Args:
            service_name: Service name

        Returns:
            True if removed
        """
        if service_name in self._breakers:
            del self._breakers[service_name]

            logger.info(
                "circuit_breaker_removed",
                service_name=service_name,
            )

            return True
        return False

    def get_all_states(self) -> dict[str, CircuitBreakerState]:
        """Get states of all circuit breakers."""
        return {name: breaker.get_state() for name, breaker in self._breakers.items()}

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()

        logger.info("all_circuit_breakers_reset")

    def get_registry_stats(self) -> dict[str, Any]:
        """
        Get registry statistics.

        Returns:
            Registry statistics
        """
        total_breakers = len(self._breakers)

        state_counts: dict[str, int] = {}
        for breaker in self._breakers.values():
            state = breaker.get_state().state
            state_counts[state] = state_counts.get(state, 0) + 1

        return {
            "total_breakers": total_breakers,
            "state_breakdown": state_counts,
        }
