"""Comprehensive tests for durable workflow engine.

Tests cover:
- WorkflowDefinition dataclass and factory
- WorkflowExecution dataclass and methods
- WorkflowStatus enum
- RetryPolicy enum
- Edge cases and error conditions
- Hardened error handling
"""

import dataclasses

import pytest

from domain.workflow.durable import (
    RetryPolicy,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowStatus,
)


class TestWorkflowStatus:
    """Test WorkflowStatus enum."""

    def test_status_values(self):
        """Test all status values exist."""
        assert WorkflowStatus.RUNNING.value == "running"
        assert WorkflowStatus.COMPLETED.value == "completed"
        assert WorkflowStatus.FAILED.value == "failed"
        assert WorkflowStatus.CANCELLED.value == "cancelled"
        assert WorkflowStatus.TIMED_OUT.value == "timed_out"

    def test_status_comparison(self):
        """Test status comparison."""
        assert WorkflowStatus.RUNNING == WorkflowStatus.RUNNING
        assert WorkflowStatus.RUNNING != WorkflowStatus.COMPLETED


class TestRetryPolicy:
    """Test RetryPolicy enum."""

    def test_policy_values(self):
        """Test all policy values exist."""
        assert RetryPolicy.NONE.value == "none"
        assert RetryPolicy.LINEAR.value == "linear"
        assert RetryPolicy.EXPONENTIAL.value == "exponential"
        assert RetryPolicy.FIXED.value == "fixed"

    def test_policy_comparison(self):
        """Test policy comparison."""
        assert RetryPolicy.EXPONENTIAL == RetryPolicy.EXPONENTIAL
        assert RetryPolicy.EXPONENTIAL != RetryPolicy.LINEAR


class TestWorkflowDefinition:
    """Test WorkflowDefinition dataclass."""

    def test_create_workflow_definition(self):
        """Test creating a workflow definition."""
        definition = WorkflowDefinition(
            workflow_id="wf_1",
            workflow_name="test_workflow",
            tenant_id="tenant_1",
            account_id="account_1",
            task_id="task_1",
            timeout_seconds=300,
            retry_policy=RetryPolicy.EXPONENTIAL,
            max_retries=3,
        )
        assert definition.workflow_id == "wf_1"
        assert definition.workflow_name == "test_workflow"
        assert definition.tenant_id == "tenant_1"
        assert definition.account_id == "account_1"
        assert definition.task_id == "task_1"
        assert definition.timeout_seconds == 300
        assert definition.retry_policy == RetryPolicy.EXPONENTIAL
        assert definition.max_retries == 3

    def test_create_workflow_definition_factory(self):
        """Test creating workflow definition using factory method."""
        definition = WorkflowDefinition.create(
            workflow_id="wf_1",
            workflow_name="test_workflow",
            tenant_id="tenant_1",
            account_id="account_1",
        )
        assert definition.workflow_id == "wf_1"
        assert definition.workflow_name == "test_workflow"
        assert definition.tenant_id == "tenant_1"
        assert definition.account_id == "account_1"
        assert definition.task_id is None
        assert definition.timeout_seconds == 300
        assert definition.retry_policy == RetryPolicy.EXPONENTIAL
        assert definition.max_retries == 3

    def test_create_workflow_definition_factory_with_custom_params(self):
        """Test factory method with custom parameters."""
        definition = WorkflowDefinition.create(
            workflow_id="wf_1",
            workflow_name="test_workflow",
            tenant_id="tenant_1",
            account_id="account_1",
            task_id="task_1",
            timeout_seconds=600,
            retry_policy=RetryPolicy.LINEAR,
            max_retries=5,
        )
        assert definition.task_id == "task_1"
        assert definition.timeout_seconds == 600
        assert definition.retry_policy == RetryPolicy.LINEAR
        assert definition.max_retries == 5

    def test_workflow_definition_frozen(self):
        """Test WorkflowDefinition is frozen (immutable)."""
        definition = WorkflowDefinition.create(
            workflow_id="wf_1",
            workflow_name="test_workflow",
            tenant_id="tenant_1",
            account_id="account_1",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            definition.workflow_id = "wf_2"  # type: ignore

    def test_workflow_definition_with_none_task_id(self):
        """Test workflow definition with None task_id."""
        definition = WorkflowDefinition.create(
            workflow_id="wf_1",
            workflow_name="test_workflow",
            tenant_id="tenant_1",
            account_id="account_1",
            task_id=None,
        )
        assert definition.task_id is None

    def test_workflow_definition_with_zero_timeout(self):
        """Test workflow definition with zero timeout."""
        definition = WorkflowDefinition.create(
            workflow_id="wf_1",
            workflow_name="test_workflow",
            tenant_id="tenant_1",
            account_id="account_1",
            timeout_seconds=0,
        )
        assert definition.timeout_seconds == 0

    def test_workflow_definition_with_negative_timeout(self):
        """Test workflow definition with negative timeout (should be allowed)."""
        definition = WorkflowDefinition.create(
            workflow_id="wf_1",
            workflow_name="test_workflow",
            tenant_id="tenant_1",
            account_id="account_1",
            timeout_seconds=-1,
        )
        assert definition.timeout_seconds == -1

    def test_workflow_definition_with_zero_retries(self):
        """Test workflow definition with zero retries."""
        definition = WorkflowDefinition.create(
            workflow_id="wf_1",
            workflow_name="test_workflow",
            tenant_id="tenant_1",
            account_id="account_1",
            max_retries=0,
        )
        assert definition.max_retries == 0


class TestWorkflowExecution:
    """Test WorkflowExecution dataclass."""

    def test_create_workflow_execution_completed(self):
        """Test creating a completed workflow execution."""
        execution = WorkflowExecution(
            workflow_id="wf_1",
            status=WorkflowStatus.COMPLETED,
            result={"output": "success"},
            error=None,
            started_at=0.0,
            completed_at=1.0,
        )
        assert execution.workflow_id == "wf_1"
        assert execution.status == WorkflowStatus.COMPLETED
        assert execution.result == {"output": "success"}
        assert execution.error is None
        assert execution.started_at == 0.0
        assert execution.completed_at == 1.0

    def test_create_workflow_execution_failed(self):
        """Test creating a failed workflow execution."""
        execution = WorkflowExecution(
            workflow_id="wf_1",
            status=WorkflowStatus.FAILED,
            result=None,
            error="Task failed",
            started_at=0.0,
            completed_at=1.0,
        )
        assert execution.status == WorkflowStatus.FAILED
        assert execution.result is None
        assert execution.error == "Task failed"

    def test_create_workflow_execution_running(self):
        """Test creating a running workflow execution."""
        execution = WorkflowExecution(
            workflow_id="wf_1",
            status=WorkflowStatus.RUNNING,
            result=None,
            error=None,
            started_at=0.0,
            completed_at=None,
        )
        assert execution.status == WorkflowStatus.RUNNING
        assert execution.completed_at is None

    def test_is_complete_completed(self):
        """Test is_complete returns True for completed status."""
        execution = WorkflowExecution(
            workflow_id="wf_1",
            status=WorkflowStatus.COMPLETED,
            result=None,
            error=None,
            started_at=0.0,
            completed_at=1.0,
        )
        assert execution.is_complete() is True

    def test_is_complete_failed(self):
        """Test is_complete returns True for failed status."""
        execution = WorkflowExecution(
            workflow_id="wf_1",
            status=WorkflowStatus.FAILED,
            result=None,
            error="Error",
            started_at=0.0,
            completed_at=1.0,
        )
        assert execution.is_complete() is True

    def test_is_complete_cancelled(self):
        """Test is_complete returns True for cancelled status."""
        execution = WorkflowExecution(
            workflow_id="wf_1",
            status=WorkflowStatus.CANCELLED,
            result=None,
            error=None,
            started_at=0.0,
            completed_at=1.0,
        )
        assert execution.is_complete() is True

    def test_is_complete_timed_out(self):
        """Test is_complete returns True for timed_out status."""
        execution = WorkflowExecution(
            workflow_id="wf_1",
            status=WorkflowStatus.TIMED_OUT,
            result=None,
            error=None,
            started_at=0.0,
            completed_at=1.0,
        )
        assert execution.is_complete() is True

    def test_is_complete_running(self):
        """Test is_complete returns False for running status."""
        execution = WorkflowExecution(
            workflow_id="wf_1",
            status=WorkflowStatus.RUNNING,
            result=None,
            error=None,
            started_at=0.0,
            completed_at=None,
        )
        assert execution.is_complete() is False

    def test_is_successful_completed(self):
        """Test is_successful returns True for completed status."""
        execution = WorkflowExecution(
            workflow_id="wf_1",
            status=WorkflowStatus.COMPLETED,
            result=None,
            error=None,
            started_at=0.0,
            completed_at=1.0,
        )
        assert execution.is_successful() is True

    def test_is_successful_failed(self):
        """Test is_successful returns False for failed status."""
        execution = WorkflowExecution(
            workflow_id="wf_1",
            status=WorkflowStatus.FAILED,
            result=None,
            error="Error",
            started_at=0.0,
            completed_at=1.0,
        )
        assert execution.is_successful() is False

    def test_is_successful_cancelled(self):
        """Test is_successful returns False for cancelled status."""
        execution = WorkflowExecution(
            workflow_id="wf_1",
            status=WorkflowStatus.CANCELLED,
            result=None,
            error=None,
            started_at=0.0,
            completed_at=1.0,
        )
        assert execution.is_successful() is False

    def test_is_successful_running(self):
        """Test is_successful returns False for running status."""
        execution = WorkflowExecution(
            workflow_id="wf_1",
            status=WorkflowStatus.RUNNING,
            result=None,
            error=None,
            started_at=0.0,
            completed_at=None,
        )
        assert execution.is_successful() is False

    def test_workflow_execution_frozen(self):
        """Test WorkflowExecution is frozen (immutable)."""
        execution = WorkflowExecution(
            workflow_id="wf_1",
            status=WorkflowStatus.RUNNING,
            result=None,
            error=None,
            started_at=0.0,
            completed_at=None,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            execution.status = WorkflowStatus.COMPLETED  # type: ignore


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_workflow_definition_empty_ids(self):
        """Test workflow definition with empty IDs."""
        definition = WorkflowDefinition.create(
            workflow_id="",
            workflow_name="",
            tenant_id="",
            account_id="",
        )
        assert definition.workflow_id == ""
        assert definition.workflow_name == ""
        assert definition.tenant_id == ""
        assert definition.account_id == ""

    def test_workflow_definition_very_long_ids(self):
        """Test workflow definition with very long IDs."""
        long_id = "a" * 10000
        definition = WorkflowDefinition.create(
            workflow_id=long_id,
            workflow_name=long_id,
            tenant_id=long_id,
            account_id=long_id,
        )
        assert definition.workflow_id == long_id
        assert definition.workflow_name == long_id

    def test_workflow_definition_unicode_ids(self):
        """Test workflow definition with unicode IDs."""
        definition = WorkflowDefinition.create(
            workflow_id="wf_日本語",
            workflow_name="workflow_中文",
            tenant_id="tenant_العربية",
            account_id="account_русский",
        )
        assert "日本語" in definition.workflow_id
        assert "中文" in definition.workflow_name

    def test_workflow_execution_negative_timestamps(self):
        """Test workflow execution with negative timestamps."""
        execution = WorkflowExecution(
            workflow_id="wf_1",
            status=WorkflowStatus.RUNNING,
            result=None,
            error=None,
            started_at=-1.0,
            completed_at=None,
        )
        assert execution.started_at == -1.0

    def test_workflow_execution_large_timestamps(self):
        """Test workflow execution with large timestamps."""
        execution = WorkflowExecution(
            workflow_id="wf_1",
            status=WorkflowStatus.COMPLETED,
            result=None,
            error=None,
            started_at=9999999999.0,
            completed_at=10000000000.0,
        )
        assert execution.started_at == 9999999999.0
        assert execution.completed_at == 10000000000.0

    def test_workflow_execution_empty_result(self):
        """Test workflow execution with empty result dict."""
        execution = WorkflowExecution(
            workflow_id="wf_1",
            status=WorkflowStatus.COMPLETED,
            result={},
            error=None,
            started_at=0.0,
            completed_at=1.0,
        )
        assert execution.result == {}

    def test_workflow_execution_large_result(self):
        """Test workflow execution with large result dict."""
        large_result: dict[str, object] = {f"key_{i}": f"value_{i}" for i in range(10000)}
        execution = WorkflowExecution(
            workflow_id="wf_1",
            status=WorkflowStatus.COMPLETED,
            result=large_result,
            error=None,
            started_at=0.0,
            completed_at=1.0,
        )
        assert len(execution.result or {}) == 10000


class TestIntegrationScenarios:
    """Test integration scenarios."""

    def test_full_workflow_lifecycle(self):
        """Test full workflow lifecycle from definition to execution."""
        # Create workflow definition
        definition = WorkflowDefinition.create(
            workflow_id="wf_1",
            workflow_name="test_workflow",
            tenant_id="tenant_1",
            account_id="account_1",
            task_id="task_1",
        )

        # Simulate execution
        execution_running = WorkflowExecution(
            workflow_id=definition.workflow_id,
            status=WorkflowStatus.RUNNING,
            result=None,
            error=None,
            started_at=0.0,
            completed_at=None,
        )

        assert execution_running.is_complete() is False
        assert execution_running.is_successful() is False

        # Simulate completion
        execution_completed = WorkflowExecution(
            workflow_id=definition.workflow_id,
            status=WorkflowStatus.COMPLETED,
            result={"output": "success"},
            error=None,
            started_at=0.0,
            completed_at=1.0,
        )

        assert execution_completed.is_complete() is True
        assert execution_completed.is_successful() is True

    def test_workflow_with_linear_retry(self):
        """Test workflow with linear retry policy."""
        definition = WorkflowDefinition.create(
            workflow_id="wf_1",
            workflow_name="test_workflow",
            tenant_id="tenant_1",
            account_id="account_1",
            retry_policy=RetryPolicy.LINEAR,
            max_retries=5,
        )
        assert definition.retry_policy == RetryPolicy.LINEAR
        assert definition.max_retries == 5

    def test_workflow_with_no_retry(self):
        """Test workflow with no retry policy."""
        definition = WorkflowDefinition.create(
            workflow_id="wf_1",
            workflow_name="test_workflow",
            tenant_id="tenant_1",
            account_id="account_1",
            retry_policy=RetryPolicy.NONE,
            max_retries=0,
        )
        assert definition.retry_policy == RetryPolicy.NONE
        assert definition.max_retries == 0

    def test_multiple_workflow_executions(self):
        """Test multiple workflow executions."""
        executions = []
        for i in range(10):
            execution = WorkflowExecution(
                workflow_id=f"wf_{i}",
                status=WorkflowStatus.COMPLETED,
                result={"index": i},
                error=None,
                started_at=float(i),
                completed_at=float(i + 1),
            )
            executions.append(execution)

        assert len(executions) == 10
        assert all(e.is_complete() for e in executions)
        assert all(e.is_successful() for e in executions)

    def test_workflow_failure_then_retry(self):
        """Test workflow failure then retry scenario."""
        # First execution fails
        execution_failed = WorkflowExecution(
            workflow_id="wf_1",
            status=WorkflowStatus.FAILED,
            result=None,
            error="Temporary error",
            started_at=0.0,
            completed_at=1.0,
        )

        assert execution_failed.is_complete() is True
        assert execution_failed.is_successful() is False

        # Retry succeeds
        execution_success = WorkflowExecution(
            workflow_id="wf_1",
            status=WorkflowStatus.COMPLETED,
            result={"output": "success"},
            error=None,
            started_at=2.0,
            completed_at=3.0,
        )

        assert execution_success.is_complete() is True
        assert execution_success.is_successful() is True
