"""Butler Runtime Kernel.

The single authority that chooses how a task is executed.

Hermes agent loop is one execution strategy among several. Butler owns
checkpoint boundaries, state progression, and execution strategy selection.

Execution strategies:
    DETERMINISTIC  - Butler-native tool dispatch, no LLM loop
    HERMES_AGENT   - Hermes agentic loop (multi-turn, tool-calling)
    WORKFLOW_DAG   - Durable long-running workflow with checkpoints
    SUBAGENT       - Delegated ACP execution via another Butler agent
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, AsyncGenerator, Callable, Mapping, Protocol, Sequence

import structlog

if TYPE_CHECKING:
    from domain.events.schemas import ButlerEvent
    from domain.orchestrator.models import Task, Workflow
    from domain.tools.models import ButlerToolSpec


logger = structlog.get_logger(__name__)


class ExecutionStrategy(str, Enum):
    """Execution strategy selected by the runtime kernel."""

    DETERMINISTIC = "deterministic"
    HERMES_AGENT = "hermes_agent"
    WORKFLOW_DAG = "workflow_dag"
    SUBAGENT = "subagent"


@dataclass(frozen=True, slots=True)
class ExecutionMessage:
    """Canonical execution message passed into runtime backends."""

    role: str
    content: str
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """Immutable runtime context passed to execution backends."""

    task: Task
    workflow: Workflow
    strategy: ExecutionStrategy
    model: str
    toolset: Sequence[ButlerToolSpec]
    system_prompt: str
    messages: Sequence[ExecutionMessage]
    trace_id: str
    account_id: str
    session_id: str
    on_event: Callable[[ButlerEvent], None] | None = None


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Canonical token accounting for one execution."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    estimated_cost_usd: float = 0.0


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Canonical result returned by all runtime backends."""

    content: str
    actions: Sequence[Mapping[str, object]] = field(default_factory=tuple)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    duration_ms: int = 0

    def to_legacy_dict(self) -> dict[str, object]:
        """Convert to legacy dict shape for compatibility with existing callers."""
        return {
            "content": self.content,
            "actions": list(self.actions),
            "input_tokens": self.token_usage.input_tokens,
            "output_tokens": self.token_usage.output_tokens,
            "cache_read_tokens": self.token_usage.cache_read_tokens,
            "estimated_cost_usd": self.token_usage.estimated_cost_usd,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_backend_payload(cls, payload: Mapping[str, object]) -> ExecutionResult:
        """Normalize a backend payload into the canonical execution result."""
        return cls(
            content=str(payload.get("content", "")),
            actions=tuple(payload.get("actions", []) or []),
            token_usage=TokenUsage(
                input_tokens=int(payload.get("input_tokens", 0) or 0),
                output_tokens=int(payload.get("output_tokens", 0) or 0),
                cache_read_tokens=int(payload.get("cache_read_tokens", 0) or 0),
                estimated_cost_usd=float(payload.get("estimated_cost_usd", 0.0) or 0.0),
            ),
            duration_ms=int(payload.get("duration_ms", 0) or 0),
        )


class DeterministicExecutionBackend(Protocol):
    """Contract for deterministic execution backends."""

    async def execute(self, ctx: ExecutionContext) -> Mapping[str, object] | ExecutionResult:
        """Execute a deterministic task."""


class HermesExecutionBackend(Protocol):
    """Contract for Hermes agentic execution backends."""

    async def run(self, ctx: ExecutionContext) -> Mapping[str, object] | ExecutionResult:
        """Execute the Hermes agentic loop."""

    async def run_streaming(
        self,
        ctx: ExecutionContext,
    ) -> AsyncGenerator[ButlerEvent, None]:
        """Stream canonical Butler events for the Hermes execution."""


class WorkflowExecutionBackend(Protocol):
    """Contract for durable workflow execution backends."""

    async def execute(self, ctx: ExecutionContext) -> Mapping[str, object] | ExecutionResult:
        """Execute a durable workflow task."""


class SubagentExecutionBackend(Protocol):
    """Contract for delegated subagent execution backends."""

    async def delegate(self, ctx: ExecutionContext) -> Mapping[str, object] | ExecutionResult:
        """Delegate execution to a subagent boundary."""


class RuntimeKernelConfigurationError(RuntimeError):
    """Raised when the kernel selects a strategy whose backend is not configured."""


class RuntimeKernel:
    """Strategy-selection authority for Butler task execution.

    The runtime kernel decides *how* a task runs. It does not own persistence,
    transport, or checkpoint storage. Backends are injected through explicit
    contracts and may be bound at assembly time.
    """

    def __init__(
        self,
        *,
        deterministic_backend: DeterministicExecutionBackend | None = None,
        hermes_backend: HermesExecutionBackend | None = None,
        workflow_backend: WorkflowExecutionBackend | None = None,
        subagent_backend: SubagentExecutionBackend | None = None,
    ) -> None:
        self._deterministic = deterministic_backend
        self._hermes = hermes_backend
        self._workflow = workflow_backend
        self._subagent = subagent_backend

    def bind_workflow_backend(self, workflow_backend: WorkflowExecutionBackend) -> None:
        """Bind the workflow backend after construction."""
        self._workflow = workflow_backend

    def bind_subagent_backend(self, subagent_backend: SubagentExecutionBackend) -> None:
        """Bind the subagent backend after construction."""
        self._subagent = subagent_backend

    def choose_strategy(self, task: Task, workflow: Workflow) -> ExecutionStrategy:
        """Choose the correct execution strategy for the given task."""
        mode = str(getattr(workflow, "mode", "") or "")
        task_type = str(getattr(task, "task_type", "") or "")
        intent = str(getattr(workflow, "intent", "") or "")
        plan = getattr(workflow, "plan_schema", {}) or {}
        steps = plan.get("steps", []) or []

        has_acp_target = bool(plan.get("acp_target"))
        requires_reasoning = bool(plan.get("requires_reasoning"))
        is_resumable = bool(plan.get("resumable"))

        if self._is_subagent_task(task_type=task_type, has_acp_target=has_acp_target):
            self._log_strategy(
                task=task,
                strategy=ExecutionStrategy.SUBAGENT,
                reason="delegate_or_acp_target",
            )
            return ExecutionStrategy.SUBAGENT

        if self._is_deterministic_task(
            task_type=task_type,
            intent=intent,
            step_count=len(steps),
            requires_reasoning=requires_reasoning,
        ):
            self._log_strategy(
                task=task,
                strategy=ExecutionStrategy.DETERMINISTIC,
                reason=(
                    "deterministic_fast_path "
                    f"task_type={task_type or 'unknown'} intent={intent or 'unknown'}"
                ),
            )
            return ExecutionStrategy.DETERMINISTIC

        if self._is_workflow_task(
            task_type=task_type,
            mode=mode,
            step_count=len(steps),
            resumable=is_resumable,
        ):
            self._log_strategy(
                task=task,
                strategy=ExecutionStrategy.WORKFLOW_DAG,
                reason=f"durable_workflow mode={mode} steps={len(steps)} resumable={is_resumable}",
            )
            return ExecutionStrategy.WORKFLOW_DAG

        self._log_strategy(
            task=task,
            strategy=ExecutionStrategy.HERMES_AGENT,
            reason=f"default_agentic task_type={task_type or 'unknown'}",
        )
        return ExecutionStrategy.HERMES_AGENT

    async def execute(self, ctx: ExecutionContext) -> dict[str, object]:
        """Execute a task with the strategy already selected in the context."""
        logger.info(
            "runtime_kernel_execute_started",
            strategy=ctx.strategy,
            task_type=getattr(ctx.task, "task_type", None),
            task_id=str(getattr(ctx.task, "id", "")),
            trace_id=ctx.trace_id,
            session_id=ctx.session_id,
        )

        result = await self._dispatch(ctx)
        return result.to_legacy_dict()

    async def execute_result(self, ctx: ExecutionContext) -> ExecutionResult:
        """Execute a task and return the canonical typed result."""
        logger.info(
            "runtime_kernel_execute_result_started",
            strategy=ctx.strategy,
            task_type=getattr(ctx.task, "task_type", None),
            task_id=str(getattr(ctx.task, "id", "")),
            trace_id=ctx.trace_id,
            session_id=ctx.session_id,
        )
        return await self._dispatch(ctx)

    async def execute_streaming(
        self,
        ctx: ExecutionContext,
    ) -> AsyncGenerator[ButlerEvent, None]:
        """Execute a task and stream canonical Butler events."""
        if ctx.strategy == ExecutionStrategy.HERMES_AGENT:
            hermes_backend = self._require_hermes_backend()
            async for event in hermes_backend.run_streaming(ctx):
                yield event
            return

        result = await self._dispatch(ctx)

        from domain.events.schemas import StreamFinalEvent, StreamTokenEvent

        if result.content:
            yield StreamTokenEvent(
                account_id=ctx.account_id,
                session_id=ctx.session_id,
                task_id=str(ctx.task.id),
                trace_id=ctx.trace_id,
                payload={"content": result.content},
            )

        yield StreamFinalEvent(
            account_id=ctx.account_id,
            session_id=ctx.session_id,
            task_id=str(ctx.task.id),
            trace_id=ctx.trace_id,
            payload={
                "content": result.content,
                "input_tokens": result.token_usage.input_tokens,
                "output_tokens": result.token_usage.output_tokens,
                "cache_read_tokens": result.token_usage.cache_read_tokens,
                "estimated_cost_usd": result.token_usage.estimated_cost_usd,
                "duration_ms": result.duration_ms,
            },
        )

    async def _dispatch(self, ctx: ExecutionContext) -> ExecutionResult:
        """Dispatch execution to the configured backend for the selected strategy."""
        match ctx.strategy:
            case ExecutionStrategy.DETERMINISTIC:
                backend = self._require_deterministic_backend()
                payload = await backend.execute(ctx)
                return self._normalize_result(payload)

            case ExecutionStrategy.HERMES_AGENT:
                backend = self._require_hermes_backend()
                payload = await backend.run(ctx)
                return self._normalize_result(payload)

            case ExecutionStrategy.WORKFLOW_DAG:
                backend = self._require_workflow_backend()
                payload = await backend.execute(ctx)
                return self._normalize_result(payload)

            case ExecutionStrategy.SUBAGENT:
                backend = self._require_subagent_backend()
                payload = await backend.delegate(ctx)
                return self._normalize_result(payload)

        raise RuntimeKernelConfigurationError(
            f"Unsupported execution strategy selected: {ctx.strategy!r}"
        )

    def _normalize_result(
        self,
        payload: Mapping[str, object] | ExecutionResult,
    ) -> ExecutionResult:
        """Normalize a backend return value into the canonical execution result."""
        if isinstance(payload, ExecutionResult):
            return payload
        return ExecutionResult.from_backend_payload(payload)

    def _require_deterministic_backend(self) -> DeterministicExecutionBackend:
        if self._deterministic is None:
            raise RuntimeKernelConfigurationError(
                "Deterministic strategy selected but no deterministic backend is wired."
            )
        return self._deterministic

    def _require_hermes_backend(self) -> HermesExecutionBackend:
        if self._hermes is None:
            raise RuntimeKernelConfigurationError(
                "Hermes strategy selected but no Hermes backend is wired."
            )
        return self._hermes

    def _require_workflow_backend(self) -> WorkflowExecutionBackend:
        if self._workflow is None:
            raise RuntimeKernelConfigurationError(
                "Workflow strategy selected but no workflow backend is wired."
            )
        return self._workflow

    def _require_subagent_backend(self) -> SubagentExecutionBackend:
        if self._subagent is None:
            raise RuntimeKernelConfigurationError(
                "Subagent strategy selected but no subagent backend is wired."
            )
        return self._subagent

    def _is_subagent_task(self, *, task_type: str, has_acp_target: bool) -> bool:
        return task_type == "delegate" or has_acp_target

    def _is_deterministic_task(
        self,
        *,
        task_type: str,
        intent: str,
        step_count: int,
        requires_reasoning: bool,
    ) -> bool:
        deterministic_intent = intent == "system_stats"
        deterministic_task_types = {"memory_recall", "verify_result", "system_stats"}

        if requires_reasoning:
            return False

        if task_type not in deterministic_task_types and not deterministic_intent:
            return False

        max_steps = 2 if deterministic_intent else 1
        return step_count <= max_steps

    def _is_workflow_task(
        self,
        *,
        task_type: str,
        mode: str,
        step_count: int,
        resumable: bool,
    ) -> bool:
        is_tool_task = task_type not in {"", "session", "orchestrator"}
        if is_tool_task:
            return False
        return mode == "durable" or step_count > 8 or resumable

    def _log_strategy(
        self,
        *,
        task: Task,
        strategy: ExecutionStrategy,
        reason: str,
    ) -> None:
        logger.info(
            "kernel_strategy_selected",
            strategy=strategy.value,
            reason=reason,
            task_id=str(getattr(task, "id", "")),
        )
