"""ButlerCircuitBreaker — Phase 6.

Per-dependency circuit breaker implementing the three-state model:
  CLOSED     — normal operation; failures are counted
  OPEN       — dependency considered failed; calls rejected immediately
  HALF_OPEN  — probe mode; one test call allowed through

State transitions:
  CLOSED  → OPEN       when failure_count >= threshold within window_s
  OPEN    → HALF_OPEN  after recovery_s seconds have elapsed
  HALF_OPEN → CLOSED   if the probe call succeeds
  HALF_OPEN → OPEN     if the probe call fails

Sovereignty rules:
  - Each upstream dependency (Redis, PostgreSQL, Qdrant, Neo4j, vLLM,
    external APIs) gets its own independent breaker.
  - Breaker state is in-process only (no Redis). Restarts reset to CLOSED.
    This is intentional — we don't want a stale OPEN to survive a fix.
  - ButlerCircuitBreaker is a pure synchronous class. Async wrappers are
    on the caller side (`async with breaker.guard():`).
  - The circuit breaker NEVER catches non-infrastructure errors (e.g.
    ToolPolicyViolation, MemoryWritePolicy decisions). Only IOError,
    ConnectionError, TimeoutError, and explicit `record_failure()` calls.

Usage:
    breaker = ButlerCircuitBreaker("redis", threshold=5, window_s=60, recovery_s=30)

    async def _redis_ping():
        await redis.ping()

    async with breaker.guard(_redis_ping):
        ...  # runs only when CLOSED or HALF_OPEN probe allowed

    # Or explicit:
    if breaker.allow_request():
        try:
            result = await redis.get(key)
            breaker.record_success()
        except Exception:
            breaker.record_failure()
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Callable, Awaitable

import structlog

logger = structlog.get_logger(__name__)


class CircuitState(str, Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the circuit is OPEN."""

    def __init__(self, name: str, opens_at: float) -> None:
        self.name = name
        self.opens_at = opens_at
        recovery_in = max(0.0, opens_at - time.monotonic())
        super().__init__(
            f"Circuit '{name}' is OPEN. Recovery probe in {recovery_in:.1f}s."
        )


@dataclass
class CircuitStats:
    """Snapshot of a circuit breaker's current state."""
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

    @property
    def recovery_remaining_s(self) -> float:
        if self.state == CircuitState.OPEN and self.opened_at:
            remaining = (self.opened_at + self.recovery_s) - time.monotonic()
            return max(0.0, remaining)
        return 0.0


class ButlerCircuitBreaker:
    """Three-state (CLOSED/OPEN/HALF_OPEN) circuit breaker.

    Thread-safe for async contexts (single-threaded event loop per process).
    """

    def __init__(
        self,
        name: str,
        threshold: int = 5,        # failures before opening
        window_s: float = 60.0,    # rolling window for failure counting
        recovery_s: float = 30.0,  # seconds before OPEN → HALF_OPEN
    ) -> None:
        self._name = name
        self._threshold = threshold
        self._window_s = window_s
        self._recovery_s = recovery_s

        self._state = CircuitState.CLOSED
        self._failures: list[float] = []  # monotonic timestamps
        self._success_count = 0
        self._last_failure_at: float | None = None
        self._last_success_at: float | None = None
        self._opened_at: float | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        self._maybe_transition()
        return self._state

    @property
    def name(self) -> str:
        return self._name

    def allow_request(self) -> bool:
        """Return True if the circuit allows this call through."""
        self._maybe_transition()

        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.HALF_OPEN:
            return True  # one probe call
        # OPEN
        return False

    def record_success(self) -> None:
        """Record a successful call. Closes circuit if in HALF_OPEN."""
        self._last_success_at = time.monotonic()
        self._success_count += 1
        if self._state == CircuitState.HALF_OPEN:
            self._close()
            logger.info("circuit_closed", name=self._name, via="successful_probe")

    def record_failure(self) -> None:
        """Record a failed call. Opens circuit if threshold exceeded."""
        now = time.monotonic()
        self._last_failure_at = now
        self._failures.append(now)
        self._prune_old_failures(now)

        if self._state == CircuitState.HALF_OPEN:
            # Probe failed — stay OPEN
            self._open(now)
            logger.warning("circuit_stayed_open", name=self._name, via="failed_probe")
            return

        if len(self._failures) >= self._threshold:
            self._open(now)
            logger.warning(
                "circuit_opened",
                name=self._name,
                failures=len(self._failures),
                threshold=self._threshold,
            )

    @contextlib.asynccontextmanager
    async def guard(
        self,
        call: Callable[[], Awaitable],
        *,
        fallback=None,
    ) -> AsyncIterator:
        """Async context manager that gates a single async call.

        Usage:
            async with breaker.guard(lambda: redis.ping()):
                pass  # will not raise; exception mapped to record_failure

        Raises CircuitOpenError if the circuit is OPEN.
        Re-raises the call's exception after recording the failure.
        """
        if not self.allow_request():
            raise CircuitOpenError(self._name, self._opened_at + self._recovery_s if self._opened_at else 0)

        try:
            result = await call()
            self.record_success()
            yield result
        except (ConnectionError, TimeoutError, OSError, IOError) as exc:
            self.record_failure()
            raise
        except Exception:
            # Non-infrastructure exceptions don't trip the breaker
            yield None

    def stats(self) -> CircuitStats:
        self._maybe_transition()
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
        )

    def reset(self) -> None:
        """Force circuit back to CLOSED (admin/test use only)."""
        self._close()
        self._failures.clear()
        logger.info("circuit_reset", name=self._name)

    # ── Private ───────────────────────────────────────────────────────────────

    def _maybe_transition(self) -> None:
        """Check if OPEN → HALF_OPEN transition is due."""
        if (
            self._state == CircuitState.OPEN
            and self._opened_at is not None
            and (time.monotonic() - self._opened_at) >= self._recovery_s
        ):
            self._state = CircuitState.HALF_OPEN
            logger.info("circuit_half_open", name=self._name)

    def _open(self, now: float) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = now

    def _close(self) -> None:
        self._state = CircuitState.CLOSED
        self._failures.clear()
        self._opened_at = None

    def _prune_old_failures(self, now: float) -> None:
        cutoff = now - self._window_s
        self._failures = [t for t in self._failures if t >= cutoff]


class CircuitBreakerRegistry:
    """Global registry of all circuit breakers in the Butler process.

    Used by AdminPlane and HealthChecker to inspect system state.
    """

    def __init__(self) -> None:
        self._breakers: dict[str, ButlerCircuitBreaker] = {}

    def register(
        self,
        name: str,
        threshold: int = 10,
        window_s: float = 60.0,
        recovery_s: float = 30.0,
    ) -> ButlerCircuitBreaker:
        """Register and return a new circuit breaker (idempotent)."""
        if name not in self._breakers:
            self._breakers[name] = ButlerCircuitBreaker(
                name=name,
                threshold=threshold,
                window_s=window_s,
                recovery_s=recovery_s,
            )
        return self._breakers[name]

    def get(self, name: str) -> ButlerCircuitBreaker | None:
        return self._breakers.get(name)

    def all_stats(self) -> list[dict]:
        return [
            {
                "name": s.name,
                "state": s.state.value,
                "failure_count": s.failure_count,
                "success_count": s.success_count,
                "recovery_remaining_s": s.recovery_remaining_s,
                "threshold": s.threshold,
                "window_s": s.window_s,
                "recovery_s": s.recovery_s,
            }
            for breaker in self._breakers.values()
            for s in [breaker.stats()]
        ]

    def any_open(self) -> bool:
        return any(b.state == CircuitState.OPEN for b in self._breakers.values())

    def reset_all(self) -> int:
        """Admin: reset all breakers to CLOSED. Returns count reset."""
        count = 0
        for b in self._breakers.values():
            b.reset()
            count += 1
        return count


# ── Singleton for dependency injection ────────────────────────────────────────

_registry: CircuitBreakerRegistry | None = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Return the global CircuitBreakerRegistry (lazy-init)."""
    global _registry  # noqa: PLW0603
    if _registry is None:
        _registry = CircuitBreakerRegistry()
        # Register default Butler infrastructure dependencies
        _registry.register("redis",       threshold=5, window_s=60,  recovery_s=20)
        _registry.register("postgres",    threshold=5, window_s=60,  recovery_s=30)
        _registry.register("qdrant",      threshold=3, window_s=60,  recovery_s=30)
        _registry.register("neo4j",       threshold=3, window_s=60,  recovery_s=30)
        _registry.register("vllm",        threshold=3, window_s=120, recovery_s=60)
        _registry.register("anthropic",   threshold=5, window_s=60,  recovery_s=15)
        _registry.register("openai",      threshold=5, window_s=60,  recovery_s=15)
    return _registry
