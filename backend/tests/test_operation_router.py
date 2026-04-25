"""Comprehensive tests for OperationRouter and AdmissionController.

Tests cover:
- Admission control logic for different operation types
- Risk tier handling
- Routing logic for all operation types
- Edge cases and error conditions
- Hardened error handling
"""

import dataclasses
import pytest

from domain.orchestration.router import (
    AdmissionController,
    AdmissionDecision,
    AdmissionResult,
    OperationRequest,
    OperationRouter,
    OperationType,
)


class TestAdmissionController:
    """Test AdmissionController admission logic."""

    def test_admission_controller_init(self):
        """Test AdmissionController initialization."""
        controller = AdmissionController(enable_rate_limiting=True)
        assert controller.enable_rate_limiting is True

        controller = AdmissionController(enable_rate_limiting=False)
        assert controller.enable_rate_limiting is False

    def test_check_admission_low_risk_tool_call(self):
        """Test low-risk tool call is allowed."""
        controller = AdmissionController()
        request = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name="search",
            risk_tier="L1",
            estimated_cost=0.01,
        )

        result = controller.check_admission(request)
        assert result.decision == AdmissionDecision.ALLOW
        assert result.reason == "Operation allowed"
        assert result.approval_id is None

    def test_check_admission_high_risk_tool_call(self):
        """Test high-risk tool call requires approval."""
        controller = AdmissionController()
        request = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name="delete_database",
            risk_tier="L3",
            estimated_cost=100.0,
        )

        result = controller.check_admission(request)
        assert result.decision == AdmissionDecision.REQUIRE_APPROVAL
        assert result.reason == "High-risk operation requires approval"
        assert result.approval_id == "apr_tenant_1_account_1"

    def test_check_admission_memory_write_no_check(self):
        """Test memory write does not require admission check."""
        controller = AdmissionController()
        request = OperationRequest(
            operation_type=OperationType.MEMORY_WRITE,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name=None,
            risk_tier=None,
            estimated_cost=None,
        )

        result = controller.check_admission(request)
        assert result.decision == AdmissionDecision.ALLOW
        assert result.reason == "Operation does not require admission check"

    def test_check_admission_chat_no_check(self):
        """Test chat does not require admission check."""
        controller = AdmissionController()
        request = OperationRequest(
            operation_type=OperationType.CHAT,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name=None,
            risk_tier=None,
            estimated_cost=None,
        )

        result = controller.check_admission(request)
        assert result.decision == AdmissionDecision.ALLOW
        assert result.reason == "Operation does not require admission check"

    def test_check_admission_workflow_execution_high_risk(self):
        """Test high-risk workflow execution requires approval."""
        controller = AdmissionController()
        request = OperationRequest(
            operation_type=OperationType.WORKFLOW_EXECUTION,
            tenant_id="tenant_2",
            account_id="account_2",
            user_id="user_2",
            tool_name=None,
            risk_tier="L4",
            estimated_cost=500.0,
        )

        result = controller.check_admission(request)
        assert result.decision == AdmissionDecision.REQUIRE_APPROVAL
        assert result.approval_id == "apr_tenant_2_account_2"

    def test_check_admission_workflow_execution_low_risk(self):
        """Test low-risk workflow execution is allowed."""
        controller = AdmissionController()
        request = OperationRequest(
            operation_type=OperationType.WORKFLOW_EXECUTION,
            tenant_id="tenant_2",
            account_id="account_2",
            user_id="user_2",
            tool_name=None,
            risk_tier="L2",
            estimated_cost=10.0,
        )

        result = controller.check_admission(request)
        assert result.decision == AdmissionDecision.ALLOW
        assert result.reason == "Operation allowed"

    def test_check_admission_missing_risk_tier(self):
        """Test operation with missing risk tier is allowed."""
        controller = AdmissionController()
        request = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name="unknown",
            risk_tier=None,
            estimated_cost=None,
        )

        result = controller.check_admission(request)
        assert result.decision == AdmissionDecision.ALLOW
        assert result.reason == "Operation allowed"


class TestOperationRequest:
    """Test OperationRequest dataclass."""

    def test_requires_admission_check_tool_call(self):
        """Test tool call requires admission check."""
        request = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name="search",
            risk_tier="L1",
            estimated_cost=0.01,
        )
        assert request.requires_admission_check() is True

    def test_requires_admission_check_workflow_execution(self):
        """Test workflow execution requires admission check."""
        request = OperationRequest(
            operation_type=OperationType.WORKFLOW_EXECUTION,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name=None,
            risk_tier="L2",
            estimated_cost=10.0,
        )
        assert request.requires_admission_check() is True

    def test_requires_admission_check_memory_write(self):
        """Test memory write does not require admission check."""
        request = OperationRequest(
            operation_type=OperationType.MEMORY_WRITE,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name=None,
            risk_tier=None,
            estimated_cost=None,
        )
        assert request.requires_admission_check() is False

    def test_requires_admission_check_chat(self):
        """Test chat does not require admission check."""
        request = OperationRequest(
            operation_type=OperationType.CHAT,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name=None,
            risk_tier=None,
            estimated_cost=None,
        )
        assert request.requires_admission_check() is False

    def test_is_high_risk_l3(self):
        """Test L3 risk tier is high risk."""
        request = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name="delete",
            risk_tier="L3",
            estimated_cost=100.0,
        )
        assert request.is_high_risk() is True

    def test_is_high_risk_l4(self):
        """Test L4 risk tier is high risk."""
        request = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name="destroy",
            risk_tier="L4",
            estimated_cost=1000.0,
        )
        assert request.is_high_risk() is True

    def test_is_high_risk_l1(self):
        """Test L1 risk tier is not high risk."""
        request = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name="search",
            risk_tier="L1",
            estimated_cost=0.01,
        )
        assert request.is_high_risk() is False

    def test_is_high_risk_l2(self):
        """Test L2 risk tier is not high risk."""
        request = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name="query",
            risk_tier="L2",
            estimated_cost=1.0,
        )
        assert request.is_high_risk() is False

    def test_is_high_risk_none(self):
        """Test None risk tier is not high risk."""
        request = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name="unknown",
            risk_tier=None,
            estimated_cost=None,
        )
        assert request.is_high_risk() is False

    def test_operation_request_frozen(self):
        """Test OperationRequest is frozen (immutable)."""
        request = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name="search",
            risk_tier="L1",
            estimated_cost=0.01,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            request.tenant_id = "tenant_2"  # type: ignore


class TestOperationRouter:
    """Test OperationRouter routing logic."""

    def test_router_init(self):
        """Test OperationRouter initialization."""
        controller = AdmissionController()
        router = OperationRouter(admission_controller=controller)
        assert router.admission_controller is controller

    def test_route_tool_call_allowed(self):
        """Test routing allowed tool call to tool_executor."""
        controller = AdmissionController()
        router = OperationRouter(admission_controller=controller)
        request = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name="search",
            risk_tier="L1",
            estimated_cost=0.01,
        )

        path, admission = router.route(request)
        assert path == "tool_executor"
        assert admission.decision == AdmissionDecision.ALLOW

    def test_route_tool_call_blocked(self):
        """Test routing blocked tool call."""
        controller = AdmissionController()
        router = OperationRouter(admission_controller=controller)
        request = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name="delete",
            risk_tier="L3",
            estimated_cost=100.0,
        )

        path, admission = router.route(request)
        assert path == "blocked"
        assert admission.decision == AdmissionDecision.REQUIRE_APPROVAL

    def test_route_workflow_execution_allowed(self):
        """Test routing allowed workflow execution to workflow_engine."""
        controller = AdmissionController()
        router = OperationRouter(admission_controller=controller)
        request = OperationRequest(
            operation_type=OperationType.WORKFLOW_EXECUTION,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name=None,
            risk_tier="L2",
            estimated_cost=10.0,
        )

        path, admission = router.route(request)
        assert path == "workflow_engine"
        assert admission.decision == AdmissionDecision.ALLOW

    def test_route_workflow_execution_blocked(self):
        """Test routing blocked workflow execution."""
        controller = AdmissionController()
        router = OperationRouter(admission_controller=controller)
        request = OperationRequest(
            operation_type=OperationType.WORKFLOW_EXECUTION,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name=None,
            risk_tier="L4",
            estimated_cost=500.0,
        )

        path, admission = router.route(request)
        assert path == "blocked"
        assert admission.decision == AdmissionDecision.REQUIRE_APPROVAL

    def test_route_memory_write(self):
        """Test routing memory write to memory_writer."""
        controller = AdmissionController()
        router = OperationRouter(admission_controller=controller)
        request = OperationRequest(
            operation_type=OperationType.MEMORY_WRITE,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name=None,
            risk_tier=None,
            estimated_cost=None,
        )

        path, admission = router.route(request)
        assert path == "memory_writer"
        assert admission.decision == AdmissionDecision.ALLOW

    def test_route_memory_read(self):
        """Test routing memory read to memory_reader."""
        controller = AdmissionController()
        router = OperationRouter(admission_controller=controller)
        request = OperationRequest(
            operation_type=OperationType.MEMORY_READ,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name=None,
            risk_tier=None,
            estimated_cost=None,
        )

        path, admission = router.route(request)
        assert path == "memory_reader"
        assert admission.decision == AdmissionDecision.ALLOW

    def test_route_chat(self):
        """Test routing chat to chat_handler."""
        controller = AdmissionController()
        router = OperationRouter(admission_controller=controller)
        request = OperationRequest(
            operation_type=OperationType.CHAT,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name=None,
            risk_tier=None,
            estimated_cost=None,
        )

        path, admission = router.route(request)
        assert path == "chat_handler"
        assert admission.decision == AdmissionDecision.ALLOW

    def test_route_streaming(self):
        """Test routing streaming to chat_handler (default)."""
        controller = AdmissionController()
        router = OperationRouter(admission_controller=controller)
        request = OperationRequest(
            operation_type=OperationType.STREAMING,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name=None,
            risk_tier=None,
            estimated_cost=None,
        )

        path, admission = router.route(request)
        assert path == "chat_handler"
        assert admission.decision == AdmissionDecision.ALLOW

    def test_route_with_null_user_id(self):
        """Test routing with null user_id."""
        controller = AdmissionController()
        router = OperationRouter(admission_controller=controller)
        request = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id=None,
            tool_name="search",
            risk_tier="L1",
            estimated_cost=0.01,
        )

        path, admission = router.route(request)
        assert path == "tool_executor"
        assert admission.decision == AdmissionDecision.ALLOW


class TestAdmissionResult:
    """Test AdmissionResult dataclass."""

    def test_admission_result_allow(self):
        """Test ALLOW admission result."""
        result = AdmissionResult(
            decision=AdmissionDecision.ALLOW,
            reason="Operation allowed",
        )
        assert result.decision == AdmissionDecision.ALLOW
        assert result.reason == "Operation allowed"
        assert result.approval_id is None
        assert result.retry_after_seconds is None

    def test_admission_result_require_approval(self):
        """Test REQUIRE_APPROVAL admission result."""
        result = AdmissionResult(
            decision=AdmissionDecision.REQUIRE_APPROVAL,
            reason="High-risk operation requires approval",
            approval_id="apr_tenant_1_account_1",
        )
        assert result.decision == AdmissionDecision.REQUIRE_APPROVAL
        assert result.approval_id == "apr_tenant_1_account_1"
        assert result.retry_after_seconds is None

    def test_admission_result_rate_limited(self):
        """Test RATE_LIMITED admission result."""
        result = AdmissionResult(
            decision=AdmissionDecision.RATE_LIMITED,
            reason="Too many requests",
            retry_after_seconds=60,
        )
        assert result.decision == AdmissionDecision.RATE_LIMITED
        assert result.retry_after_seconds == 60
        assert result.approval_id is None

    def test_admission_result_frozen(self):
        """Test AdmissionResult is frozen (immutable)."""
        result = AdmissionResult(
            decision=AdmissionDecision.ALLOW,
            reason="Operation allowed",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.decision = AdmissionDecision.DENY  # type: ignore


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_admission_controller_with_none_request(self):
        """Test AdmissionController handles None request gracefully."""
        controller = AdmissionController()
        with pytest.raises(AttributeError):
            controller.check_admission(None)  # type: ignore

    def test_router_with_none_controller(self):
        """Test OperationRouter handles None controller."""
        with pytest.raises(TypeError):
            OperationRouter(admission_controller=None)  # type: ignore

    def test_operation_request_with_invalid_risk_tier(self):
        """Test OperationRequest with invalid risk tier."""
        request = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name="test",
            risk_tier="INVALID",
            estimated_cost=0.01,
        )
        # Invalid risk tier should not be high risk
        assert request.is_high_risk() is False

    def test_empty_tenant_id(self):
        """Test operation with empty tenant_id."""
        controller = AdmissionController()
        request = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="",
            account_id="account_1",
            user_id="user_1",
            tool_name="search",
            risk_tier="L1",
            estimated_cost=0.01,
        )
        result = controller.check_admission(request)
        assert result.decision == AdmissionDecision.ALLOW

    def test_empty_account_id(self):
        """Test operation with empty account_id."""
        controller = AdmissionController()
        request = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="tenant_1",
            account_id="",
            user_id="user_1",
            tool_name="search",
            risk_tier="L1",
            estimated_cost=0.01,
        )
        result = controller.check_admission(request)
        assert result.decision == AdmissionDecision.ALLOW

    def test_negative_estimated_cost(self):
        """Test operation with negative estimated cost."""
        request = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name="search",
            risk_tier="L1",
            estimated_cost=-10.0,
        )
        # Negative cost should not affect admission
        assert request.is_high_risk() is False

    def test_zero_estimated_cost(self):
        """Test operation with zero estimated cost."""
        request = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name="search",
            risk_tier="L1",
            estimated_cost=0.0,
        )
        assert request.is_high_risk() is False


class TestIntegrationScenarios:
    """Test integration scenarios with multiple components."""

    def test_full_routing_flow_allowed(self):
        """Test full routing flow for allowed operation."""
        controller = AdmissionController()
        router = OperationRouter(admission_controller=controller)
        request = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name="search",
            risk_tier="L1",
            estimated_cost=0.01,
        )

        path, admission = router.route(request)
        assert path == "tool_executor"
        assert admission.decision == AdmissionDecision.ALLOW
        assert admission.reason == "Operation allowed"

    def test_full_routing_flow_blocked(self):
        """Test full routing flow for blocked operation."""
        controller = AdmissionController()
        router = OperationRouter(admission_controller=controller)
        request = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name="delete",
            risk_tier="L3",
            estimated_cost=100.0,
        )

        path, admission = router.route(request)
        assert path == "blocked"
        assert admission.decision == AdmissionDecision.REQUIRE_APPROVAL
        assert admission.reason == "High-risk operation requires approval"
        assert admission.approval_id == "apr_tenant_1_account_1"

    def test_multiple_operations_same_tenant(self):
        """Test multiple operations from same tenant."""
        controller = AdmissionController()
        router = OperationRouter(admission_controller=controller)

        # Low-risk operation
        request1 = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name="search",
            risk_tier="L1",
            estimated_cost=0.01,
        )
        path1, admission1 = router.route(request1)
        assert path1 == "tool_executor"
        assert admission1.decision == AdmissionDecision.ALLOW

        # High-risk operation
        request2 = OperationRequest(
            operation_type=OperationType.TOOL_CALL,
            tenant_id="tenant_1",
            account_id="account_1",
            user_id="user_1",
            tool_name="delete",
            risk_tier="L3",
            estimated_cost=100.0,
        )
        path2, admission2 = router.route(request2)
        assert path2 == "blocked"
        assert admission2.decision == AdmissionDecision.REQUIRE_APPROVAL

    def test_different_operation_types(self):
        """Test routing for all operation types."""
        controller = AdmissionController()
        router = OperationRouter(admission_controller=controller)

        operations = [
            (OperationType.CHAT, "chat_handler"),
            (OperationType.TOOL_CALL, "tool_executor"),
            (OperationType.MEMORY_WRITE, "memory_writer"),
            (OperationType.MEMORY_READ, "memory_reader"),
            (OperationType.WORKFLOW_EXECUTION, "workflow_engine"),
            (OperationType.STREAMING, "chat_handler"),
        ]

        for op_type, expected_path in operations:
            request = OperationRequest(
                operation_type=op_type,
                tenant_id="tenant_1",
                account_id="account_1",
                user_id="user_1",
                tool_name="test" if op_type == OperationType.TOOL_CALL else None,
                risk_tier="L1" if op_type == OperationType.TOOL_CALL else None,
                estimated_cost=0.01 if op_type == OperationType.TOOL_CALL else None,
            )
            path, admission = router.route(request)
            assert path == expected_path, f"Failed for {op_type}"
            assert admission.decision == AdmissionDecision.ALLOW
