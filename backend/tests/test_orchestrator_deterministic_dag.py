from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.orchestrator.models import Workflow
from domain.orchestrator.runtime_kernel import ExecutionContext, ExecutionStrategy
from domain.orchestrator.workflow_dag import DAGNode, NodeKind, WorkflowDAG
from services.orchestrator.backends import ButlerDeterministicExecutor
from services.workflow.engine import WorkflowEngine


class _FakeTask:
    def __init__(self) -> None:
        self.id = uuid.uuid4()
        self.task_type = "memory_recall"
        self.tool_name = "memory_recall"
        self.input_data = {"query": "hello"}


@pytest.mark.asyncio
async def test_deterministic_executor_uses_task_tool_for_dag_workflow() -> None:
    tools = MagicMock()
    tools.execute = AsyncMock(return_value={"content": "remembered"})
    executor = ButlerDeterministicExecutor(tools)

    workflow = Workflow(
        id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        session_id="session-1",
        mode="macro",
        status="active",
        plan_schema=WorkflowDAG(
            nodes=[
                DAGNode(id="step_0_memory_recall", kind=NodeKind.TASK, tool_name="memory_recall"),
                DAGNode(id="terminal_success", kind=NodeKind.SUCCESS),
            ],
            start_at="step_0_memory_recall",
        ).model_dump(),
    )
    task = _FakeTask()

    ctx = ExecutionContext(
        task=task,
        workflow=workflow,
        strategy=ExecutionStrategy.DETERMINISTIC,
        model="",
        toolset=[],
        system_prompt="",
        messages=[],
        trace_id="trace-1",
        account_id=str(workflow.account_id),
        session_id=workflow.session_id,
    )

    result = await executor.execute(ctx)

    tools.execute.assert_awaited_once()
    assert tools.execute.await_args.kwargs["tool_name"] == "memory_recall"
    assert tools.execute.await_args.kwargs["params"] == {"query": "hello"}
    assert result["content"] == "remembered"


@pytest.mark.asyncio
async def test_workflow_engine_uses_node_tool_name_as_task_type() -> None:
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    redis = AsyncMock()
    sm = MagicMock()

    workflow = Workflow(
        id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        session_id="session-1",
        mode="macro",
        status="active",
        plan_schema={},
        state_snapshot={
            "completed_nodes": {},
            "running_nodes": {},
            "suspended_nodes": {},
            "failed_nodes": {},
        },
    )
    node = DAGNode(id="step_0_memory_recall", kind=NodeKind.TASK, tool_name="memory_recall")
    state = {"completed_nodes": {}, "running_nodes": {}, "suspended_nodes": {}, "failed_nodes": {}}

    engine = WorkflowEngine(db, redis, sm)

    await engine._start_task_node(workflow, node, state)

    task = db.add.call_args.args[0]
    assert task.task_type == "memory_recall"
    assert task.tool_name == "memory_recall"
