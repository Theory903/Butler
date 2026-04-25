from __future__ import annotations

import asyncio
import enum
import inspect
import logging
import time
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypeVar

import structlog
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from domain.policy.capability_flags import TrustLevel

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

T = TypeVar("T")


# ============================================================================
# Exception Classes
# ============================================================================


class BudgetExceededError(Exception):
    """Raised when sub-agent exceeds allocated resource budget."""


class TrustBoundaryViolationError(Exception):
    """Raised when sub-agent attempts to cross trust boundaries."""


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and blocking execution."""

    def __init__(self, name: str, retry_after_seconds: float | None = None) -> None:
        self.name = name
        self.retry_after_seconds = retry_after_seconds
        detail = (
            f"Circuit breaker '{name}' is open."
            if retry_after_seconds is None
            else f"Circuit breaker '{name}' is open. Retry after {retry_after_seconds:.2f}s."
        )
        super().__init__(detail)


class TransientExecutionError(Exception):
    """Raised when execution fails transiently and can be retried."""


# ============================================================================
# Core Enums and Models
# ============================================================================


class RuntimeClass(enum.StrEnum):
    """Sub-agent execution runtime isolation levels."""

    IN_PROCESS = "in_process"
    PROCESS_POOL = "process_pool"
    SANDBOX = "sandbox"
    REMOTE_PEER = "remote_peer"
    HUMAN_GATE = "human_gate"

    @property
    def isolation_level(self) -> int:
        return {
            RuntimeClass.IN_PROCESS: 0,
            RuntimeClass.PROCESS_POOL: 1,
            RuntimeClass.SANDBOX: 2,
            RuntimeClass.REMOTE_PEER: 3,
            RuntimeClass.HUMAN_GATE: 4,
        }[self]


class SubAgentProfile(BaseModel):
    """
    Sub-agent identity and execution profile.

    Defines trust boundaries, tool permissions, memory scope,
    and resource quotas for a sub-agent instance.
    """

    model_config = ConfigDict(frozen=True, use_enum_values=False)

    agent_id: str = Field(default_factory=lambda: f"sub:{uuid.uuid4().hex[:12]}")
    parent_agent_id: str
    session_id: str
    runtime_class: RuntimeClass
    trust_level: TrustLevel = Field(default=TrustLevel.UNTRUSTED)

    tool_permissions: set[str] = Field(default_factory=set)
    memory_scope: str

    max_execution_time_ms: int = Field(default=30_000, gt=0)
    max_memory_mb: int = Field(default=128, gt=0)
    max_tool_calls: int = Field(default=50, gt=0)
    max_tokens: int = Field(default=100_000, gt=0)

    allow_network_access: bool = False
    allow_file_system_access: bool = False
    allow_state_modification: bool = False
    inherit_parent_trace: bool = True

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None

    @field_validator("agent_id", "parent_agent_id", "session_id", "memory_scope")
    @classmethod
    def _validate_non_empty_string(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("field must not be empty")
        return cleaned

    @field_validator("tool_permissions")
    @classmethod
    def _normalize_permissions(cls, value: set[str]) -> set[str]:
        return {item.strip() for item in value if item and item.strip()}

    @model_validator(mode="after")
    def _validate_profile(self) -> SubAgentProfile:
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")

        trust_value = _trust_level_value(self.trust_level)

        if self.runtime_class == RuntimeClass.IN_PROCESS and trust_value < _trust_level_value(
            TrustLevel.VERIFIED_USER
        ):
            raise ValueError("in-process execution requires trust level >= VERIFIED_USER")

        if self.allow_state_modification and trust_value < 50:
            raise ValueError("state modification requires trust level >= 50")

        return self

    def is_expired(self, *, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        now = now or datetime.now(UTC)
        return now >= self.expires_at


class BudgetUsage(BaseModel):
    """Tracks resource consumption for a sub-agent execution."""

    execution_time_ms: int = 0
    memory_used_mb: int = 0
    tool_calls: int = 0
    tokens_used: int = 0
    network_requests: int = 0
    file_operations: int = 0


class BudgetEnforcer:
    """
    Enforces resource quotas and budget limits for sub-agent execution.
    """

    def __init__(self, profile: SubAgentProfile):
        self.profile = profile
        self.usage = BudgetUsage()
        self.start_time_monotonic: float | None = None
        self._terminated = False

    def start(self) -> None:
        self.start_time_monotonic = time.perf_counter()
        self._terminated = False

    def check(self) -> None:
        if self._terminated:
            raise BudgetExceededError("execution terminated")

        if self.start_time_monotonic is None:
            raise RuntimeError("budget tracking not started")

        elapsed_ms = int((time.perf_counter() - self.start_time_monotonic) * 1000)
        self.usage.execution_time_ms = elapsed_ms

        if elapsed_ms > self.profile.max_execution_time_ms:
            self._terminated = True
            raise BudgetExceededError(
                f"execution time exceeded: {elapsed_ms}ms > {self.profile.max_execution_time_ms}ms"
            )

        if self.usage.tool_calls > self.profile.max_tool_calls:
            self._terminated = True
            raise BudgetExceededError(
                f"tool calls exceeded: {self.usage.tool_calls} > {self.profile.max_tool_calls}"
            )

        if self.usage.tokens_used > self.profile.max_tokens:
            self._terminated = True
            raise BudgetExceededError(
                f"tokens exceeded: {self.usage.tokens_used} > {self.profile.max_tokens}"
            )

        if self.usage.memory_used_mb > self.profile.max_memory_mb:
            self._terminated = True
            raise BudgetExceededError(
                f"memory exceeded: {self.usage.memory_used_mb}MB > {self.profile.max_memory_mb}MB"
            )

    def record_tool_call(self, count: int = 1) -> None:
        self.usage.tool_calls += count
        self.check()

    def record_tokens(self, count: int) -> None:
        if count < 0:
            raise ValueError("token count must be non-negative")
        self.usage.tokens_used += count
        self.check()

    def record_memory_mb(self, used_mb: int) -> None:
        if used_mb < 0:
            raise ValueError("memory usage must be non-negative")
        self.usage.memory_used_mb = used_mb
        self.check()

    def record_network_request(self, count: int = 1) -> None:
        self.usage.network_requests += count
        self.check()

    def record_file_operation(self, count: int = 1) -> None:
        self.usage.file_operations += count
        self.check()

    def terminate(self) -> None:
        self._terminated = True

    @property
    def is_terminated(self) -> bool:
        return self._terminated


# ============================================================================
# Circuit Breaker
# ============================================================================


@dataclass
class _CircuitState:
    state: str = "CLOSED"
    failure_count: int = 0
    last_failure_monotonic: float | None = None
    half_open_probe_in_flight: bool = False


class CircuitBreaker:
    """
    Circuit breaker for sub-agent execution isolation.

    Concurrency-safe for asyncio usage inside one process.
    """

    def __init__(self, name: str, failure_threshold: int = 5, reset_timeout_ms: int = 30_000):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout_ms = reset_timeout_ms
        self._state = _CircuitState()
        self._lock = asyncio.Lock()

    async def allow_execution(self) -> bool:
        async with self._lock:
            now = time.perf_counter()

            if self._state.state == "CLOSED":
                return True

            if self._state.state == "OPEN":
                if self._state.last_failure_monotonic is None:
                    return False

                elapsed_ms = (now - self._state.last_failure_monotonic) * 1000
                if elapsed_ms >= self.reset_timeout_ms:
                    self._state.state = "HALF_OPEN"
                    self._state.half_open_probe_in_flight = True
                    logger.info("circuit_breaker_half_open", name=self.name)
                    return True
                return False

            if self._state.state == "HALF_OPEN":
                if self._state.half_open_probe_in_flight:
                    return False
                self._state.half_open_probe_in_flight = True
                return True

            return False

    async def record_success(self) -> None:
        async with self._lock:
            self._state.state = "CLOSED"
            self._state.failure_count = 0
            self._state.last_failure_monotonic = None
            self._state.half_open_probe_in_flight = False
            logger.debug("circuit_breaker_closed", name=self.name)

    async def record_failure(self) -> None:
        async with self._lock:
            now = time.perf_counter()

            if self._state.state == "HALF_OPEN":
                self._state.state = "OPEN"
                self._state.failure_count = self.failure_threshold
                self._state.last_failure_monotonic = now
                self._state.half_open_probe_in_flight = False
                logger.warning("circuit_breaker_reopened", name=self.name)
                return

            self._state.failure_count += 1
            self._state.last_failure_monotonic = now
            self._state.half_open_probe_in_flight = False

            if self._state.failure_count >= self.failure_threshold:
                self._state.state = "OPEN"
                logger.warning(
                    "circuit_breaker_opened",
                    name=self.name,
                    failure_count=self._state.failure_count,
                )

    async def recovery_remaining_seconds(self) -> float | None:
        async with self._lock:
            if self._state.state != "OPEN" or self._state.last_failure_monotonic is None:
                return None
            elapsed = time.perf_counter() - self._state.last_failure_monotonic
            return max(0.0, (self.reset_timeout_ms / 1000.0) - elapsed)

    async def current_state(self) -> str:
        async with self._lock:
            return self._state.state


# ============================================================================
# Factory
# ============================================================================


class SubAgentFactory:
    """
    Factory for creating profiled sub-agent instances with inheritance.
    """

    @staticmethod
    def create_child(
        parent_profile: SubAgentProfile,
        runtime_class: RuntimeClass | None = None,
        additional_permissions: set[str] | None = None,
        budget_overrides: dict[str, int] | None = None,
    ) -> SubAgentProfile:
        runtime = runtime_class or parent_profile.runtime_class

        if runtime.isolation_level > parent_profile.runtime_class.isolation_level:
            raise TrustBoundaryViolationError(
                f"child agent cannot use higher isolation runtime {runtime.value} than parent {parent_profile.runtime_class.value}"
            )

        permissions = set(parent_profile.tool_permissions)
        if additional_permissions is not None:
            invalid = set(additional_permissions) - parent_profile.tool_permissions
            if invalid:
                raise TrustBoundaryViolationError(
                    f"cannot grant permissions not held by parent: {sorted(invalid)}"
                )
            permissions = set(additional_permissions)

        overrides = budget_overrides or {}
        allowed_override_keys = {
            "max_execution_time_ms",
            "max_memory_mb",
            "max_tool_calls",
            "max_tokens",
        }

        for key, value in overrides.items():
            if key not in allowed_override_keys:
                raise ValueError(f"unsupported budget override: {key}")
            parent_value = getattr(parent_profile, key)
            if value > parent_value:
                raise TrustBoundaryViolationError(
                    f"budget override {key}={value} exceeds parent limit {parent_value}"
                )

        profile_data = parent_profile.model_dump(
            exclude={"agent_id", "created_at", "expires_at"},
            mode="python",
        )
        profile_data.update(
            {
                "runtime_class": runtime,
                "tool_permissions": permissions,
                **overrides,
            }
        )
        return SubAgentProfile(**profile_data)


# ============================================================================
# Executor
# ============================================================================


class SubAgentExecutor[T]:
    """
    Executes sub-agent tasks with budget enforcement, timeout control,
    retry for transient failures, and circuit-breaker isolation.
    """

    def __init__(self, profile: SubAgentProfile):
        self.profile = profile
        self.budget = BudgetEnforcer(profile)
        self.circuit_breaker = CircuitBreaker(name=profile.agent_id)
        self.idempotency_key: str | None = None

    @contextmanager
    def execution_context(self, span_name: str = "subagent.execute"):
        with tracer.start_as_current_span(span_name) as span:
            span.set_attribute("subagent.id", self.profile.agent_id)
            span.set_attribute("subagent.parent_id", self.profile.parent_agent_id)
            span.set_attribute("subagent.runtime", self.profile.runtime_class.value)
            span.set_attribute("subagent.trust_level", str(self.profile.trust_level))
            span.set_attribute("subagent.session_id", self.profile.session_id)

            self.budget.start()

            try:
                yield span
                span.set_status(Status(StatusCode.OK))
            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.record_exception(exc)
                raise
            finally:
                span.set_attribute("budget.execution_time_ms", self.budget.usage.execution_time_ms)
                span.set_attribute("budget.tool_calls", self.budget.usage.tool_calls)
                span.set_attribute("budget.tokens_used", self.budget.usage.tokens_used)
                span.set_attribute("budget.memory_used_mb", self.budget.usage.memory_used_mb)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.1, min=0.1, max=1.0),
        retry=retry_if_exception_type(TransientExecutionError),
        reraise=True,
    )
    async def execute(
        self,
        task: Callable[..., Any],
        *args: Any,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """
        Execute a sub-agent task.

        Retry applies only to TransientExecutionError.
        """
        await self._check_security_policy()

        if self.profile.is_expired():
            raise TrustBoundaryViolationError("sub-agent profile has expired")

        if not await self.circuit_breaker.allow_execution():
            retry_after = await self.circuit_breaker.recovery_remaining_seconds()
            raise CircuitBreakerOpenError(self.profile.agent_id, retry_after)

        self.idempotency_key = idempotency_key or str(uuid.uuid4())

        with self.execution_context():
            try:
                result = await self._run_with_timeout(task, *args, **kwargs)
                self.budget.check()
                await self.circuit_breaker.record_success()
                return result
            except TransientExecutionError:
                await self.circuit_breaker.record_failure()
                raise
            except (ConnectionError, TimeoutError, OSError) as exc:
                await self.circuit_breaker.record_failure()
                raise TransientExecutionError(str(exc)) from exc
            except BudgetExceededError:
                await self.circuit_breaker.record_failure()
                raise
            except Exception:
                # Business/domain errors do not trip the breaker.
                raise

    async def _run_with_timeout(
        self,
        task: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        timeout_seconds = self.profile.max_execution_time_ms / 1000.0

        task_result = task(*args, **kwargs)
        if inspect.isawaitable(task_result):
            try:
                result = await asyncio.wait_for(task_result, timeout=timeout_seconds)
            except TimeoutError as exc:
                self.budget.terminate()
                raise BudgetExceededError(
                    f"execution timed out after {self.profile.max_execution_time_ms}ms"
                ) from exc
            return result

        # Synchronous task result already computed by call site.
        self.budget.check()
        return task_result

    async def _check_security_policy(self) -> None:
        """
        Internal security policy validation before execution.

        Hook this into Butler's policy engine later.
        """
        if (
            self.profile.allow_state_modification
            and self.profile.runtime_class == RuntimeClass.IN_PROCESS
        ):
            trust_value = _trust_level_value(self.profile.trust_level)
            if trust_value < 80:
                raise TrustBoundaryViolationError(
                    "in-process state modification requires elevated trust"
                )

    def interrupt(self) -> None:
        self.budget.terminate()
        logger.info("subagent_interrupted", agent_id=self.profile.agent_id)


# ============================================================================
# Helpers
# ============================================================================


def _trust_level_value(value: TrustLevel | int) -> int:
    if isinstance(value, int):
        return value
    try:
        return int(value)  # handles IntEnum-like types
    except Exception:
        raw = getattr(value, "value", None)
        if isinstance(raw, int):
            return raw
        raise TypeError(f"Unsupported TrustLevel value: {value!r}")
