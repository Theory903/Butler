"""Tests for ToolScope Deep Architecture - 6-layer pipeline.

Tests for:
1. Intent Builder (Layer 1)
2. Tool Retrieval Pipeline (Layer 2)
3. Tool Selection Contract (Layer 3)
4. Execution Guardrail (Layer 4)
5. Feedback Loop (Layer 6)
"""

from __future__ import annotations

import pytest

from domain.tools.selection_contract import ToolSelection, ToolRejection, ToolSelectionContract
from domain.tools.specs import ButlerToolSpec, RiskTier, ApprovalMode, ExecutableKind
from services.intent.intent_builder import IntentBuilder, IntentContext, IntentConstraints
from services.tools.guardrail import ExecutionGuardrail, GuardrailResult
from services.tools.feedback_service import FeedbackService, ToolFeedback


class TestIntentBuilder:
    """Test Layer 1: Intent Builder."""

    def test_intent_builder_initialization(self):
        """Test intent builder can be initialized."""
        builder = IntentBuilder(enabled=True, default_risk_level="L2", max_query_length=500)
        assert builder._enabled is True
        assert builder._default_risk_level == "L2"
        assert builder._max_query_length == 500

    def test_build_intent_context(self):
        """Test building intent context from user input."""
        builder = IntentBuilder(enabled=True)
        context = builder.build("What time is it?")

        assert isinstance(context, IntentContext)
        assert context.query == "What time is it?"
        assert context.intent_type in ["action", "info", "transactional"]
        assert context.original_input == "What time is it?"

    def test_normalize_query(self):
        """Test query normalization removes noise."""
        builder = IntentBuilder(enabled=True)
        context = builder.build("Please can you get the current time? Thanks!")

        # Should remove filler phrases
        assert "please" not in context.query.lower()
        assert "thanks" not in context.query.lower()

    def test_classify_intent_action(self):
        """Test intent classification for action queries."""
        builder = IntentBuilder(enabled=True)
        context = builder.build("Send an email to John")

        assert context.intent_type == "action"

    def test_classify_intent_transactional(self):
        """Test intent classification for transactional queries."""
        builder = IntentBuilder(enabled=True)
        context = builder.build("Delete my account")

        assert context.intent_type == "transactional"

    def test_classify_intent_info(self):
        """Test intent classification for info queries."""
        builder = IntentBuilder(enabled=True)
        context = builder.build("What is the weather today?")

        assert context.intent_type == "info"

    def test_extract_constraints_latency_sensitive(self):
        """Test constraint extraction for latency-sensitive queries."""
        builder = IntentBuilder(enabled=True)
        context = builder.build("Get the time quickly")

        assert context.constraints.latency == "low"

    def test_extract_constraints_cost_sensitive(self):
        """Test constraint extraction for cost-sensitive queries."""
        builder = IntentBuilder(enabled=True)
        context = builder.build("Find cheap flights")

        assert context.constraints.cost_sensitive is True

    def test_disabled_intent_builder(self):
        """Test disabled intent builder passes through."""
        builder = IntentBuilder(enabled=False)
        context = builder.build("Test query")

        assert context.query == "Test query"
        assert context.intent_type == "info"


class TestToolSelectionContract:
    """Test Layer 3: Tool Selection Contract."""

    def test_tool_selection_creation(self):
        """Test creating a tool selection."""
        selection = ToolSelection(
            name="get_time",
            reason="User wants to know the time",
            confidence=0.85,
            score_components={"semantic": 0.8, "intent": 0.9},
        )

        assert selection.name == "get_time"
        assert selection.confidence == 0.85
        assert selection.reason == "User wants to know the time"

    def test_tool_rejection_creation(self):
        """Test creating a tool rejection."""
        rejection = ToolRejection(
            name="delete_account",
            reason="Too high risk tier",
            stage="policy",
            score=0.95,
        )

        assert rejection.name == "delete_account"
        assert rejection.stage == "policy"

    def test_selection_contract_creation(self):
        """Test creating a selection contract."""
        selected = [
            ToolSelection(name="get_time", reason="time query", confidence=0.9)
        ]
        rejected = [
            ToolRejection(name="delete_account", reason="risk", stage="policy")
        ]

        contract = ToolSelectionContract(
            selected_tools=selected,
            rejected_tools=rejected,
            retrieval_metadata={"stage1_candidates": 10},
        )

        assert contract.get_tool_count() == 1
        assert contract.has_tool("get_time")
        assert not contract.has_tool("delete_account")

    def test_contract_to_dict(self):
        """Test contract serialization."""
        selected = [
            ToolSelection(name="get_time", reason="time query", confidence=0.9)
        ]
        contract = ToolSelectionContract(
            selected_tools=selected,
            rejected_tools=[],
            retrieval_metadata={},
        )

        contract_dict = contract.to_dict()
        assert "selected_tools" in contract_dict
        assert "rejected_tools" in contract_dict
        assert contract_dict["selected_count"] == 1


class TestExecutionGuardrail:
    """Test Layer 4: Execution Guardrail."""

    @pytest.fixture
    def sample_tool_spec(self):
        """Create a sample tool spec for testing."""
        return ButlerToolSpec(
            name="get_time",
            version="1.0.0",
            description="Get current time",
            owner="tools",
            risk_tier=RiskTier.L0,
            approval_mode=ApprovalMode.NONE,
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            executable_kind=ExecutableKind.DIRECT_FUNCTION,
            binding_ref="get_time",
            timeout_ms=5000,
            idempotent=True,
            enabled=True,
            model_visible=True,
            tags=["time"],
        )

    @pytest.fixture
    def sample_selection(self, sample_tool_spec):
        """Create a sample tool selection."""
        from domain.tools.selection_contract import ToolSelection

        return ToolSelection(
            name="get_time",
            reason="User wants time",
            confidence=0.9,
            spec=sample_tool_spec,
        )

    def test_guardrail_initialization(self):
        """Test guardrail can be initialized."""
        guardrail = ExecutionGuardrail(
            enabled=True,
            strict_mode=False,
            max_parameter_size=10000,
        )
        assert guardrail._enabled is True

    def test_guardrail_validate_pass(self, sample_selection):
        """Test guardrail validation passes for safe tools."""
        guardrail = ExecutionGuardrail(enabled=True, strict_mode=False)
        result = guardrail.validate(selected_tools=[sample_selection])

        assert result.passed is True
        assert len(result.violations) == 0

    def test_guardrail_validate_l3_requires_admin(self):
        """Test L3 tools require admin permissions."""
        from domain.tools.selection_contract import ToolSelection

        l3_spec = ButlerToolSpec(
            name="delete_account",
            version="1.0.0",
            description="Delete user account",
            owner="admin",
            risk_tier=RiskTier.L3,
            approval_mode=ApprovalMode.REQUIRED,
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            executable_kind=ExecutableKind.DIRECT_FUNCTION,
            binding_ref="delete_account",
            timeout_ms=5000,
            idempotent=False,
            enabled=True,
            model_visible=True,
            tags=["admin"],
        )

        selection = ToolSelection(
            name="delete_account",
            reason="User wants to delete",
            confidence=0.9,
            spec=l3_spec,
        )

        guardrail = ExecutionGuardrail(enabled=True)
        result = guardrail.validate(
            selected_tools=[selection],
            account_permissions=frozenset(["read_only"]),
        )

        assert result.passed is False
        assert "admin" in str(result.violations).lower()

    def test_guardrail_validate_with_admin_permissions(self):
        """Test L3 tools pass with admin permissions."""
        from domain.tools.selection_contract import ToolSelection

        l3_spec = ButlerToolSpec(
            name="delete_account",
            version="1.0.0",
            description="Delete user account",
            owner="admin",
            risk_tier=RiskTier.L3,
            approval_mode=ApprovalMode.REQUIRED,
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            executable_kind=ExecutableKind.DIRECT_FUNCTION,
            binding_ref="delete_account",
            timeout_ms=5000,
            idempotent=False,
            enabled=True,
            model_visible=True,
            tags=["admin"],
        )

        selection = ToolSelection(
            name="delete_account",
            reason="User wants to delete",
            confidence=0.9,
            spec=l3_spec,
        )

        guardrail = ExecutionGuardrail(enabled=True)
        result = guardrail.validate(
            selected_tools=[selection],
            account_permissions=frozenset(["admin"]),
        )

        assert result.passed is True

    def test_guardrail_validate_parameters_missing_required(self, sample_selection):
        """Test guardrail validates required parameters."""
        guardrail = ExecutionGuardrail(enabled=True, enable_schema_validation=True)

        # Add required field to schema
        sample_selection.spec.input_schema = {
            "type": "object",
            "properties": {"timezone": {"type": "string"}},
            "required": ["timezone"],
        }

        result = guardrail.validate(
            selected_tools=[sample_selection],
            parameters={"get_time": {}},  # Missing timezone
        )

        assert len(result.violations) > 0
        assert "timezone" in str(result.violations).lower()

    def test_guardrail_disabled(self, sample_selection):
        """Test disabled guardrail always passes."""
        guardrail = ExecutionGuardrail(enabled=False)
        result = guardrail.validate(selected_tools=[sample_selection])

        assert result.passed is True


class TestFeedbackService:
    """Test Layer 6: Feedback Loop."""

    def test_feedback_service_initialization(self):
        """Test feedback service can be initialized."""
        service = FeedbackService(
            enabled=True,
            feedback_window_seconds=3600,
            min_samples=10,
        )
        assert service._enabled is True

    def test_record_feedback(self):
        """Test recording tool execution feedback."""
        service = FeedbackService(enabled=True)
        feedback = ToolFeedback(
            tool="get_time",
            used=True,
            success=True,
            latency_ms=100,
            user_satisfied=True,
            error_type=None,
        )

        # Record should not raise errors
        # Note: This is async but we're testing the sync interface
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(service.record(feedback))

        assert "get_time" in service._feedback_history

    def test_get_success_rates(self):
        """Test getting tool success rates."""
        service = FeedbackService(enabled=True)

        # Record some feedback
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        for i in range(15):
            feedback = ToolFeedback(
                tool="get_time",
                used=True,
                success=(i % 2 == 0),  # 50% success rate
                latency_ms=100,
                user_satisfied=True,
                error_type=None,
            )
            loop.run_until_complete(service.record(feedback))

        success_rates = loop.run_until_complete(service.get_success_rates())

        assert "get_time" in success_rates
        assert 0.0 <= success_rates["get_time"] <= 1.0

    def test_get_tool_feedback_summary(self):
        """Test getting feedback summary for a tool."""
        service = FeedbackService(enabled=True)

        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        for _ in range(10):
            feedback = ToolFeedback(
                tool="get_time",
                used=True,
                success=True,
                latency_ms=100,
                user_satisfied=True,
                error_type=None,
            )
            loop.run_until_complete(service.record(feedback))

        summary = loop.run_until_complete(service.get_tool_feedback_summary("get_time"))

        assert summary["tool"] == "get_time"
        assert summary["total_executions"] == 10
        assert summary["successful_executions"] == 10
        assert summary["success_rate"] == 1.0

    def test_feedback_disabled(self):
        """Test disabled feedback service doesn't record."""
        service = FeedbackService(enabled=False)
        feedback = ToolFeedback(
            tool="get_time",
            used=True,
            success=True,
            latency_ms=100,
            user_satisfied=True,
            error_type=None,
        )

        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(service.record(feedback))

        # Should not record when disabled
        assert len(service._feedback_history) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
