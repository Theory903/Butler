"""Butler Durable Executor.

Durable workflow execution for Butler DAG-based orchestration.

Responsibilities:
- Lower plans into durable DAGs when needed
- Step workflow state through WorkflowEngine
- Execute ready nodes through RuntimeKernel
- Persist node outcomes and task transitions
- Suspend and resume on approvals/signals
- Provide streaming execution for direct task runs
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

import structlog
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.locks import LockManager
from core.observability import get_tracer
from domain.events.schemas import (
    ButlerEvent,
    StreamApprovalRequiredEvent,
    StreamErrorEvent,
)
from domain.memory.contracts import MemoryServiceContract
from domain.orchestrator.models import Task, Workflow, WorkflowEvent
from domain.orchestrator.runtime_kernel import (
    ExecutionContext,
    ExecutionMessage,
    RuntimeKernel,
)
from domain.orchestration.router import OperationRequest, OperationRouter, OperationType
from domain.orchestrator.state import TaskStateMachine
from domain.orchestrator.workflow_dag import PlanLowerer, WorkflowDAG
from domain.tools.contracts import ToolsServiceContract
from services.orchestrator.planner import Plan, Step
from services.workflow.engine import WorkflowEngine

logger = structlog.get_logger(__name__)


class ApprovalServiceContract(Protocol):
    """Contract for approval request creation."""

    async def create(
        self,
        db: AsyncSession,
        account_id: str,
        tool_name: str,
        description: str,
        task_id: str,
        workflow_id: str,
        approval_type: str,
    ) -> Any:
        """Create an approval request."""


class ApprovalRequired(Exception):  # noqa: N818
    """Raised when a workflow node requires explicit human approval."""

    def __init__(
        self,
        approval_type: str,
        description: str,
        risk_tier: str = "L2",
        tool_name: str | None = None,
    ) -> None:
        self.approval_type = approval_type
        self.description = description
        self.risk_tier = risk_tier
        self.tool_name = tool_name
        super().__init__(f"Approval required: {description}")


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    """Canonical result from a completed workflow execution."""

    workflow_id: str
    content: str
    actions: Sequence[dict[str, object]] = field(default_factory=tuple)
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    metadata: dict[str, object] = field(default_factory=dict)


class DurableExecutor:
    """Execute Butler workflows with durable checkpoint-aware semantics."""

    def __init__(
        self,
        *,
        db: AsyncSession,
        redis: Redis,
        kernel: RuntimeKernel,
        memory_service: MemoryServiceContract,
        tools_service: ToolsServiceContract,
        state_machine: TaskStateMachine,
        approval_service: ApprovalServiceContract | None = None,
        system_prompt: str = "",
        model: str = "",
        lock_manager: LockManager | None = None,
        blender: object | None = None,
        smart_router: object | None = None,
        operation_router: OperationRouter | None = None,
        feature_service: object | None = None,
        redaction_service: object | None = None,
        safety_service: object | None = None,
    ) -> None:
        self._db = db
        self._redis = redis
        self._kernel = kernel
        self._memory = memory_service
        self._tools = tools_service
        self._sm = state_machine
        self._approval_service = approval_service
        self._system_prompt = system_prompt
        self._model = model
        self._locks = lock_manager
        self._blender = blender
        self._router = smart_router
        self._operation_router = operation_router
        self._features = feature_service
        self._redactor = redaction_service
        self._safety = safety_service
        self._tracer = get_tracer()

    async def execute_workflow(self, workflow: Workflow, plan: Plan) -> WorkflowResult:
        """Execute a durable workflow plan through the DAG engine."""
        workflow_start_ms = int(time.monotonic() * 1000)

        if not workflow.plan_schema:
            dag = PlanLowerer.lower(plan)
            workflow.plan_schema = dag.model_dump()
            await self._db.flush()
            await self._db.commit()

        engine = WorkflowEngine(self._db, self._redis, self._sm)
        await engine.step_workflow(str(workflow.id))
        await self._db.commit()

        last_content = ""
        max_iterations = 50
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            await self._db.refresh(workflow)

            if workflow.status != "active":
                break

            state_snapshot = workflow.state_snapshot or {}
            running_nodes = state_snapshot.get("running_nodes", {}) or {}
            progressed = False
            retry_scheduled = False
            terminal_failure = False

            for node_id, node_data in list(running_nodes.items()):
                node_task_id = (
                    node_data.get("task_id") if isinstance(node_data, dict) else node_data
                )

                if node_task_id in {
                    "awaiting_approval",
                    "awaiting_signal",
                    "awaiting_wait",
                }:
                    continue

                task = await self._load_node_task(node_task_id=node_task_id)
                if task is None:
                    logger.warning(
                        "durable_executor_task_missing",
                        workflow_id=str(workflow.id),
                        node_id=node_id,
                        task_id=node_task_id,
                    )
                    continue

                if task.status != "pending":
                    continue

                progressed = True

                try:
                    result = await self._load_or_execute_node_result(
                        workflow=workflow,
                        task=task,
                        node_id=node_id,
                    )

                    if result.content:
                        last_content = result.content

                    task.output_data = {
                        "content": result.content,
                        "actions": list(result.actions),
                        "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens,
                        "duration_ms": result.duration_ms,
                        "metadata": dict(result.metadata),
                    }
                    task.completed_at = datetime.now(UTC)

                    if task.status != "completed":
                        transition = self._sm.transition(task, "completed", "auto")
                        self._db.add(transition)

                    await engine.complete_task_node(
                        str(workflow.id),
                        node_id,
                        str(task.id),
                        task.output_data,
                    )
                    await self._db.commit()

                except ApprovalRequired as exc:
                    await self._handle_approval_required(
                        task=task,
                        workflow=workflow,
                        error=exc,
                    )
                    await self._db.commit()
                    return WorkflowResult(
                        workflow_id=str(workflow.id),
                        content=last_content,
                        actions=(),
                        duration_ms=int(time.monotonic() * 1000) - workflow_start_ms,
                        metadata={
                            "status": "awaiting_approval",
                            "suspended": True,
                            "suspension_reason": "awaiting_approval",
                        },
                    )

                except Exception as exc:
                    logger.exception(
                        "durable_executor_task_failure",
                        workflow_id=str(workflow.id),
                        task_id=str(task.id),
                        node_id=node_id,
                    )
                    terminal_failure = await self._handle_task_failure(
                        task=task,
                        workflow=workflow,
                        exc=exc,
                    )
                    await self._db.commit()

                    if terminal_failure:
                        break

                    retry_scheduled = True
                    break

            await self._db.refresh(workflow)

            if terminal_failure or workflow.status != "active":
                break

            if retry_scheduled:
                continue

            if not progressed:
                stepped = await engine.step_workflow(str(workflow.id))
                await self._db.commit()

                if not stepped:
                    state_snapshot = workflow.state_snapshot or {}
                    running_nodes = state_snapshot.get("running_nodes", {}) or {}
                    pending_states = {
                        str(value.get("task_id") if isinstance(value, dict) else value)
                        for value in running_nodes.values()
                    }

                    if any(state.startswith("awaiting_") for state in pending_states):
                        logger.info(
                            "durable_executor_workflow_suspended",
                            workflow_id=str(workflow.id),
                            running_nodes=running_nodes,
                        )
                        break

                    logger.info(
                        "durable_executor_no_further_progress",
                        workflow_id=str(workflow.id),
                    )
                    break

                await asyncio.sleep(0.1)

        await self._db.refresh(workflow)

        duration_ms = int(time.monotonic() * 1000) - workflow_start_ms
        metadata: dict[str, object] = {}

        if workflow.status == "failed":
            metadata["error"] = "workflow_failed"
            content = "Butler could not complete the workflow."
        else:
            content = last_content or "[Durable workflow completed]"

        return WorkflowResult(
            workflow_id=str(workflow.id),
            content=content,
            actions=(),
            duration_ms=duration_ms,
            metadata=metadata,
        )

    async def execute_streaming(
        self,
        *,
        workflow: Workflow,
        task: Task,
        messages: Sequence[ExecutionMessage],
    ) -> AsyncGenerator[ButlerEvent]:
        """Stream execution events for a single task through RuntimeKernel."""
        await self._cache_task_state(task)

        session_lock = f"session:{workflow.session_id}"
        lock_context = (
            self._locks.get_lock(session_lock, ttl=60)
            if self._locks is not None
            else contextlib.nullcontext()
        )

        async with lock_context:
            strategy = self._kernel.choose_strategy(task, workflow)
            trace_id = self._tracer.get_current_trace_id() or f"trc_{uuid.uuid4().hex[:12]}"
            context = ExecutionContext(
                task=task,
                workflow=workflow,
                strategy=strategy,
                model=self._model,
                toolset=self._extract_toolset(),
                system_prompt=self._system_prompt,
                messages=messages,
                trace_id=trace_id,
                account_id=str(workflow.account_id),
                session_id=workflow.session_id,
            )

            transition = self._sm.transition(task, "executing", "auto")
            self._db.add(transition)
            await self._db.flush()
            await self._db.commit()
            await self._cache_task_state(task)

        failed = False

        try:
            async for event in self._kernel.execute_streaming(context):
                if isinstance(event, StreamApprovalRequiredEvent):
                    await self._handle_streaming_approval(
                        task=task,
                        workflow=workflow,
                        event=event,
                    )
                elif isinstance(event, StreamErrorEvent):
                    failed = True
                yield event

        except Exception:
            failed = True
            logger.exception(
                "durable_executor_streaming_exception",
                workflow_id=str(workflow.id),
                task_id=str(task.id),
            )
            yield StreamErrorEvent(
                account_id=str(workflow.account_id),
                session_id=workflow.session_id,
                task_id=str(task.id),
                trace_id=(self._tracer.get_current_trace_id() or f"trc_{uuid.uuid4().hex[:12]}"),
                payload={
                    "title": "ExecutionError",
                    "status": 500,
                    "detail": "Butler could not complete the streamed execution.",
                },
            )

        finally:
            if task.status == "executing":
                final_status = "failed" if failed else "completed"
                task.completed_at = datetime.now(UTC)
                transition = self._sm.transition(task, final_status, "auto")
                self._db.add(transition)
                await self._db.commit()
            else:
                await self._db.commit()

            await self._cache_task_state(task)

    async def _load_node_task(self, *, node_task_id: object) -> Task | None:
        """Load a workflow node task safely from its identifier."""
        try:
            task_uuid = uuid.UUID(str(node_task_id))
        except (TypeError, ValueError):
            logger.error(
                "durable_executor_invalid_task_id",
                task_id=node_task_id,
            )
            return None

        return await self._db.get(Task, task_uuid)

    async def _load_or_execute_node_result(
        self,
        *,
        workflow: Workflow,
        task: Task,
        node_id: str,
    ) -> WorkflowResult:
        """Replay a memoized node result or execute the node through the kernel."""
        history = await self._db.execute(
            select(WorkflowEvent)
            .where(
                WorkflowEvent.workflow_id == workflow.id,
                WorkflowEvent.node_id == node_id,
                WorkflowEvent.event_type == "node_end",
            )
            .order_by(WorkflowEvent.created_at.desc())
        )
        memoized_event = history.scalars().first()
        if memoized_event is not None:
            logger.info(
                "durable_executor_replay_node",
                workflow_id=str(workflow.id),
                node_id=node_id,
            )
            return self._workflow_result_from_payload(
                workflow_id=str(workflow.id),
                payload=memoized_event.output_data or {},
            )

        transition = self._sm.transition(task, "executing", "auto")
        self._db.add(transition)
        await self._db.flush()

        dag = WorkflowDAG.model_validate(workflow.plan_schema)
        node = next((item for item in dag.nodes if item.id == node_id), None)
        if node is None:
            raise ValueError(f"Node {node_id!r} not found in workflow DAG")

        step = Step(action=node.tool_name or "respond", params=node.inputs)
        result_payload = await self._execute_step_via_kernel(
            task=task,
            step=step,
            workflow=workflow,
            node_id=node_id,
        )
        return self._workflow_result_from_payload(
            workflow_id=str(workflow.id),
            payload=result_payload,
        )

    async def _handle_approval_required(
        self,
        *,
        task: Task,
        workflow: Workflow,
        error: ApprovalRequired,
    ) -> Any:
        """Suspend a task and create an approval request."""
        if task.status != "executing":
            transition = self._sm.transition(task, "executing", "approval_guard")
            self._db.add(transition)
            await self._db.flush()

        transition = self._sm.transition(task, "awaiting_approval", "approval_needed")
        self._db.add(transition)

        if self._approval_service is None:
            raise RuntimeError("Approval is required but no approval service is configured.")

        request = await self._approval_service.create(
            self._db,
            str(workflow.account_id),
            error.tool_name or task.tool_name or "unknown",
            error.description,
            str(task.id),
            str(workflow.id),
            approval_type=error.approval_type,
        )
        await self._db.flush()
        return request

    async def suspend_for_approval(
        self,
        *,
        task: Task,
        workflow: Workflow,
        error: ApprovalRequired,
    ) -> Any:
        """Public boundary for direct graph paths that need durable approval."""
        request = await self._handle_approval_required(
            task=task,
            workflow=workflow,
            error=error,
        )
        await self._db.commit()
        await self._cache_task_state(task)
        return request

    async def _handle_task_failure(
        self,
        *,
        task: Task,
        workflow: Workflow,
        exc: Exception,
    ) -> bool:
        """Move a task through failure and retry handling.

        Returns True when the workflow should be treated as terminally failed.
        """
        task.error_data = {
            "error": str(exc),
            "type": type(exc).__name__,
        }
        task.completed_at = datetime.now(UTC)

        transition_failed = self._sm.transition(task, "failed", "error")
        self._db.add(transition_failed)

        if task.retries < task.max_retries:
            task.retries += 1
            transition_retry = self._sm.transition(task, "pending", "retry")
            self._db.add(transition_retry)
            logger.warning(
                "durable_executor_task_retrying",
                task_id=str(task.id),
                retries=task.retries,
            )
            await self._db.flush()
            return False

        workflow.status = "failed"
        logger.error(
            "durable_executor_task_failed_max_retries",
            task_id=str(task.id),
            workflow_id=str(workflow.id),
        )
        await self._db.flush()
        return True

    async def _handle_streaming_approval(
        self,
        *,
        task: Task,
        workflow: Workflow,
        event: StreamApprovalRequiredEvent,
    ) -> None:
        """Create approval state for a streaming task."""
        if self._approval_service is None:
            raise RuntimeError(
                "Streaming approval requested but no approval service is configured."
            )

        request = await self._approval_service.create(
            self._db,
            str(workflow.account_id),
            str(event.payload.get("tool_name", "unknown")),
            str(event.payload.get("description", "")),
            str(task.id),
            str(workflow.id),
            approval_type=str(event.payload.get("approval_type", "tool_execution")),
        )
        event.payload["approval_id"] = str(request.id)

        if task.status == "executing":
            transition = self._sm.transition(task, "awaiting_approval", "approval_needed")
            self._db.add(transition)
            await self._db.flush()

    async def _execute_step_via_kernel(
        self,
        *,
        task: Task,
        step: Step,
        workflow: Workflow,
        node_id: str,
    ) -> dict[str, object]:
        """Execute one workflow node through the RuntimeKernel with router admission check."""
        # Check tool operation admission through router
        if self._operation_router is not None and step.action != "respond":
            from domain.orchestration.router import AdmissionDecision

            tenant_id = getattr(workflow, 'tenant_id', None) or str(workflow.account_id)
            operation_request = OperationRequest(
                operation_type=OperationType.TOOL_CALL,
                tenant_id=tenant_id,
                account_id=str(workflow.account_id),
                user_id=None,
                tool_name=step.action,
                risk_tier=None,
                estimated_cost=None,
            )

            _, admission = self._operation_router.route(operation_request)
            if admission.decision != AdmissionDecision.ALLOW:
                raise ApprovalRequired(
                    approval_type="router_denied",
                    description=admission.reason,
                    tool_name=step.action,
                )

        strategy = self._kernel.choose_strategy(task, workflow)
        trace_id = self._tracer.get_current_trace_id() or f"trc_{uuid.uuid4().hex[:12]}"
        idempotency_key = f"{workflow.session_id}:{workflow.id}:{node_id}"

        task.idempotency_key = idempotency_key

        node_message = self._resolve_step_message(step)
        messages = [
            ExecutionMessage(
                role="user",
                content=node_message,
            )
        ]

        tenant_id = getattr(workflow, 'tenant_id', None) or str(workflow.account_id)
        context = ExecutionContext(
            task=task,
            workflow=workflow,
            strategy=strategy,
            model=self._model,
            toolset=self._extract_toolset(),
            system_prompt=self._system_prompt,
            messages=messages,
            trace_id=trace_id,
            account_id=str(workflow.account_id),
            session_id=workflow.session_id,
            tenant_id=tenant_id,
        )

        with self._tracer.span(
            "butler.executor.execute_step",
            attrs={
                "tool": step.action,
                "idempotency_key": idempotency_key,
                "node_id": node_id,
            },
        ):
            return await self._kernel.execute(context)

    async def resume_task(self, task: Task) -> None:
        """Resume a task suspended on approval."""
        if task.status != "awaiting_approval":
            return

        workflow = await self._db.get(Workflow, task.workflow_id)
        if workflow is None:
            return

        logger.info(
            "durable_executor_resuming_task",
            workflow_id=str(workflow.id),
            task_id=str(task.id),
        )

        transition = self._sm.transition(task, "executing", "approval_granted")
        self._db.add(transition)

        engine = WorkflowEngine(self._db, self._redis, self._sm)
        await engine.resolve_signal(
            str(workflow.id),
            "approval_decision",
            {
                "decision": "approved",
                "task_id": str(task.id),
            },
        )
        await self._db.commit()
        await self._cache_task_state(task)

    async def _cache_task_state(self, task: Task) -> None:
        """Cache hot task state in Redis for fast reads."""
        # Use tenant-scoped key if task has tenant_id, otherwise fallback to legacy format
        tenant_id = getattr(task, 'tenant_id', None)
        if tenant_id:
            from services.tenant.namespace import get_tenant_namespace
            namespace = get_tenant_namespace(tenant_id)
            key = f"{namespace.prefix}:task:{task.id}:state"
        else:
            # Fallback to legacy format for tasks without tenant_id
            key = f"butler:task:{task.id}:state"
        await self._redis.setex(
            key,
            3600,
            json.dumps(
                {
                    "status": task.status,
                    "type": task.task_type,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ),
        )

    def _extract_toolset(self) -> list[object]:
        compiled_specs = getattr(self._tools, "_specs", {})
        if isinstance(compiled_specs, dict):
            return list(compiled_specs.values())
        return []

    def _resolve_step_message(self, step: Step) -> str:
        params = step.params

        if isinstance(params, str):
            return params

        if isinstance(params, dict):
            query = params.get("query")
            if isinstance(query, str) and query:
                return query

            message = params.get("message")
            if isinstance(message, str) and message:
                return message

        return str(params)

    def _workflow_result_from_payload(
        self,
        *,
        workflow_id: str,
        payload: dict[str, object],
    ) -> WorkflowResult:
        raw_actions = payload.get("actions", [])
        actions: tuple[dict[str, object], ...]
        if isinstance(raw_actions, list):
            actions = tuple(item for item in raw_actions if isinstance(item, dict))
        else:
            actions = ()

        raw_metadata = payload.get("metadata", {})
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}

        return WorkflowResult(
            workflow_id=workflow_id,
            content=str(payload.get("content", "") or ""),
            actions=actions,
            input_tokens=int(payload.get("input_tokens", 0) or 0),
            output_tokens=int(payload.get("output_tokens", 0) or 0),
            duration_ms=int(payload.get("duration_ms", 0) or 0),
            metadata=metadata,
        )
