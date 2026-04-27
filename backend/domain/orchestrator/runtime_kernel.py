"""Butler Runtime Kernel.

The single authority that selects and dispatches task execution strategy.

Execution strategies
--------------------
DETERMINISTIC  – Butler-native tool dispatch, no LLM loop.
HERMES_AGENT   – Hermes agentic loop (multi-turn, tool-calling).
WORKFLOW_DAG   – Durable long-running workflow with checkpoints.
SUBAGENT       – Delegated ACP execution via another Butler agent.

Backends are injected through typed Protocol contracts and bound at
composition time.  The kernel does not own persistence, transport, or
checkpoint storage.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

import structlog

if TYPE_CHECKING:
    from domain.events.schemas import ButlerEvent, StreamFinalEvent, StreamTokenEvent
    from domain.orchestrator.models import Task, Workflow
    from domain.tools.models import ButlerToolSpec

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ExecutionStrategy(StrEnum):
    """Execution strategy selected by the runtime kernel."""

    DETERMINISTIC = "deterministic"
    HERMES_AGENT = "hermes_agent"
    WORKFLOW_DAG = "workflow_dag"
    SUBAGENT = "subagent"


class StopReason(StrEnum):
    """Canonical execution stop reasons across all backends."""

    END_TURN = "end_turn"
    APPROVAL_REQUIRED = "approval_required"
    MAX_ITERATIONS = "max_iterations"
    ERROR = "error"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExecutionMessage:
    """Canonical execution message passed into runtime backends."""

    role: str
    content: str
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """Immutable runtime context passed to execution backends.

    This is the single canonical runtime contract.  Backends must not
    spelunk ``workflow`` or ``task`` internals for fields that are already
    surfaced here.
    """

    task: Task
    workflow: Workflow
    strategy: ExecutionStrategy

    model: str
    toolset: Sequence[ButlerToolSpec]
    system_prompt: str
    messages: Sequence[ExecutionMessage]

    trace_id: str
    account_id: str
    tenant_id: str
    session_id: str

    # Runtime policy / context surface
    account_tier: str = "free"
    channel: str = "api"
    assurance_level: str = "AAL1"
    user_id: str | None = None
    product_tier: object | None = None
    industry_profile: object | None = None

    # Optional inline event observation hook (best-effort, never raises)
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
    """Canonical typed result returned by all runtime backends."""

    content: str
    actions: Sequence[Mapping[str, object]] = field(default_factory=tuple)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    duration_ms: int = 0
    tool_calls_made: int = 0
    stopped_reason: StopReason = StopReason.END_TURN

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    def to_legacy_dict(self) -> dict[str, object]:
        """Return a plain dict compatible with existing callers."""
        return {
            "content": self.content,
            "actions": list(self.actions),
            "input_tokens": self.token_usage.input_tokens,
            "output_tokens": self.token_usage.output_tokens,
            "cache_read_tokens": self.token_usage.cache_read_tokens,
            "estimated_cost_usd": self.token_usage.estimated_cost_usd,
            "duration_ms": self.duration_ms,
            "tool_calls_made": self.tool_calls_made,
            "stopped_reason": self.stopped_reason.value,
        }

    @classmethod
    def from_backend_payload(cls, payload: Mapping[str, object]) -> ExecutionResult:
        """Coerce a raw backend payload dict into the canonical result."""
        raw_actions = payload.get("actions") or []
        if isinstance(raw_actions, Sequence) and not isinstance(raw_actions, (str, bytes)):
            actions: tuple[Mapping[str, object], ...] = tuple(
                item for item in raw_actions if isinstance(item, Mapping)
            )
        else:
            actions = ()

        return cls(
            content=str(payload.get("content") or ""),
            actions=actions,
            token_usage=TokenUsage(
                input_tokens=int(payload.get("input_tokens") or 0),
                output_tokens=int(payload.get("output_tokens") or 0),
                cache_read_tokens=int(payload.get("cache_read_tokens") or 0),
                estimated_cost_usd=float(payload.get("estimated_cost_usd") or 0.0),
            ),
            duration_ms=int(payload.get("duration_ms") or 0),
            tool_calls_made=int(payload.get("tool_calls_made") or 0),
            stopped_reason=_coerce_stop_reason(
                str(payload.get("stopped_reason") or StopReason.END_TURN.value)
            ),
        )


# ---------------------------------------------------------------------------
# Backend Protocols
# ---------------------------------------------------------------------------


class DeterministicExecutionBackend(Protocol):
    async def execute(self, ctx: ExecutionContext) -> Mapping[str, object] | ExecutionResult: ...


class HermesExecutionBackend(Protocol):
    async def run(self, ctx: ExecutionContext) -> Mapping[str, object] | ExecutionResult: ...

    async def run_streaming(self, ctx: ExecutionContext) -> AsyncGenerator[ButlerEvent]: ...


class WorkflowExecutionBackend(Protocol):
    async def execute(self, ctx: ExecutionContext) -> Mapping[str, object] | ExecutionResult: ...


class SubagentExecutionBackend(Protocol):
    async def delegate(self, ctx: ExecutionContext) -> Mapping[str, object] | ExecutionResult: ...


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class RuntimeKernelConfigurationError(RuntimeError):
    """Raised when a selected strategy has no backend wired."""


# ---------------------------------------------------------------------------
# Strategy selection helpers  (pure, no I/O)
# ---------------------------------------------------------------------------

_DETERMINISTIC_TASK_TYPES: frozenset[str] = frozenset(
    {"memory_recall", "verify_result", "system_stats"}
)
_AGENT_TASK_TYPES: frozenset[str] = frozenset({"", "session", "orchestrator"})


def _is_subagent_task(task_type: str, has_acp_target: bool) -> bool:
    return task_type == "delegate" or has_acp_target


def _is_deterministic_task(
    task_type: str,
    intent: str,
    step_count: int,
    requires_reasoning: bool,
) -> bool:
    if requires_reasoning:
        return False

    is_deterministic_intent = intent == "system_stats"
    is_deterministic_type = task_type in _DETERMINISTIC_TASK_TYPES

    if not (is_deterministic_type or is_deterministic_intent):
        return False

    max_steps = 2 if is_deterministic_intent else 1
    return step_count <= max_steps


def _is_workflow_task(
    task_type: str,
    mode: str,
    step_count: int,
    resumable: bool,
) -> bool:
    # Tasks with explicit types route deterministically or to Hermes, not DAG.
    if task_type not in _AGENT_TASK_TYPES:
        return False
    return mode == "durable" or step_count > 8 or resumable


# ---------------------------------------------------------------------------
# RuntimeKernel
# ---------------------------------------------------------------------------


class RuntimeKernel:
    """Strategy-selection authority for Butler task execution.

    Backends are injected at construction time.  Two backends
    (``workflow`` and ``subagent``) may also be bound after construction via
    their explicit ``bind_*`` methods to break circular-dependency cycles at
    the composition root.
    """

    __slots__ = ("_deterministic", "_hermes", "_workflow", "_subagent")

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

    # ------------------------------------------------------------------
    # Late-binding (for dependency-cycle resolution at composition root)
    # ------------------------------------------------------------------

    def bind_workflow_backend(self, backend: WorkflowExecutionBackend) -> None:
        self._workflow = backend

    def bind_subagent_backend(self, backend: SubagentExecutionBackend) -> None:
        self._subagent = backend

    # ------------------------------------------------------------------
    # Strategy selection
    # ------------------------------------------------------------------

    def choose_strategy(self, task: Task, workflow: Workflow) -> ExecutionStrategy:
        """Return the correct execution strategy for *task* in *workflow*."""
        mode = str(getattr(workflow, "mode", "") or "")
        task_type = str(getattr(task, "task_type", "") or "")
        intent = str(getattr(workflow, "intent", "") or "")
        plan: dict[str, Any] = getattr(workflow, "plan_schema", {}) or {}
        steps: list[Any] = plan.get("steps") or []

        has_acp_target: bool = bool(plan.get("acp_target"))
        requires_reasoning: bool = bool(plan.get("requires_reasoning"))
        resumable: bool = bool(plan.get("resumable"))
        step_count = len(steps)

        if _is_subagent_task(task_type, has_acp_target):
            return self._selected(
                task, ExecutionStrategy.SUBAGENT, "delegate_or_acp_target"
            )

        if _is_deterministic_task(task_type, intent, step_count, requires_reasoning):
            return self._selected(
                task,
                ExecutionStrategy.DETERMINISTIC,
                f"deterministic_fast_path task_type={task_type!r} intent={intent!r}",
            )

        if _is_workflow_task(task_type, mode, step_count, resumable):
            return self._selected(
                task,
                ExecutionStrategy.WORKFLOW_DAG,
                f"durable_workflow mode={mode!r} steps={step_count} resumable={resumable}",
            )

        return self._selected(
            task,
            ExecutionStrategy.HERMES_AGENT,
            f"default_agentic task_type={task_type!r}",
        )

    # ------------------------------------------------------------------
    # Execution entry points
    # ------------------------------------------------------------------

    async def execute(self, ctx: ExecutionContext) -> dict[str, object]:
        """Execute *ctx* and return a legacy-compatible dict."""
        self._log_execute("runtime_kernel_execute_started", ctx)
        result = await self._dispatch(ctx)
        return result.to_legacy_dict()

    async def execute_result(self, ctx: ExecutionContext) -> ExecutionResult:
        """Execute *ctx* and return the canonical typed result."""
        self._log_execute("runtime_kernel_execute_result_started", ctx)
        return await self._dispatch(ctx)

    async def execute_streaming(
        self, ctx: ExecutionContext
    ) -> AsyncGenerator[ButlerEvent]:
        """Stream canonical Butler events for *ctx*.

        Hermes uses its native streaming path.  All other strategies are
        adapted into a single token event followed by a final event.
        """
        if ctx.strategy == ExecutionStrategy.HERMES_AGENT:
            async for event in self._require_hermes().run_streaming(ctx):
                self._emit_hook(ctx, event)
                yield event
            return

        result = await self._dispatch(ctx)
        async for event in self._adapt_result_to_events(ctx, result):
            yield event

    # ------------------------------------------------------------------
    # Internal dispatch
    # ------------------------------------------------------------------

    async def _dispatch(self, ctx: ExecutionContext) -> ExecutionResult:
        match ctx.strategy:
            case ExecutionStrategy.DETERMINISTIC:
                payload = await self._require_deterministic().execute(ctx)
            case ExecutionStrategy.HERMES_AGENT:
                payload = await self._require_hermes().run(ctx)
            case ExecutionStrategy.WORKFLOW_DAG:
                payload = await self._require_workflow().execute(ctx)
            case ExecutionStrategy.SUBAGENT:
                payload = await self._require_subagent().delegate(ctx)
            case _:  # unreachable — guards exhaustiveness should new variants be added
                raise RuntimeKernelConfigurationError(
                    f"Unsupported execution strategy: {ctx.strategy!r}"
                )

        return self._normalize_result(payload)

    # ------------------------------------------------------------------
    # Result normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_result(
        payload: Mapping[str, object] | ExecutionResult | Any,
    ) -> ExecutionResult:
        """Coerce any backend return value into an ``ExecutionResult``."""
        if isinstance(payload, ExecutionResult):
            return payload

        if isinstance(payload, Mapping):
            return ExecutionResult.from_backend_payload(payload)

        # Backends that return a domain object with a ``content`` attribute
        # are converted to a Mapping first so the same path handles them.
        if hasattr(payload, "content"):
            proxy: dict[str, object] = {
                "content": getattr(payload, "content", ""),
                "actions": getattr(payload, "actions", ()),
                "input_tokens": getattr(payload, "input_tokens", 0),
                "output_tokens": getattr(payload, "output_tokens", 0),
                "cache_read_tokens": getattr(payload, "cache_read_tokens", 0),
                "estimated_cost_usd": getattr(payload, "estimated_cost_usd", 0.0),
                "duration_ms": getattr(payload, "duration_ms", 0),
                "tool_calls_made": getattr(payload, "tool_calls_made", 0),
                "stopped_reason": getattr(
                    payload, "stopped_reason", StopReason.END_TURN.value
                ),
            }
            return ExecutionResult.from_backend_payload(proxy)

        raise TypeError(
            f"Cannot normalize backend result of type {type(payload)!r}. "
            "Backend must return ExecutionResult, Mapping, or an object with a 'content' attribute."
        )

    # ------------------------------------------------------------------
    # Streaming adapter for non-Hermes strategies
    # ------------------------------------------------------------------

    @staticmethod
    def _adapt_result_to_events(
        ctx: ExecutionContext, result: ExecutionResult
    ) -> AsyncGenerator[ButlerEvent]:
        """Yield a StreamTokenEvent + StreamFinalEvent for a completed result."""
        # Late import keeps the module importable even when domain.events is
        # partially initialised (e.g. during test collection).
        from domain.events.schemas import StreamFinalEvent, StreamTokenEvent

        async def _gen() -> AsyncGenerator[ButlerEvent]:
            if result.content:
                yield StreamTokenEvent(
                    account_id=ctx.account_id,
                    session_id=ctx.session_id,
                    task_id=str(ctx.task.id),
                    trace_id=ctx.trace_id,
                    payload={"content": result.content, "index": 0},
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
                    "tool_calls_made": result.tool_calls_made,
                    "stopped_reason": result.stopped_reason.value,
                },
            )

        return _gen()

    # ------------------------------------------------------------------
    # Backend guards
    # ------------------------------------------------------------------

    def _require_deterministic(self) -> DeterministicExecutionBackend:
        if self._deterministic is None:
            raise RuntimeKernelConfigurationError(
                "DETERMINISTIC strategy selected but no deterministic backend is wired."
            )
        return self._deterministic

    def _require_hermes(self) -> HermesExecutionBackend:
        if self._hermes is None:
            raise RuntimeKernelConfigurationError(
                "HERMES_AGENT strategy selected but no Hermes backend is wired."
            )
        return self._hermes

    def _require_workflow(self) -> WorkflowExecutionBackend:
        if self._workflow is None:
            raise RuntimeKernelConfigurationError(
                "WORKFLOW_DAG strategy selected but no workflow backend is wired."
            )
        return self._workflow

    def _require_subagent(self) -> SubagentExecutionBackend:
        if self._subagent is None:
            raise RuntimeKernelConfigurationError(
                "SUBAGENT strategy selected but no subagent backend is wired."
            )
        return self._subagent

    # ------------------------------------------------------------------
    # Logging / hook helpers
    # ------------------------------------------------------------------

    def _emit_hook(self, ctx: ExecutionContext, event: ButlerEvent) -> None:
        """Call ``ctx.on_event`` in a best-effort, never-raising wrapper."""
        if ctx.on_event is None:
            return
        try:
            ctx.on_event(event)
        except Exception:
            logger.warning(
                "runtime_kernel_on_event_hook_failed",
                task_id=str(getattr(ctx.task, "id", "")),
                trace_id=ctx.trace_id,
            )

    @staticmethod
    def _selected(
        task: Task,
        strategy: ExecutionStrategy,
        reason: str,
    ) -> ExecutionStrategy:
        logger.info(
            "kernel_strategy_selected",
            strategy=strategy.value,
            reason=reason,
            task_id=str(getattr(task, "id", "")),
        )
        return strategy

    @staticmethod
    def _log_execute(event_name: str, ctx: ExecutionContext) -> None:
        logger.info(
            event_name,
            strategy=ctx.strategy.value,
            task_type=getattr(ctx.task, "task_type", None),
            task_id=str(getattr(ctx.task, "id", "")),
            trace_id=ctx.trace_id,
            session_id=ctx.session_id,
        )


# ---------------------------------------------------------------------------
# Module-level utility
# ---------------------------------------------------------------------------


def _coerce_stop_reason(value: str) -> StopReason:
    """Return the matching ``StopReason`` or ``ERROR`` for unrecognised values."""
    normalised = (value or "").strip().lower()
    for member in StopReason:
        if member.value == normalised:
            return member
    return StopReason.ERROR