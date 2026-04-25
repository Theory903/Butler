import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.orchestrator.models import Task, Workflow
from domain.orchestrator.workflow_dag import DAGNode, NodeKind, PlanLowerer, WorkflowDAG
from services.orchestrator.planner import Plan, Step
from services.workflow.engine import WorkflowEngine


def _workflow_result(workflow: Workflow) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = workflow
    return result


def _assign_task_ids(db: AsyncMock) -> None:
    def add(obj):
        if isinstance(obj, Task) and getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()

    db.add.side_effect = add


@pytest.mark.asyncio
async def test_workflow_dag_traversal():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    db.add = MagicMock()
    _assign_task_ids(db)
    redis = AsyncMock()
    sm = MagicMock()

    node_a = DAGNode(id="node_a", kind=NodeKind.TASK, tool_name="action_a", next="node_b")
    node_b = DAGNode(
        id="node_b",
        kind=NodeKind.TASK,
        tool_name="action_b",
        depends_on=["node_a"],
        next="terminal_success",
    )
    terminal = DAGNode(id="terminal_success", kind=NodeKind.SUCCESS)
    dag = WorkflowDAG(nodes=[node_a, node_b, terminal], start_at="node_a")

    workflow = Workflow(
        id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        session_id="session-1",
        mode="durable",
        status="active",
        plan_schema=dag.model_dump(),
        state_snapshot={
            "completed_nodes": {},
            "running_nodes": {},
            "suspended_nodes": {},
            "failed_nodes": {},
        },
    )
    db.execute = AsyncMock(return_value=_workflow_result(workflow))

    engine = WorkflowEngine(db, redis, sm)

    changed = await engine.step_workflow(str(workflow.id))

    assert changed is True
    assert workflow.state_snapshot["current_node"] == "node_a"
    assert "node_a" in workflow.state_snapshot["running_nodes"]

    task_id = uuid.UUID(workflow.state_snapshot["running_nodes"]["node_a"]["task_id"])
    task = Task(id=task_id, workflow_id=workflow.id, task_type="execution", status="pending")
    db.get = AsyncMock(return_value=task)

    await engine.complete_task_node(str(workflow.id), "node_a", str(task_id), {"result": "ok"})

    assert "node_a" in workflow.state_snapshot["completed_nodes"]
    assert "node_b" in workflow.state_snapshot["running_nodes"]


@pytest.mark.asyncio
async def test_plan_lowerer():
    plan = Plan(
        steps=[
            Step(action="step1", params={}),
            Step(action="step2", params={}),
        ],
        intent="test",
        context={},
    )

    dag = PlanLowerer.lower(plan)

    assert dag.start_at == "step_0_step1"
    assert len(dag.nodes) == 3
    assert dag.nodes[0].kind == NodeKind.TASK
    assert dag.nodes[0].next == "step_1_step2"
    assert dag.nodes[1].next == "terminal_success"
    assert dag.nodes[2].kind == NodeKind.SUCCESS


@pytest.mark.asyncio
async def test_signal_resumption():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    db.add = MagicMock()
    _assign_task_ids(db)
    redis = AsyncMock()
    sm = MagicMock()

    node_wait = DAGNode(id="wait_node", kind=NodeKind.APPROVAL)
    dag = WorkflowDAG(nodes=[node_wait], start_at="wait_node")

    workflow = Workflow(
        id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        session_id="session-2",
        mode="durable",
        status="active",
        plan_schema=dag.model_dump(),
        state_snapshot={
            "current_node": "wait_node",
            "completed_nodes": {},
            "running_nodes": {},
            "suspended_nodes": {
                "wait_node": {"kind": "approval", "signal_name": "approval_decision"}
            },
            "failed_nodes": {},
        },
    )
    db.execute = AsyncMock(return_value=_workflow_result(workflow))

    engine = WorkflowEngine(db, redis, sm)

    await engine._apply_signal_message(
        workflow.id,
        {"signal_name": "approval_decision", "payload": '{"decision":"approved"}'},
    )

    assert "wait_node" in workflow.state_snapshot["completed_nodes"]
    assert "wait_node" not in workflow.state_snapshot["suspended_nodes"]
