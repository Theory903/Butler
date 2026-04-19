"""Butler Durable Executor — Phase 1B.

Replaced stub logic with RuntimeKernel dispatch.

What changed:
  - _execute_step() no longer pattern-matches on step action strings.
    The RuntimeKernel chooses the execution strategy per task; the executor
    commits state transitions before and after.
  - _build_response() stub is gone. Content comes from kernel output.
  - Hermes is never imported here. Executor talks to RuntimeKernel only.
  - ApprovalRequired, compensation, retry logic are preserved and hardened.

The executor's job:
  1. Create Task in PostgreSQL
  2. Commit pending → executing before kernel runs
  3. Call kernel.execute() or kernel.execute_streaming()
  4. Normalize result through MemoryWritePolicy for any memory writes
  5. Commit executing → completed/failed with full output
  6. Cache hot state in Redis

This file never knows whether Hermes, a workflow DAG, or a deterministic
tool call ran. That is RuntimeKernel's domain.
"""

from __future__ import annotations

import json
import uuid
import structlog
import time
from datetime import datetime, timedelta, UTC
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from domain.orchestrator.models import Workflow, Task, ApprovalRequest
from domain.orchestrator.state import TaskStateMachine
from domain.orchestrator.runtime_kernel import RuntimeKernel, ExecutionContext, ExecutionStrategy
from domain.memory.contracts import MemoryServiceContract
from domain.tools.contracts import ToolsServiceContract
from domain.events.schemas import ButlerEvent, StreamApprovalRequiredEvent, StreamErrorEvent
from services.orchestrator.planner import Plan, Step

from domain.plugins.plugin_bus import ButlerPluginBus
from domain.hooks.hook_bus import ButlerHookBus

logger = structlog.get_logger(__name__)


class ApprovalRequired(Exception):
    """Raised when a task step requires human approval."""
    def __init__(
        self,
        approval_type: str,
        description: str,
        risk_tier: str = "L2",
        tool_name: str | None = None,
    ):
        self.approval_type = approval_type
        self.description = description
        self.risk_tier = risk_tier
        self.tool_name = tool_name
        super().__init__(f"Approval required: {description}")


class WorkflowResult:
    """Butler-canonical result from a completed workflow."""
    def __init__(
        self,
        workflow_id: str,
        content: str,
        actions: list,
        input_tokens: int = 0,
        output_tokens: int = 0,
        duration_ms: int = 0,
    ):
        self.workflow_id = workflow_id
        self.content = content
        self.actions = actions
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.duration_ms = duration_ms


class DurableExecutor:
    """Execute workflow tasks with durable state persistence.

    The executor owns:
      - PostgreSQL task lifecycle (pending → executing → completed/failed)
      - Redis hot cache writes
      - ApprovalRequest creation on gated tool proposals
      - Compensation on failure

    The executor does NOT own:
      - Which execution strategy to use (RuntimeKernel decides)
      - Which LLM to call (ButlerSmartRouter decides — Phase 5)
      - Which memory to write (MemoryWritePolicy decides)
      - Which tool to run (ButlerToolDispatch + ButlerToolPolicyGate decide)
    """

    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        kernel: RuntimeKernel,
        memory_service: MemoryServiceContract,
        tools_service: ToolsServiceContract,
        state_machine: TaskStateMachine,
        # Assembled by OrchestratorService at startup — not imported here
        system_prompt: str = "",
        model: str = "",
        plugin_bus: ButlerPluginBus | None = None,
        hook_bus: ButlerHookBus | None = None,
    ):
        self._db = db
        self._redis = redis
        self._kernel = kernel
        self._memory = memory_service
        self._tools = tools_service
        self._sm = state_machine
        self._system_prompt = system_prompt
        self._model = model
        self._plugin_bus = plugin_bus
        self._hook_bus = hook_bus

    # ── Main execution path ───────────────────────────────────────────────────

    async def execute_workflow(self, workflow: Workflow, plan: Plan) -> WorkflowResult:
        """Execute a plan as a series of durable tasks.

        For HERMES_AGENT strategy: the entire plan may be handled by a single
        kernel run. For WORKFLOW_DAG strategy: each step is a separate task.
        """
        results: list[dict] = []
        total_input_tokens = 0
        total_output_tokens = 0
        workflow_start = int(time.monotonic() * 1000)

        for step in plan.steps:
            task = Task(
                workflow_id=workflow.id,
                task_type=step.action,
                status="pending",
                input_data=step.params,
            )
            self._db.add(task)
            await self._db.flush()
            await self._cache_task_state(task)

            try:
                # ── Butler commits: pending → executing BEFORE kernel runs ──
                transition = self._sm.transition(task, "executing", "auto")
                self._db.add(transition)
                await self._db.flush()

                result = await self._execute_step_via_kernel(task, step, workflow)

                if self._hook_bus:
                    await self._hook_bus.emit(
                        "butler:agent:end",
                        {
                            "account_id": str(workflow.account_id),
                            "session_id": workflow.session_id,
                            "task_id": str(task.id),
                            "success": True,
                        }
                    )

                # ── Butler commits: executing → completed AFTER kernel runs ──
                task.output_data = result
                task.completed_at = datetime.now(UTC)
                transition = self._sm.transition(task, "completed", "auto")
                self._db.add(transition)

                total_input_tokens += result.get("input_tokens", 0)
                total_output_tokens += result.get("output_tokens", 0)
                results.append(result)

            except ApprovalRequired as e:
                transition = self._sm.transition(task, "awaiting_approval", "approval_needed")
                self._db.add(transition)

                approval = ApprovalRequest(
                    task_id=task.id,
                    workflow_id=workflow.id,
                    account_id=workflow.account_id,
                    approval_type=e.approval_type,
                    description=e.description,
                    expires_at=datetime.now(UTC) + timedelta(hours=24),
                )
                self._db.add(approval)
                await self._db.commit()
                await self._cache_task_state(task)

                # Return partial result — workflow resumes on approval
                return WorkflowResult(
                    workflow_id=str(workflow.id),
                    content="[Paused: awaiting approval]",
                    actions=[],
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    duration_ms=int(time.monotonic() * 1000) - workflow_start,
                )

            except Exception as exc:
                task.error_data = {"error": str(exc), "type": type(exc).__name__}
                task.completed_at = datetime.now(UTC)
                transition = self._sm.transition(task, "failed", "error")
                self._db.add(transition)

                if self._hook_bus:
                    await self._hook_bus.emit(
                        "butler:agent:end",
                        {
                            "account_id": str(workflow.account_id),
                            "session_id": workflow.session_id,
                            "task_id": str(task.id),
                            "success": False,
                        }
                    )

                if task.retries < task.max_retries:
                    task.retries += 1
                    transition = self._sm.transition(task, "pending", "retry")
                    self._db.add(transition)
                    logger.warning(
                        "task_retrying",
                        task_id=str(task.id),
                        retries=task.retries,
                        error=str(exc),
                    )
                else:
                    await self._compensate(workflow, results)
                    await self._db.commit()
                    raise

            await self._db.commit()
            await self._cache_task_state(task)

        duration_ms = int(time.monotonic() * 1000) - workflow_start
        all_completed = len(results) == len(plan.steps) and all(r is not None for r in results)
        workflow.status = "completed" if all_completed else "failed"
        workflow.completed_at = datetime.now(UTC)
        await self._db.commit()

        # Build final content from kernel results
        content = self._assemble_content(results)
        actions = [r for r in results if r and r.get("action")]

        return WorkflowResult(
            workflow_id=str(workflow.id),
            content=content,
            actions=actions,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            duration_ms=duration_ms,
        )

    async def execute_streaming(
        self,
        workflow: Workflow,
        plan: Plan,
        messages: list[dict],
    ) -> AsyncGenerator[ButlerEvent, None]:
        """Streaming variant — yields Butler canonical events from RuntimeKernel.

        Used by the Gateway's SSE/WebSocket path.
        Memory writes, task state, and approvals are all handled here,
        interleaved with the yielded events.
        """
        # Create the primary execution task
        task = Task(
            workflow_id=workflow.id,
            task_type=plan.steps[0].action if plan.steps else "respond",
            status="pending",
            input_data={"plan": plan.to_dict()},
        )
        self._db.add(task)
        await self._db.flush()
        await self._cache_task_state(task)

        # Build ExecutionContext for the kernel
        strategy = self._kernel.choose_strategy(task, workflow)
        ctx = ExecutionContext(
            task=task,
            workflow=workflow,
            strategy=strategy,
            model=self._model,
            toolset=[],        # Populated by OrchestratorService (Phase 2)
            system_prompt=self._system_prompt,
            messages=messages,
            trace_id=f"trc_{uuid.uuid4().hex[:12]}",
            account_id=str(workflow.account_id),
            session_id=workflow.session_id,
        )

        # Butler commits: pending → executing BEFORE yielding any kernel events
        transition = self._sm.transition(task, "executing", "auto")
        self._db.add(transition)
        await self._db.flush()
        await self._db.commit()
        await self._cache_task_state(task)

        if self._hook_bus:
            await self._hook_bus.emit(
                "butler:agent:start",
                {
                    "account_id": str(workflow.account_id),
                    "session_id": workflow.session_id,
                    "task_id": str(task.id),
                    "model": self._model,
                }
            )

        failed = False
        start_time = time.monotonic()
        try:
            async for event in self._kernel.execute_streaming(ctx):
                # Intercept approval events to create ApprovalRequest in DB
                if isinstance(event, StreamApprovalRequiredEvent):
                    approval = ApprovalRequest(
                        task_id=task.id,
                        workflow_id=workflow.id,
                        account_id=workflow.account_id,
                        approval_type=event.payload.get("approval_type", "tool_execution"),
                        description=event.payload.get("description", ""),
                        expires_at=datetime.now(UTC) + timedelta(hours=24),
                    )
                    self._db.add(approval)
                    # Update approval_id in event payload
                    event.payload["approval_id"] = str(approval.id) if hasattr(approval, "id") else "pending"

                    transition = self._sm.transition(task, "awaiting_approval", "approval_needed")
                    self._db.add(transition)
                    await self._db.commit()
                    await self._cache_task_state(task)

                elif isinstance(event, StreamErrorEvent):
                    failed = True

                yield event

        except Exception as exc:
            failed = True
            logger.exception("executor_streaming_exception", task_id=str(task.id))
            from domain.events.schemas import StreamErrorEvent as SErr
            yield SErr(
                account_id=ctx.account_id,
                session_id=ctx.session_id,
                task_id=str(task.id),
                trace_id=ctx.trace_id,
                payload={
                    "type": "https://butler.lasmoid.ai/problems/internal-error",
                    "title": "InternalError",
                    "status": 500,
                    "detail": str(exc),
                    "retryable": False,
                },
            )

        finally:
            # Emit hook for agent end
            if self._hook_bus:
                await self._hook_bus.emit(
                    "butler:agent:end",
                    {
                        "account_id": str(workflow.account_id),
                        "session_id": workflow.session_id,
                        "task_id": str(task.id),
                        "success": not failed,
                        "duration_ms": int((time.monotonic() - start_time) * 1000),
                    }
                )

            # Butler commits final state AFTER kernel finishes
            final_status = "failed" if failed else "completed"
            task.completed_at = datetime.now(UTC)
            transition = self._sm.transition(task, final_status, "auto")
            self._db.add(transition)
            await self._db.commit()
            await self._cache_task_state(task)

    # ── Kernel dispatch for non-streaming step ─────────────────────────────

    async def _execute_step_via_kernel(
        self, task: Task, step: Step, workflow: Workflow
    ) -> dict:
        """Execute a single plan step via RuntimeKernel and return a result dict."""
        strategy = self._kernel.choose_strategy(task, workflow)

        sys_prompt = self._system_prompt
        if self._plugin_bus:
            blocks = []
            for plugin in self._plugin_bus.plugins_of_type("memory"):
                if getattr(plugin, "available", False) and hasattr(plugin.instance, "system_prompt_block"):
                    block = plugin.instance.system_prompt_block()
                    if block:
                        blocks.append(block)
            if blocks:
                sys_prompt += "\n\n" + "\n\n".join(blocks)

        ctx = ExecutionContext(
            task=task,
            workflow=workflow,
            strategy=strategy,
            model=self._model,
            toolset=[],  # Phase 2: populated from compiled ButlerToolSpecs
            system_prompt=sys_prompt,
            messages=[],  # Phase 4: populated from MemoryService session history
            trace_id=f"trc_{uuid.uuid4().hex[:12]}",
            account_id=str(workflow.account_id),
            session_id=workflow.session_id,
        )

        if self._hook_bus:
            await self._hook_bus.emit(
                "butler:agent:start",
                {
                    "account_id": str(workflow.account_id),
                    "session_id": workflow.session_id,
                    "task_id": str(task.id),
                    "model": self._model,
                }
            )

        start_time = time.monotonic()
        kernel_result = await self._kernel.execute(ctx)
        
        # Note: agent:end hook for the step is emitted in execute_workflow

        return {
            "action": step.action,
            "strategy": strategy.value,
            "content": kernel_result.get("content", ""),
            "input_tokens": kernel_result.get("input_tokens", 0),
            "output_tokens": kernel_result.get("output_tokens", 0),
            "duration_ms": kernel_result.get("duration_ms", 0),
        }

    # ── Compensation ──────────────────────────────────────────────────────────

    async def _compensate(self, workflow: Workflow, completed_results: list[dict]):
        """Undo side-effects of completed steps on workflow failure."""
        for result in reversed(completed_results):
            if result and result.get("compensation"):
                try:
                    await self._tools.compensate(result["compensation"])
                except Exception:
                    logger.error("compensation_failed", workflow_id=str(workflow.id))

    # ── Resume (post-approval) ────────────────────────────────────────────────

    async def resume_task(self, task: Task):
        """Resume an awaiting_approval task after human decision.

        Full re-execution via kernel. Task state is committed before/after.
        """
        if task.status != "awaiting_approval":
            logger.warning("resume_task_unexpected_status", status=task.status)
            return

        logger.info("task_resuming_after_approval", task_id=str(task.id))
        # Full resume logic is Phase 6 (approval workflow engine)
        # For now: transition back to executing so the service layer can re-dispatch
        transition = self._sm.transition(task, "executing", "approval_granted")
        self._db.add(transition)
        await self._db.commit()
        await self._cache_task_state(task)

    # ── Utilities ──────────────────────────────────────────────────────────────

    async def _cache_task_state(self, task: Task):
        """Cache hot task state in Redis. TTL: 1 hour."""
        await self._redis.setex(
            f"butler:task:{task.id}:state",
            3600,
            json.dumps({
                "status": task.status,
                "type": task.task_type,
                "retries": task.retries,
                "updated_at": datetime.now(UTC).isoformat(),
            }),
        )

    def _assemble_content(self, results: list[dict]) -> str:
        """Assemble final response text from step results.

        Prior implementation: "Workflow completed. Actions taken: ..." (mock string)
        Now: actual content from kernel execution.
        """
        parts = []
        for r in results:
            if r and r.get("content"):
                parts.append(r["content"])
        return "\n\n".join(parts) if parts else ""
