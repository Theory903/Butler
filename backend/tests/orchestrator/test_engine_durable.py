import sys
from unittest.mock import MagicMock, AsyncMock

# Mock out infrastructure and core deps to avoid environment failures
sys.modules["infrastructure.database"] = MagicMock()
sys.modules["infrastructure.database"].Base = MagicMock
sys.modules["core.errors"] = MagicMock()
sys.modules["domain.orchestrator.exceptions"] = MagicMock()
sys.modules["domain.orchestrator.state"] = MagicMock()
# Create a mock for models that allows select(Workflow)
mock_models = MagicMock()
sys.modules["domain.orchestrator.models"] = mock_models
sys.modules["structlog"] = MagicMock()

import pytest
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from unittest.mock import patch, AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager

from domain.orchestrator.workflow_dag import WorkflowDAG, DAGNode, NodeKind
# We need to ensure engine.py uses our Mock classes or we mock the model lookups

from domain.orchestrator.workflow_dag import WorkflowDAG, DAGNode, NodeKind
from services.workflow.engine import WorkflowEngine

# We mock Workflow and Task locally since we can't import them from models
# because models imports infrastructure.database.Base
@dataclass
class MockWorkflow:
    id: uuid.UUID
    plan_schema: dict
    status: str
    version: str = "1.0"
    state_snapshot: Optional[dict] = None
    completed_at: Optional[Any] = None

@dataclass
class MockTask:
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    workflow_id: Optional[uuid.UUID] = None
    node_id: str = ""
    status: str = "pending"
    task_type: str = "execution"
    tool_name: Optional[str] = None
    input_data: Optional[dict] = field(default_factory=dict)
    version: str = "1.0"

# Inject mocks into the module
mock_models.Workflow = MockWorkflow
mock_models.Task = MockTask
mock_models.WorkflowEvent = MagicMock
mock_models.WorkflowSignal = MagicMock

from services.workflow.engine import WorkflowEngine, NODE_RUNNING, NODE_COMPLETED

# We no longer import from infrastructure.database.models 
# to avoid triggering the engine creation in database.py

@pytest.mark.asyncio
class TestWorkflowEngineDurable:
    """Tests for the event-sourced WorkflowEngine kernel."""

    async def test_linear_stepping_log_events(self):
        # 1. Setup a simple 2-node DAG
        dag = WorkflowDAG(
            nodes=[
                DAGNode(id="node_1", kind=NodeKind.TASK, tool_name="tool_a", next="node_2"),
                DAGNode(id="node_2", kind=NodeKind.TASK, tool_name="tool_b", next=None),
            ],
            start_at="node_1"
        )
        
        workflow = MockWorkflow(
            id=uuid.uuid4(),
            plan_schema=dag.model_dump(),
            status="active"
        )
        
        mock_db = AsyncMock(spec=AsyncSession)
        mock_redis = MagicMock()
        mock_sm = MagicMock()
        engine = WorkflowEngine(mock_db, redis=mock_redis, state_machine=mock_sm)
        
        # Mock the internal lock context manager
        @asynccontextmanager
        async def mock_lock(wf_id):
            yield workflow
        engine._lock_workflow = mock_lock
        
        # 2. Step from start
        await engine.step_workflow(workflow.id)
        
        # 3. Task nodes suspend on the current node until completed
        assert workflow.state_snapshot["current_node"] == "node_1"
        assert workflow.state_snapshot["running_nodes"]["node_1"]["kind"] == "task"
        
        # 4. Verify node_start event was logged
        assert mock_db.flush.called

    async def test_choice_node_branching(self):
        # 1. Setup a DAG with a Choice node
        dag = WorkflowDAG(
            nodes=[
                DAGNode(id="start", kind=NodeKind.TASK, tool_name="init", next="branch"),
                DAGNode(
                    id="branch", 
                    kind=NodeKind.CHOICE, 
                    # Choice rules in v1 are conditions
                    choices=[
                        {"variable": "val", "operator": "NumericGreaterThan", "value": 10, "next": "high"},
                    ],
                    default_next="low"
                ),
                DAGNode(id="high", kind=NodeKind.TASK, tool_name="high_tool"),
                DAGNode(id="low", kind=NodeKind.TASK, tool_name="low_tool"),
            ],
            start_at="start"
        )
        
        workflow = MockWorkflow(
            id=uuid.uuid4(),
            plan_schema=dag.model_dump(),
            status="active"
        )
        
        mock_db = AsyncMock(spec=AsyncSession)
        mock_redis = MagicMock()
        mock_sm = MagicMock()
        engine = WorkflowEngine(mock_db, redis=mock_redis, state_machine=mock_sm)
        
        @asynccontextmanager
        async def mock_lock(wf_id):
            yield workflow
        engine._lock_workflow = mock_lock

        # Step 1: Initialize
        await engine.step_workflow(workflow.id)
        assert workflow.state_snapshot["current_node"] == "start"
        
        # Complete 'start' node
        # We need a task object for complete_task_node
        task_id = uuid.uuid4()
        running_meta = workflow.state_snapshot["running_nodes"]["start"]
        running_meta["task_id"] = str(task_id) # engine expects meta to have task_id
        
        task = MockTask(id=task_id, workflow_id=workflow.id, node_id="start")
        mock_db.get.return_value = task

        await engine.complete_task_node(workflow.id, "start", task_id, {"val": 15})
        
        # Step 2: Traverse Choice (automatically advances past non-suspending Choice)
        # Note: step_workflow is called internally at end of complete_task_node
        
        # Choice nodes are non-suspending, they advance immediately
        assert workflow.state_snapshot["current_node"] == "high"

    async def test_deterministic_replay_skip(self):
        """If node_end event exists, the engine should know it is finished."""
        dag = WorkflowDAG(
            nodes=[
                DAGNode(id="n1", kind=NodeKind.TASK, next="n2"),
                DAGNode(id="n2", kind=NodeKind.TASK),
            ],
            start_at="n1"
        )
        
        workflow = MockWorkflow(
            id=uuid.uuid4(),
            plan_schema=dag.model_dump(),
            status="active",
            # Mock state showing n1 is completed
            state_snapshot={"completed_nodes": {"n1": {"output": {}}}, "running_nodes": {}, "suspended_nodes": {}, "current_node": "n1"}
        )
        
        mock_db = AsyncMock(spec=AsyncSession)
        mock_redis = MagicMock()
        mock_sm = MagicMock()
        engine = WorkflowEngine(mock_db, redis=mock_redis, state_machine=mock_sm)
        
        @asynccontextmanager
        async def mock_lock(wf_id):
            yield workflow
        engine._lock_workflow = mock_lock

        # Should advance from n1 to n2 because n1 is COMPLETED
        await engine.step_workflow(workflow.id)
        
        # Should jump to n2
        assert workflow.state_snapshot["current_node"] == "n2"
