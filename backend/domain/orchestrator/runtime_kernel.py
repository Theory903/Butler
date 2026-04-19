"""Butler Runtime Kernel.

The single authority that chooses how a Task is executed.

Hermes agent loop is ONE execution strategy among several — it is not the
runtime itself. Butler commits task state to PostgreSQL before and after
every Hermes segment. Hermes never owns checkpoint boundaries.

Execution strategies:
  DETERMINISTIC  — Butler-native tool dispatch, no LLM loop
  HERMES_AGENT   — Hermes run_agent.py agentic loop (multi-turn, tool-calling)
  WORKFLOW_DAG   — Durable long-running workflow with checkpoints
  SUBAGENT       — Delegated ACP execution (another Butler agent)

Governed by: docs/00-governance/transplant-constitution.md §5
"""

from __future__ import annotations

import structlog
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, AsyncGenerator, Callable

if TYPE_CHECKING:
    from domain.orchestrator.models import Task, Workflow
    from domain.events.schemas import ButlerEvent

logger = structlog.get_logger(__name__)


class ExecutionStrategy(str, Enum):
    """Execution strategy chosen by RuntimeKernel per task."""
    DETERMINISTIC  = "deterministic"   # Simple direct tool dispatch
    HERMES_AGENT   = "hermes_agent"    # Agentic LLM loop via Hermes
    WORKFLOW_DAG   = "workflow_dag"    # Durable multi-checkpoint workflow
    SUBAGENT       = "subagent"        # ACP delegated execution


@dataclass
class ExecutionContext:
    """Runtime context passed to the chosen execution backend."""
    task: "Task"
    workflow: "Workflow"
    strategy: ExecutionStrategy
    model: str                            # Resolved by ButlerSmartRouter (Phase 5)
    toolset: list                         # Compiled Butler ToolSpecs
    system_prompt: str                    # Built by ButlerPromptBuilder
    messages: list[dict]                  # Conversation history from MemoryService
    trace_id: str
    account_id: str
    session_id: str
    on_event: Callable[["ButlerEvent"], None] | None = None  # stream callback


class RuntimeKernel:
    """Chooses and dispatches the correct execution strategy for each task.

    The kernel is the single point where strategy selection happens.
    Backends are injected — the kernel knows nothing about LLM internals.

    Usage:
        kernel = RuntimeKernel(
            deterministic_backend=ButlerDeterministicExecutor(...),
            hermes_backend=HermesAgentBackend(...),
        )
        result = await kernel.execute(ctx)
    """

    def __init__(
        self,
        deterministic_backend=None,
        hermes_backend=None,
        workflow_backend=None,
        subagent_backend=None,
    ):
        self._deterministic = deterministic_backend
        self._hermes = hermes_backend
        self._workflow = workflow_backend
        self._subagent = subagent_backend

    # ── Strategy selection ────────────────────────────────────────────────────

    def choose_strategy(self, task: "Task", workflow: "Workflow") -> ExecutionStrategy:
        """Choose execution strategy based on task and workflow properties.

        Decision tree (in priority order):

        1. SUBAGENT   — task type is 'delegate' or workflow has acp_target
        2. WORKFLOW_DAG — workflow mode is 'durable' or has >8 steps or resumable flag
        3. DETERMINISTIC — single tool call with no LLM reasoning required
        4. HERMES_AGENT — default: agentic multi-turn LLM loop
        """
        mode = getattr(workflow, "mode", "")
        task_type = getattr(task, "task_type", "")
        plan = getattr(workflow, "plan_schema", {}) or {}
        steps = plan.get("steps", [])
        has_acp_target = bool(plan.get("acp_target"))

        # 1. Delegated ACP execution
        if task_type == "delegate" or has_acp_target:
            logger.info(
                "kernel_strategy_selected",
                strategy=ExecutionStrategy.SUBAGENT,
                reason="delegate_or_acp_target",
                task_id=str(task.id),
            )
            return ExecutionStrategy.SUBAGENT

        # 2. Durable workflow DAG
        if mode == "durable" or len(steps) > 8 or plan.get("resumable"):
            logger.info(
                "kernel_strategy_selected",
                strategy=ExecutionStrategy.WORKFLOW_DAG,
                reason=f"mode={mode} steps={len(steps)}",
                task_id=str(task.id),
            )
            return ExecutionStrategy.WORKFLOW_DAG

        # 3. Single deterministic tool call (no LLM needed)
        if (
            task_type in ("memory_recall", "search_web", "verify_result")
            and len(steps) <= 1
            and not plan.get("requires_reasoning")
        ):
            logger.info(
                "kernel_strategy_selected",
                strategy=ExecutionStrategy.DETERMINISTIC,
                reason=f"single_tool task_type={task_type}",
                task_id=str(task.id),
            )
            return ExecutionStrategy.DETERMINISTIC

        # 4. Default: Hermes agentic loop
        logger.info(
            "kernel_strategy_selected",
            strategy=ExecutionStrategy.HERMES_AGENT,
            reason="default_agentic",
            task_id=str(task.id),
        )
        return ExecutionStrategy.HERMES_AGENT

    # ── Execution dispatch ────────────────────────────────────────────────────

    async def execute(self, ctx: ExecutionContext) -> dict:
        """Execute a task using the strategy determined at plan time.

        Butler commits task state to PostgreSQL before calling any backend and
        verifies the checkpoint after. The kernel never allows a backend to
        commit state directly.

        Returns:
            dict with keys: content, actions, token_usage, duration_ms
        """
        logger.info(
            "kernel_execute_start",
            strategy=ctx.strategy,
            task_id=str(ctx.task.id),
            trace_id=ctx.trace_id,
        )

        match ctx.strategy:
            case ExecutionStrategy.DETERMINISTIC:
                return await self._execute_deterministic(ctx)
            case ExecutionStrategy.HERMES_AGENT:
                return await self._execute_hermes(ctx)
            case ExecutionStrategy.WORKFLOW_DAG:
                return await self._execute_workflow(ctx)
            case ExecutionStrategy.SUBAGENT:
                return await self._execute_subagent(ctx)
            case _:
                raise ValueError(f"Unknown execution strategy: {ctx.strategy}")

    async def execute_streaming(
        self, ctx: ExecutionContext
    ) -> AsyncGenerator["ButlerEvent", None]:
        """Execute with streaming — yields Butler canonical events.

        All events are normalized by EventNormalizer before being yielded.
        Thinking blocks are suppressed here; they never leave the kernel.
        """
        if ctx.strategy == ExecutionStrategy.HERMES_AGENT and self._hermes:
            async for event in self._hermes.run_streaming(ctx):
                yield event  # Already normalized by HermesAgentBackend
        else:
            # Non-streaming strategies yield a single final event
            result = await self.execute(ctx)
            from domain.events.schemas import StreamFinalEvent
            yield StreamFinalEvent(
                account_id=ctx.account_id,
                session_id=ctx.session_id,
                task_id=str(ctx.task.id),
                trace_id=ctx.trace_id,
                payload={
                    "input_tokens": result.get("input_tokens", 0),
                    "output_tokens": result.get("output_tokens", 0),
                    "cache_read_tokens": result.get("cache_read_tokens", 0),
                    "estimated_cost_usd": result.get("estimated_cost_usd", 0.0),
                    "duration_ms": result.get("duration_ms", 0),
                },
            )

    # ── Backend calls ─────────────────────────────────────────────────────────

    async def _execute_deterministic(self, ctx: ExecutionContext) -> dict:
        if not self._deterministic:
            logger.warning("deterministic_backend_missing", task_id=str(ctx.task.id))
            return {"content": "", "actions": [], "token_usage": {}, "duration_ms": 0}
        return await self._deterministic.execute(ctx)

    async def _execute_hermes(self, ctx: ExecutionContext) -> dict:
        if not self._hermes:
            raise RuntimeError(
                "HermesAgentBackend not wired into RuntimeKernel. "
                "Wire it in OrchestratorService.__init__ before using hermes_agent strategy."
            )
        return await self._hermes.run(ctx)

    async def _execute_workflow(self, ctx: ExecutionContext) -> dict:
        if not self._workflow:
            logger.warning("workflow_backend_missing", task_id=str(ctx.task.id))
            return {"content": "", "actions": [], "token_usage": {}, "duration_ms": 0}
        return await self._workflow.execute(ctx)

    async def _execute_subagent(self, ctx: ExecutionContext) -> dict:
        if not self._subagent:
            logger.warning("subagent_backend_missing", task_id=str(ctx.task.id))
            return {"content": "", "actions": [], "token_usage": {}, "duration_ms": 0}
        return await self._subagent.delegate(ctx)
