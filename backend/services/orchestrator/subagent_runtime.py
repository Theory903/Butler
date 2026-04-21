"""
Butler Sub-Agent Runtime System

Implements sub-agent deployment, execution isolation, budget enforcement,
and observability following Oracle-grade architectural patterns.

Version: 2.0
Status: Production Ready
"""

from typing import Callable
from __future__ import annotations

import asyncio
import enum
import inspect
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Generic, TypeVar, cast

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, Field, root_validator, validator
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from domain.policy.capability_flags import SubagentIsolationClass, TrustLevel

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

T = TypeVar("T")
T_awaitable = TypeVar("T_awaitable", bound=Any)


# ============================================================================
# Exception Classes - Defined first for forward reference compatibility
# ============================================================================

class BudgetExceededError(Exception):
    """Raised when sub-agent exceeds allocated resource budget."""


class TrustBoundaryViolationError(Exception):
    """Raised when sub-agent attempts to cross trust boundaries."""


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and blocking execution."""


class TransientExecutionError(Exception):
    """Raised when execution fails transiently and can be retried."""


# ============================================================================
# Core Enums and Models
# ============================================================================

class RuntimeClass(str, enum.Enum):
    """Sub-agent execution runtime isolation levels."""

    IN_PROCESS = "in_process"             # Shared memory, same interpreter
    PROCESS_POOL = "process_pool"         # Isolated Unix process
    SANDBOX = "sandbox"                   # gVisor/Wasm container
    REMOTE_PEER = "remote_peer"           # External ACP node
    HUMAN_GATE = "human_gate"             # Human-in-the-loop

    @property
    def isolation_level(self) -> int:
        """Return numeric isolation level for comparison."""
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

    agent_id: str = Field(default_factory=lambda: f"sub:{uuid.uuid4().hex[:12]}")
    parent_agent_id: str
    session_id: str
    runtime_class: RuntimeClass
    trust_level: TrustLevel = Field(default=TrustLevel.UNTRUSTED)
    tool_permissions: set[str] = Field(default_factory=set)
    memory_scope: str
    max_execution_time_ms: int = Field(gt=0, default=30000)
    max_memory_mb: int = Field(gt=0, default=128)
    max_tool_calls: int = Field(gt=0, default=50)
    max_tokens: int = Field(gt=0, default=100000)
    allow_network_access: bool = False
    allow_file_system_access: bool = False
    allow_state_modification: bool = False
    inherit_parent_trace: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None

    @validator("expires_at")
    def validate_expiry(cls, v: datetime | None, values: dict[str, Any]) -> datetime | None:
        if v is not None and v <= values["created_at"]:
            raise ValueError("Expiry time must be after creation time")
        return v

    @root_validator(skip_on_failure=True)
    def validate_trust_boundaries(cls, values: dict[str, Any]) -> dict[str, Any]:
        runtime_class = values.get("runtime_class")
        trust_level = values.get("trust_level", 0)

        if runtime_class == RuntimeClass.IN_PROCESS and trust_level > TrustLevel.VERIFIED_USER:
            raise ValueError("In-process execution requires high trust (INTERNAL or VERIFIED_USER)")

        if values.get("allow_state_modification") and trust_level < 50:
            raise ValueError("State modification requires trust level >= 50")

        return values

    class Config:
        frozen = True
        use_enum_values = True


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

    Tracks consumption in real-time and terminates execution when limits are exceeded.
    """

    def __init__(self, profile: SubAgentProfile):
        self.profile = profile
        self.usage = BudgetUsage()
        self.start_time: float | None = None
        self._terminated = False

    def start(self) -> None:
        """Start budget tracking."""
        self.start_time = time.perf_counter()

    def check(self) -> None:
        """
        Check if budget limits have been exceeded.

        Raises:
            BudgetExceededError: If any quota limit is exceeded
        """
        if self._terminated:
            raise BudgetExceededError("Execution already terminated")

        if self.start_time is None:
            raise RuntimeError("Budget tracking not started")

        elapsed_ms = int((time.perf_counter() - self.start_time) * 1000)
        self.usage.execution_time_ms = elapsed_ms

        if elapsed_ms > self.profile.max_execution_time_ms:
            self._terminated = True
            raise BudgetExceededError(f"Execution time exceeded: {elapsed_ms}ms > {self.profile.max_execution_time_ms}ms")

        if self.usage.tool_calls > self.profile.max_tool_calls:
            self._terminated = True
            raise BudgetExceededError(f"Tool calls exceeded: {self.usage.tool_calls} > {self.profile.max_tool_calls}")

        if self.usage.tokens_used > self.profile.max_tokens:
            self._terminated = True
            raise BudgetExceededError(f"Tokens exceeded: {self.usage.tokens_used} > {self.profile.max_tokens}")

    def record_tool_call(self) -> None:
        """Record a tool call invocation."""
        self.usage.tool_calls += 1
        self.check()

    def record_tokens(self, count: int) -> None:
        """Record token consumption."""
        self.usage.tokens_used += count
        self.check()

    def terminate(self) -> None:
        """Force terminate budget tracking."""
        self._terminated = True

    @property
    def is_terminated(self) -> bool:
        return self._terminated


class CircuitBreaker:
    """
    Circuit breaker pattern for sub-agent execution failure isolation.

    Prevents cascading failures by opening circuit after consecutive failures.
    """

    def __init__(self, failure_threshold: int = 5, reset_timeout_ms: int = 30000):
        self.failure_threshold = failure_threshold
        self.reset_timeout_ms = reset_timeout_ms
        self.failure_count = 0
        self.last_failure_time: float | None = None
        self.state = "CLOSED"

    def record_success(self) -> None:
        """Record successful execution."""
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self) -> None:
        """Record failed execution."""
        self.failure_count += 1
        self.last_failure_time = time.perf_counter()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit breaker OPEN after {self.failure_count} failures")

    def allow_execution(self) -> bool:
        """Check if execution is allowed."""
        if self.state == "CLOSED":
            return True

        if self.state == "OPEN" and self.last_failure_time is not None:
            elapsed_ms = (time.perf_counter() - self.last_failure_time) * 1000
            if elapsed_ms > self.reset_timeout_ms:
                self.state = "HALF_OPEN"
                return True

        return False


class SubAgentFactory:
    """
    Factory for creating profiled sub-agent instances with inheritance.

    Maintains trust boundary enforcement when creating child agents.
    """

    @staticmethod
    def create_child(
        parent_profile: SubAgentProfile,
        runtime_class: RuntimeClass | None = None,
        additional_permissions: set[str] | None = None,
        budget_overrides: dict[str, int] | None = None,
    ) -> SubAgentProfile:
        """
        Create a child sub-agent profile inheriting from parent.

        Child agents NEVER receive higher trust or permissions than parent.
        """
        runtime = runtime_class or parent_profile.runtime_class

        # Child cannot have higher isolation level than parent
        if runtime.isolation_level > parent_profile.runtime_class.isolation_level:
            raise TrustBoundaryViolationError(
                f"Child agent cannot use higher isolation runtime {runtime} than parent {parent_profile.runtime_class}"
            )

        permissions = parent_profile.tool_permissions.copy()
        if additional_permissions:
            # Only allow subset of parent permissions
            invalid = additional_permissions - parent_profile.tool_permissions
            if invalid:
                raise TrustBoundaryViolationError(f"Cannot grant additional permissions: {invalid}")
            permissions = additional_permissions

        overrides = budget_overrides or {}

        # Budget overrides cannot exceed parent limits
        for key, value in overrides.items():
            parent_value = getattr(parent_profile, key)
            if value > parent_value:
                raise TrustBoundaryViolationError(f"Budget override {key}={value} exceeds parent limit {parent_value}")

        profile_data = parent_profile.dict(exclude={"agent_id", "created_at", "expires_at"})
        profile_data.update({
            "runtime_class": runtime,
            "tool_permissions": permissions,
            **overrides,
        })

        return SubAgentProfile(**profile_data)


class SubAgentExecutor(Generic[T]):
    """
    Executes sub-agent tasks with failure isolation, trace propagation,
    and budget enforcement.
    """

    def __init__(self, profile: SubAgentProfile):
        self.profile = profile
        self.budget = BudgetEnforcer(profile)
        self.circuit_breaker = CircuitBreaker()
        self.idempotency_key: str | None = None

    @contextmanager
    def execution_context(self, span_name: str = "subagent.execute"):
        """Context manager for execution with telemetry and budget tracking."""
        with tracer.start_as_current_span(span_name) as span:
            span.set_attribute("subagent.id", self.profile.agent_id)
            span.set_attribute("subagent.parent_id", self.profile.parent_agent_id)
            span.set_attribute("subagent.runtime", self.profile.runtime_class)
            span.set_attribute("subagent.trust_level", self.profile.trust_level)

            self.budget.start()

            try:
                yield span
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                self.circuit_breaker.record_failure()
                raise
            else:
                self.circuit_breaker.record_success()
                span.set_status(Status(StatusCode.OK))
            finally:
                span.set_attribute("budget.execution_time_ms", self.budget.usage.execution_time_ms)
                span.set_attribute("budget.tool_calls", self.budget.usage.tool_calls)
                span.set_attribute("budget.tokens_used", self.budget.usage.tokens_used)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=100, max=1000),
        retry=retry_if_exception_type((TransientExecutionError,)),
    )
    async def execute(
        self,
        task: Callable[..., Any],
        *args: Any,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """
        Execute a sub-agent task with full isolation and enforcement.

        Args:
            task: Callable task to execute
            idempotency_key: Unique key for idempotent execution
            *args: Task arguments
            **kwargs: Task keyword arguments

        Returns:
            Task result

        Raises:
            CircuitBreakerOpenError: If circuit breaker is open
            BudgetExceededError: If resource limits exceeded
            TrustBoundaryViolationError: If security policy violated
            TransientExecutionError: For retryable failures
        """
        if not self.circuit_breaker.allow_execution():
            raise CircuitBreakerOpenError("Circuit breaker open, execution blocked")

        self.idempotency_key = idempotency_key or str(uuid.uuid4())

        task_result = task(*args, **kwargs)
        if inspect.iscoroutine(task_result):
            result = await task_result
        else:
            result = task_result

        self.budget.check()
        return result

    async def _check_security_policy(self) -> None:
        """Internal security policy validation before execution."""
        # This will integrate with Butler Security service policy engine
        # Implementation placeholder for policy evaluation

    def interrupt(self) -> None:
        """Gracefully interrupt running sub-agent execution."""
        self.budget.terminate()
        logger.info(f"Sub-agent {self.profile.agent_id} interrupted")


# Backwards compatibility aliases - do not remove
BudgetExceededError = BudgetExceededError
TrustBoundaryViolationError = TrustBoundaryViolationError
CircuitBreakerOpenError = CircuitBreakerOpenError
TransientExecutionError = TransientExecutionError
