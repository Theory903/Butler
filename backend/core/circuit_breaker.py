"""ButlerCircuitBreaker — production-grade dependency circuit breaker.

Three-state model:
  CLOSED     — normal operation; failures are counted
  OPEN       — dependency considered failed; calls rejected immediately
  HALF_OPEN  — controlled probe mode; exactly one probe call allowed through

State transitions:
  CLOSED    -> OPEN       when failure_count >= threshold within window_s
  OPEN      -> HALF_OPEN  after recovery_s seconds have elapsed
  HALF_OPEN -> CLOSED     when the probe succeeds
  HALF_OPEN -> OPEN       when the probe fails

Design rules:
- breaker state is process-local by design
- only infrastructure-class exceptions trip the breaker automatically
- application/business/policy exceptions are never swallowed
- HALF_OPEN allows only one in-flight probe
- safe for concurrent async callers within a single process
"""

from __future__ import annotations

import contextlib
import time
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


InfrastructureExceptionTypes = (
    ConnectionError,
    TimeoutError,
    OSError,
    IOError,
)


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the circuit is OPEN."""

    def __init__(self, name: str, retry_after_s: float) -> None:
        self.name = name
        self.retry_after_s = max(0.0, float(retry_after_s))
        super().__init__(f"Circuit '{name}' is OPEN. Retry after {self.retry_after_s:.1f}s.")


@dataclass(slots=True, frozen=True)
class CircuitStats:
    name: str
    state: CircuitState
    failure_count: int
    success_count: int
    last_failure_at: float | None
    last_success_at: float | None
    opened_at: float | None
    threshold: int
    window_s: float
    recovery_s: float
    half_open_probe_in_flight: bool

    @property
    def recovery_remaining_s(self) -> float:
        if self.state != CircuitState.OPEN or self.opened_at is None:
            return 0.0
        return max(0.0, (self.opened_at + self.recovery_s) - time.monotonic())


class ButlerCircuitBreaker:
    """Async-safe circuit breaker for infrastructure dependencies."""

    def __init__(
        self,
        name: str,
        threshold: int = 5,
        window_s: float = 60.0,
        recovery_s: float = 30.0,
        exception_predicate: Callable[[BaseException], bool] | None = None,
    ) -> None:
        if not name.strip():
            raise ValueError("name must not be empty")
        if threshold <= 0:
            raise ValueError("threshold must be > 0")
        if window_s <= 0:
            raise ValueError("window_s must be > 0")
        if recovery_s <= 0:
            raise ValueError("recovery_s must be > 0")

        self._name = name.strip()
        self._threshold = int(threshold)
        self._window_s = float(window_s)
        self._recovery_s = float(recovery_s)
        self._state = CircuitState.CLOSED

        self._failures: deque[float] = deque()
        self._success_count = 0
        self._last_failure_at: float | None = None
        self._last_success_at: float | None = None
        self._opened_at: float | None = None

        # Single-process async safety.
        self._probe_in_flight = False

        self._exception_predicate = exception_predicate or self._default_should_trip

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> CircuitState:
        self._maybe_transition()
        return self._state

    def allow_request(self) -> bool:
        """Return True if the breaker currently allows one request through.

        In HALF_OPEN, only one probe call is allowed at a time.
        """
        self._maybe_transition()

        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            return False

        # HALF_OPEN
        if self._probe_in_flight:
            return False

        self._probe_in_flight = True
        logger.info("circuit_half_open_probe_granted", name=self._name)
        return True

    def record_success(self) -> None:
        now = time.monotonic()
        self._last_success_at = now
        self._success_count += 1

        if self._state == CircuitState.HALF_OPEN:
            self._close()
            logger.info("circuit_closed", name=self._name, via="successful_probe")

    def record_failure(self) -> None:
        now = time.monotonic()
        self._last_failure_at = now

        if self._state == CircuitState.HALF_OPEN:
            self._open(now)
            logger.warning("circuit_reopened", name=self._name, via="failed_probe")
            return

        self._prune_old_failures(now)
        self._failures.append(now)

        if len(self._failures) >= self._threshold:
            self._open(now)
            logger.warning(
                "circuit_opened",
                name=self._name,
                failures=len(self._failures),
                threshold=self._threshold,
                window_s=self._window_s,
            )

    @contextlib.asynccontextmanager
    async def guard(
        self,
        call: Callable[[], Awaitable[Any]],
    ) -> AsyncIterator[Any]:
        """Execute one guarded dependency call.

        - rejects immediately if OPEN
        - permits at most one HALF_OPEN probe
        - records success/failure automatically
        - never swallows application exceptions
        """
        if not self.allow_request():
            retry_after_s = self._retry_after_seconds()
            raise CircuitOpenError(self._name, retry_after_s)

        try:
            result = await call()
        except BaseException as exc:
            if self._exception_predicate(exc):
                self.record_failure()
            raise
        else:
            self.record_success()
            yield result
        finally:
            if self._state == CircuitState.HALF_OPEN:
                # Probe was granted but state did not transition yet due to odd flow.
                # Keep invariant sane.
                self._probe_in_flight = False
            elif self._state == CircuitState.CLOSED or self._state == CircuitState.OPEN:
                self._probe_in_flight = False

    def stats(self) -> CircuitStats:
        self._maybe_transition()
        self._prune_old_failures(time.monotonic())
        return CircuitStats(
            name=self._name,
            state=self._state,
            failure_count=len(self._failures),
            success_count=self._success_count,
            last_failure_at=self._last_failure_at,
            last_success_at=self._last_success_at,
            opened_at=self._opened_at,
            threshold=self._threshold,
            window_s=self._window_s,
            recovery_s=self._recovery_s,
            half_open_probe_in_flight=self._probe_in_flight,
        )

    def reset(self) -> None:
        self._close()
        self._failures.clear()
        logger.info("circuit_reset", name=self._name)

    def _default_should_trip(self, exc: BaseException) -> bool:
        return isinstance(exc, InfrastructureExceptionTypes)

    def _maybe_transition(self) -> None:
        if self._state != CircuitState.OPEN or self._opened_at is None:
            return

        if (time.monotonic() - self._opened_at) >= self._recovery_s:
            self._state = CircuitState.HALF_OPEN
            self._probe_in_flight = False
            logger.info("circuit_half_open", name=self._name)

    def _open(self, now: float) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = now
        self._probe_in_flight = False

    def _close(self) -> None:
        self._state = CircuitState.CLOSED
        self._failures.clear()
        self._opened_at = None
        self._probe_in_flight = False

    def _prune_old_failures(self, now: float) -> None:
        cutoff = now - self._window_s
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()

    def _retry_after_seconds(self) -> float:
        if self._state != CircuitState.OPEN or self._opened_at is None:
            return 0.0
        return max(0.0, (self._opened_at + self._recovery_s) - time.monotonic())


class CircuitBreakerRegistry:
    """Registry of process-local dependency breakers."""

    def __init__(self) -> None:
        self._breakers: dict[str, ButlerCircuitBreaker] = {}

    def register(
        self,
        name: str,
        threshold: int = 10,
        window_s: float = 60.0,
        recovery_s: float = 30.0,
        exception_predicate: Callable[[BaseException], bool] | None = None,
    ) -> ButlerCircuitBreaker:
        normalized = name.strip().lower()
        if not normalized:
            raise ValueError("breaker name must not be empty")

        breaker = self._breakers.get(normalized)
        if breaker is None:
            breaker = ButlerCircuitBreaker(
                name=normalized,
                threshold=threshold,
                window_s=window_s,
                recovery_s=recovery_s,
                exception_predicate=exception_predicate,
            )
            self._breakers[normalized] = breaker
        return breaker

    def get(self, name: str) -> ButlerCircuitBreaker | None:
        return self._breakers.get(name.strip().lower())

    def require(self, name: str) -> ButlerCircuitBreaker:
        breaker = self.get(name)
        if breaker is None:
            raise KeyError(f"Unknown circuit breaker: {name}")
        return breaker

    def all_stats(self) -> list[dict[str, Any]]:
        return [
            {
                "name": stats.name,
                "state": stats.state.value,
                "failure_count": stats.failure_count,
                "success_count": stats.success_count,
                "last_failure_at": stats.last_failure_at,
                "last_success_at": stats.last_success_at,
                "recovery_remaining_s": stats.recovery_remaining_s,
                "threshold": stats.threshold,
                "window_s": stats.window_s,
                "recovery_s": stats.recovery_s,
                "half_open_probe_in_flight": stats.half_open_probe_in_flight,
            }
            for breaker in self._breakers.values()
            for stats in [breaker.stats()]
        ]

    def any_open(self) -> bool:
        return any(breaker.state == CircuitState.OPEN for breaker in self._breakers.values())

    def reset_all(self) -> int:
        count = 0
        for breaker in self._breakers.values():
            breaker.reset()
            count += 1
        return count


_registry: CircuitBreakerRegistry | None = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    global _registry
    if _registry is None:
        registry = CircuitBreakerRegistry()
        registry.register("redis", threshold=5, window_s=60.0, recovery_s=20.0)
        registry.register("postgres", threshold=5, window_s=60.0, recovery_s=30.0)
        registry.register("qdrant", threshold=3, window_s=60.0, recovery_s=30.0)
        registry.register("neo4j", threshold=3, window_s=60.0, recovery_s=30.0)
        registry.register("vllm", threshold=3, window_s=120.0, recovery_s=60.0)
        registry.register("anthropic", threshold=5, window_s=60.0, recovery_s=15.0)
        registry.register("openai", threshold=5, window_s=60.0, recovery_s=15.0)
        _registry = registry
    return _registry
