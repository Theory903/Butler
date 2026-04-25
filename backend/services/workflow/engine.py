"""Butler Workflow Engine — durable workflow runtime core.

Production goals:
- single-worker ownership per workflow step via PostgreSQL row lock
- deterministic checkpoint state in workflow.state_snapshot
- durable event log in workflow_events
- durable external signal persistence via workflow_signals + Redis Streams
- safe suspension/resume for TASK / WAIT / SIGNAL_WAIT / APPROVAL
- controlled, explicit handling of PARALLEL / MAP until full branch scheduling is implemented
"""

from __future__ import annotations

import copy
import json
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from domain.orchestrator.models import Task, Workflow, WorkflowEvent, WorkflowSignal
from domain.orchestrator.state import TaskStateMachine
from domain.orchestrator.workflow_dag import DAGNode, NodeKind, WorkflowDAG

UTC = UTC
logger = structlog.get_logger(__name__)

# Redis stream settings
_SIGNAL_STREAM_PREFIX = "butler:workflow:signals:"
_SIGNAL_GROUP_PREFIX = "workflow-engine:"
_SIGNAL_BLOCK_MS = 5_000
_SIGNAL_COUNT = 20

# Node lifecycle values stored inside checkpoint JSON
NODE_PENDING = "pending"
NODE_RUNNING = "running"
NODE_SUSPENDED = "suspended"
NODE_COMPLETED = "completed"
NODE_FAILED = "failed"

# Optional heartbeat / safety for future stale-task reclamation
TASK_STALE_AFTER = timedelta(minutes=15)


@dataclass(frozen=True, slots=True)
class StepResult:
    """Outcome of processing a workflow node."""

    suspending: bool
    next_node_id: str | None
    reason: str = ""


class WorkflowEngine:
    """Durable engine for executing Butler Workflow DAGs.

    Invariants:
    - only one worker can advance one workflow row at a time
    - every node transition is event-logged before leaving the step
    - suspended nodes resume only from explicit task completion or signal delivery
    - this engine is transaction-participating: it flushes state, callers own commits
    """

    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        state_machine: TaskStateMachine,
        worker_id: str | None = None,
    ) -> None:
        self._db = db
        self._redis = redis
        self._sm = state_machine
        self._worker_id = worker_id or f"wf-worker-{uuid.uuid4().hex[:8]}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def step_workflow(self, workflow_id: str | uuid.UUID) -> bool:
        """Advance one workflow as far as possible without crossing a suspension boundary.

        Returns:
            True if state changed, else False.
        """
        workflow_uuid = self._coerce_uuid(workflow_id)

        try:
            async with self._lock_workflow(workflow_uuid) as workflow:
                if workflow is None or workflow.status != "active":
                    return False

                dag = self._load_dag(workflow)
                state = self._normalize_state(workflow.state_snapshot, dag)
                workflow.state_snapshot = copy.deepcopy(state)

                modified = False

                while True:
                    current_node_id = state.get("current_node")

                    if not current_node_id:
                        if workflow.status == "active":
                            workflow.status = "completed"
                            workflow.completed_at = self._now()
                            await self._log_event(
                                workflow.id,
                                "workflow_completed",
                                None,
                                output_data={"reason": "no_more_nodes"},
                            )
                            modified = True
                        break

                    node = self._get_node(dag, current_node_id)
                    if node is None:
                        workflow.status = "failed"
                        workflow.completed_at = self._now()
                        await self._log_event(
                            workflow.id,
                            "workflow_failed",
                            current_node_id,
                            error_data={"error": "node_not_found"},
                        )
                        modified = True
                        break

                    node_state = self._get_node_state(state, node.id)

                    if node_state["status"] == NODE_RUNNING:
                        logger.info(
                            "workflow_node_already_running",
                            workflow_id=str(workflow.id),
                            node_id=node.id,
                            runtime=node_state,
                        )
                        break

                    if node_state["status"] == NODE_SUSPENDED:
                        logger.info(
                            "workflow_node_suspended",
                            workflow_id=str(workflow.id),
                            node_id=node.id,
                            runtime=node_state,
                        )
                        break

                    if node_state["status"] == NODE_COMPLETED:
                        next_node_id = self._resolve_next_after_completed(node, state)
                        if next_node_id == node.id:
                            workflow.status = "failed"
                            workflow.completed_at = self._now()
                            await self._log_event(
                                workflow.id,
                                "workflow_failed",
                                node.id,
                                error_data={"error": "self_loop_detected"},
                            )
                            modified = True
                            break

                        state["current_node"] = next_node_id
                        modified = True
                        continue

                    logger.info(
                        "workflow_processing_node",
                        workflow_id=str(workflow.id),
                        node_id=node.id,
                        node_kind=node.kind.value,
                    )
                    result = await self._process_node(workflow, dag, node, state)
                    workflow.state_snapshot = copy.deepcopy(state)
                    await self._db.flush()
                    modified = True

                    if result.suspending:
                        break

                    state["current_node"] = result.next_node_id

                    if result.next_node_id is None and workflow.status == "active":
                        workflow.status = "completed"
                        workflow.completed_at = self._now()
                        await self._log_event(
                            workflow.id,
                            "workflow_completed",
                            node.id,
                            output_data={"reason": "terminal_transition"},
                        )
                        break

                workflow.state_snapshot = copy.deepcopy(state)
                await self._db.flush()
                return modified

        except Exception:
            await self._db.rollback()
            logger.exception("workflow_step_failed", workflow_id=str(workflow_uuid))
            raise

    async def complete_task_node(
        self,
        workflow_id: str | uuid.UUID,
        node_id: str,
        task_id: str | uuid.UUID,
        output: Any,
        succeeded: bool = True,
        error: dict[str, Any] | None = None,
    ) -> None:
        """Complete a TASK-backed node from the task runner."""
        workflow_uuid = self._coerce_uuid(workflow_id)
        task_uuid = self._coerce_uuid(task_id)

        try:
            async with self._lock_workflow(workflow_uuid) as workflow:
                if workflow is None:
                    return

                dag = self._load_dag(workflow)
                state = self._normalize_state(workflow.state_snapshot, dag)
                node = self._get_node(dag, node_id)
                if node is None:
                    raise ValueError(f"Unknown node_id={node_id}")

                task = await self._db.get(Task, task_uuid)
                if task is None:
                    raise ValueError(f"Unknown task_id={task_uuid}")

                running = state["running_nodes"].get(node_id)
                if not running:
                    raise ValueError(f"Node {node_id} is not running")

                expected_task_id = running.get("task_id")
                if expected_task_id != str(task_uuid):
                    raise ValueError(
                        f"Task mismatch for node {node_id}: expected {expected_task_id}, got {task_uuid}"
                    )

                if succeeded:
                    self._mark_node_completed(state, node_id, output=output)
                    if task.status not in {"completed", "failed"}:
                        transition = self._sm.transition(task, "completed", "dag_complete")
                        self._db.add(transition)

                    await self._log_event(
                        workflow.id,
                        "node_end",
                        node_id,
                        output_data=output,
                    )
                    state["current_node"] = self._resolve_next_after_completed(node, state)
                else:
                    self._mark_node_failed(
                        state,
                        node_id,
                        error=error or {"error": "task_failed"},
                    )
                    if task.status not in {"completed", "failed"}:
                        transition = self._sm.transition(task, "failed", "dag_fail")
                        self._db.add(transition)

                    workflow.status = "failed"
                    workflow.completed_at = self._now()
                    await self._log_event(
                        workflow.id,
                        "node_failed",
                        node_id,
                        error_data=error or {},
                    )
                    state["current_node"] = None

                workflow.state_snapshot = copy.deepcopy(state)
                await self._db.flush()

            if succeeded:
                await self.step_workflow(workflow_uuid)

        except Exception:
            await self._db.rollback()
            logger.exception(
                "complete_task_node_failed",
                workflow_id=str(workflow_uuid),
                node_id=node_id,
            )
            raise

    async def resolve_signal(
        self,
        workflow_id: str | uuid.UUID,
        signal_name: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> None:
        """Persist a signal to DB and publish it to the workflow Redis stream.

        Note:
            Current WorkflowSignal schema does not support idempotency_key.
            This parameter is accepted for forward compatibility only.
        """
        del idempotency_key

        workflow_uuid = self._coerce_uuid(workflow_id)

        try:
            signal = WorkflowSignal(
                workflow_id=workflow_uuid,
                signal_name=signal_name,
                status="pending",
                payload=payload,
                created_at=self._now(),
            )
            self._db.add(signal)
            await self._db.flush()

            stream_key = self._signal_stream_key(workflow_uuid)
            await self._redis.xadd(
                stream_key,
                {
                    "workflow_id": str(workflow_uuid),
                    "signal_name": signal_name,
                    "payload": self._json(payload),
                    "signal_id": str(signal.id),
                },
                maxlen=10_000,
                approximate=True,
            )
            await self._db.flush()

        except IntegrityError:
            await self._db.rollback()
            logger.info(
                "workflow_signal_duplicate_ignored",
                workflow_id=str(workflow_uuid),
                signal_name=signal_name,
            )
        except Exception:
            await self._db.rollback()
            logger.exception(
                "resolve_signal_failed",
                workflow_id=str(workflow_uuid),
                signal_name=signal_name,
            )
            raise

    async def consume_signals_forever(self, workflow_id: str | uuid.UUID) -> None:
        """Background loop for one workflow signal stream."""
        workflow_uuid = self._coerce_uuid(workflow_id)
        stream_key = self._signal_stream_key(workflow_uuid)
        group_name = self._signal_group_name(workflow_uuid)

        await self._ensure_stream_group(stream_key, group_name)

        while True:
            response = await self._redis.xreadgroup(
                group_name,
                self._worker_id,
                {stream_key: ">"},
                count=_SIGNAL_COUNT,
                block=_SIGNAL_BLOCK_MS,
            )

            if not response:
                continue

            for _, entries in response:
                for msg_id, fields in entries:
                    try:
                        await self._apply_signal_message(workflow_uuid, fields)
                        await self._redis.xack(stream_key, group_name, msg_id)
                    except Exception:
                        logger.exception(
                            "workflow_signal_apply_failed",
                            workflow_id=str(workflow_uuid),
                            redis_message_id=self._decode_redis_value(msg_id),
                        )

    # ------------------------------------------------------------------
    # Core node execution
    # ------------------------------------------------------------------

    async def _process_node(
        self,
        workflow: Workflow,
        dag: WorkflowDAG,
        node: DAGNode,
        state: dict[str, Any],
    ) -> StepResult:
        await self._log_event(
            workflow.id,
            "node_start",
            node.id,
            input_data=getattr(node, "inputs", None),
        )

        if node.kind == NodeKind.TASK:
            return await self._start_task_node(workflow, node, state)

        if node.kind == NodeKind.CHOICE:
            next_id = self._evaluate_choice(node, state)
            self._mark_node_completed(state, node.id, output={"next": next_id})
            await self._log_event(
                workflow.id,
                "node_end",
                node.id,
                output_data={"next": next_id},
            )
            return StepResult(suspending=False, next_node_id=next_id)

        if node.kind == NodeKind.PASS:
            self._mark_node_completed(state, node.id, output={})
            await self._log_event(workflow.id, "node_end", node.id, output_data={})
            return StepResult(
                suspending=False,
                next_node_id=getattr(node, "next", None),
            )

        if node.kind in {NodeKind.WAIT, NodeKind.SIGNAL_WAIT, NodeKind.APPROVAL}:
            self._mark_node_suspended(
                state,
                node.id,
                suspend_type=node.kind.value,
                meta={
                    "next": getattr(node, "next", None),
                    "signal_name": getattr(node, "signal_name", None),
                    "approval_kind": getattr(node, "approval_kind", None),
                },
            )
            await self._log_event(
                workflow.id,
                "node_suspended",
                node.id,
                output_data={"reason": node.kind.value},
            )
            return StepResult(
                suspending=True,
                next_node_id=None,
                reason=node.kind.value,
            )

        if node.kind == NodeKind.PARALLEL:
            # Explicitly gated until branch scheduler is fully implemented.
            self._mark_node_failed(
                state,
                node.id,
                error={"error": "parallel_not_yet_fully_supported"},
            )
            workflow.status = "failed"
            workflow.completed_at = self._now()
            await self._log_event(
                workflow.id,
                "node_failed",
                node.id,
                error_data={"error": "parallel_not_yet_fully_supported"},
            )
            return StepResult(suspending=False, next_node_id=None)

        if node.kind == NodeKind.MAP:
            # Explicitly gated until iterator scheduling is fully implemented.
            self._mark_node_failed(
                state,
                node.id,
                error={"error": "map_not_yet_fully_supported"},
            )
            workflow.status = "failed"
            workflow.completed_at = self._now()
            await self._log_event(
                workflow.id,
                "node_failed",
                node.id,
                error_data={"error": "map_not_yet_fully_supported"},
            )
            return StepResult(suspending=False, next_node_id=None)

        if node.kind == NodeKind.SUCCESS:
            self._mark_node_completed(state, node.id, output={"status": "completed"})
            workflow.status = "completed"
            workflow.completed_at = self._now()
            await self._log_event(
                workflow.id,
                "node_end",
                node.id,
                output_data={"status": "completed"},
            )
            return StepResult(suspending=False, next_node_id=None)

        if node.kind == NodeKind.FAIL:
            self._mark_node_failed(state, node.id, error={"status": "failed"})
            workflow.status = "failed"
            workflow.completed_at = self._now()
            await self._log_event(
                workflow.id,
                "node_failed",
                node.id,
                error_data={"status": "failed"},
            )
            return StepResult(suspending=False, next_node_id=None)

        raise ValueError(f"Unsupported node kind: {node.kind!r}")

    async def _start_task_node(
        self,
        workflow: Workflow,
        node: DAGNode,
        state: dict[str, Any],
    ) -> StepResult:
        task = Task(
            workflow_id=workflow.id,
            task_type=getattr(node, "tool_name", None) or "execution",
            status="pending",
            tool_name=getattr(node, "tool_name", None),
            input_data=getattr(node, "inputs", None),
            version=workflow.version,
        )
        self._db.add(task)
        await self._db.flush()

        self._mark_node_running(
            state,
            node.id,
            kind="task",
            meta={
                "task_id": str(task.id),
                "next": getattr(node, "next", None),
            },
        )
        return StepResult(suspending=True, next_node_id=None, reason="task_started")

    # ------------------------------------------------------------------
    # Signal application
    # ------------------------------------------------------------------

    async def _apply_signal_message(
        self,
        workflow_id: uuid.UUID,
        fields: dict[str, Any],
    ) -> None:
        signal_name = self._decode_redis_value(fields.get("signal_name"))
        signal_id_raw = self._decode_redis_value(fields.get("signal_id"))
        payload = self._parse_json(fields.get("payload"))

        async with self._lock_workflow(workflow_id) as workflow:
            if workflow is None or workflow.status != "active":
                return

            dag = self._load_dag(workflow)
            state = self._normalize_state(workflow.state_snapshot, dag)
            progressed = False

            for node_id, node_runtime in list(state["suspended_nodes"].items()):
                runtime_kind = node_runtime.get("kind")
                if runtime_kind not in {"signal_wait", "approval", "wait"}:
                    continue

                expected_name = node_runtime.get("signal_name")
                if expected_name and expected_name != signal_name:
                    continue

                node = self._get_node(dag, node_id)
                if node is None:
                    continue

                self._mark_node_completed(
                    state,
                    node_id,
                    output={
                        "signal_name": signal_name,
                        "payload": payload,
                    },
                )
                await self._log_event(
                    workflow.id,
                    "node_resumed",
                    node_id,
                    output_data={
                        "signal_name": signal_name,
                        "payload": payload,
                    },
                )

                state["current_node"] = self._resolve_next_after_completed(node, state)
                progressed = True

                if signal_id_raw:
                    signal = await self._db.get(
                        WorkflowSignal,
                        self._coerce_uuid(signal_id_raw),
                    )
                    if signal is not None:
                        signal.status = "consumed"
                        signal.consumed_at = self._now()

                break

            workflow.state_snapshot = copy.deepcopy(state)
            await self._db.flush()

        if progressed:
            await self.step_workflow(workflow_id)

    # ------------------------------------------------------------------
    # Locking / DB framing
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def _lock_workflow(self, workflow_id: uuid.UUID):
        """Acquire row-level ownership for one workflow.

        Uses FOR UPDATE SKIP LOCKED so only one worker advances one workflow row
        at a time.
        """
        stmt = select(Workflow).where(Workflow.id == workflow_id).with_for_update(skip_locked=True)
        result = await self._db.execute(stmt)
        workflow = result.scalar_one_or_none()

        if workflow is not None:
            _ = workflow.plan_schema
            _ = workflow.state_snapshot

        try:
            yield workflow
        finally:
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _ensure_stream_group(self, stream_key: str, group_name: str) -> None:
        try:
            await self._redis.xgroup_create(
                stream_key,
                group_name,
                id="$",
                mkstream=True,
            )
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def _evaluate_choice(self, node: DAGNode, state: dict[str, Any]) -> str | None:
        """Evaluate a CHOICE node.

        Production note:
            replace this with a safe expression DSL.
        """
        del state
        choices = list(getattr(node, "choices", []) or [])
        if choices:
            first = choices[0]
            return getattr(first, "next", None)
        return getattr(node, "default_next", None)

    def _resolve_next_after_completed(
        self,
        node: DAGNode,
        state: dict[str, Any],
    ) -> str | None:
        del state
        return getattr(node, "next", None)

    def _load_dag(self, workflow: Workflow) -> WorkflowDAG:
        if not workflow.plan_schema:
            raise ValueError(f"Workflow {workflow.id} has no plan_schema")
        return WorkflowDAG.model_validate(workflow.plan_schema)

    def _get_node(self, dag: WorkflowDAG, node_id: str) -> DAGNode | None:
        return next((node for node in dag.nodes if node.id == node_id), None)

    def _normalize_state(
        self,
        raw_state: Any,
        dag: WorkflowDAG,
    ) -> dict[str, Any]:
        state = dict(raw_state or {})
        state.setdefault("current_node", dag.start_at)
        state.setdefault("completed_nodes", {})
        state.setdefault("running_nodes", {})
        state.setdefault("suspended_nodes", {})
        state.setdefault("failed_nodes", {})
        return state

    def _get_node_state(
        self,
        state: dict[str, Any],
        node_id: str,
    ) -> dict[str, Any]:
        if node_id in state["completed_nodes"]:
            return {"status": NODE_COMPLETED, **state["completed_nodes"][node_id]}
        if node_id in state["suspended_nodes"]:
            return {"status": NODE_SUSPENDED, **state["suspended_nodes"][node_id]}
        if node_id in state["running_nodes"]:
            return {"status": NODE_RUNNING, **state["running_nodes"][node_id]}
        if node_id in state["failed_nodes"]:
            return {"status": NODE_FAILED, **state["failed_nodes"][node_id]}
        return {"status": NODE_PENDING}

    def _mark_node_running(
        self,
        state: dict[str, Any],
        node_id: str,
        kind: str,
        meta: dict[str, Any],
    ) -> None:
        state["running_nodes"][node_id] = {
            "kind": kind,
            "started_at": self._now_iso(),
            **meta,
        }
        state["suspended_nodes"].pop(node_id, None)
        state["failed_nodes"].pop(node_id, None)

    def _mark_node_suspended(
        self,
        state: dict[str, Any],
        node_id: str,
        suspend_type: str,
        meta: dict[str, Any],
    ) -> None:
        state["suspended_nodes"][node_id] = {
            "kind": suspend_type,
            "started_at": self._now_iso(),
            **meta,
        }
        state["running_nodes"].pop(node_id, None)
        state["failed_nodes"].pop(node_id, None)

    def _mark_node_completed(
        self,
        state: dict[str, Any],
        node_id: str,
        output: Any,
    ) -> None:
        state["completed_nodes"][node_id] = {
            "completed_at": self._now_iso(),
            "output": output,
        }
        state["running_nodes"].pop(node_id, None)
        state["suspended_nodes"].pop(node_id, None)
        state["failed_nodes"].pop(node_id, None)

    def _mark_node_failed(
        self,
        state: dict[str, Any],
        node_id: str,
        error: Any,
    ) -> None:
        state["failed_nodes"][node_id] = {
            "failed_at": self._now_iso(),
            "error": error,
        }
        state["running_nodes"].pop(node_id, None)
        state["suspended_nodes"].pop(node_id, None)

    async def _log_event(
        self,
        workflow_id: uuid.UUID,
        event_type: str,
        node_id: str | None,
        **kwargs: Any,
    ) -> None:
        event = WorkflowEvent(
            workflow_id=workflow_id,
            event_type=event_type,
            node_id=node_id,
            input_data=kwargs.get("input_data"),
            output_data=kwargs.get("output_data"),
            error_data=kwargs.get("error_data"),
        )
        self._db.add(event)
        await self._db.flush()

    def _signal_stream_key(self, workflow_id: uuid.UUID) -> str:
        return f"{_SIGNAL_STREAM_PREFIX}{workflow_id}"

    def _signal_group_name(self, workflow_id: uuid.UUID) -> str:
        return f"{_SIGNAL_GROUP_PREFIX}{workflow_id}"

    def _coerce_uuid(self, value: str | uuid.UUID) -> uuid.UUID:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, separators=(",", ":"), default=str)

    @staticmethod
    def _decode_redis_value(value: str | bytes | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value

    @classmethod
    def _parse_json(cls, value: str | bytes | None) -> Any:
        decoded = cls._decode_redis_value(value)
        if decoded is None:
            return None
        return json.loads(decoded)
