"""Tests for Butler Unified Runtime.

Validates the fused Butler-Hermes unified runtime.
"""

import pytest

from butler_runtime.agent.budget import ExecutionBudget
from butler_runtime.hermes.execution.tool_schema_converter import (
    convert_hermes_schema_to_butler_spec,
)
from butler_runtime.hermes.tools.utility import ButlerHermesUtilityTools
from butler_runtime.tools.registry import ButlerToolSpec, UnifiedToolRegistry


class TestExecutionBudget:
    """Test ExecutionBudget functionality."""

    def test_initial_state(self):
        """Test initial budget state."""
        budget = ExecutionBudget(max_total=10)
        assert budget.used == 0
        assert budget.remaining == 10
        assert budget.can_continue() is True

    def test_consume_iteration(self):
        """Test consuming iterations."""
        budget = ExecutionBudget(max_total=10)
        assert budget.consume() is True
        assert budget.used == 1
        assert budget.remaining == 9

    def test_budget_exhausted(self):
        """Test budget exhaustion."""
        budget = ExecutionBudget(max_total=2)
        assert budget.consume() is True
        assert budget.consume() is True
        assert budget.consume() is False
        assert budget.can_continue() is False

    def test_refund(self):
        """Test iteration refund."""
        budget = ExecutionBudget(max_total=10)
        budget.consume()
        assert budget.used == 1
        budget.refund()
        assert budget.used == 0

    def test_token_budget(self):
        """Test token budget tracking."""
        budget = ExecutionBudget(max_total=10, max_tokens=1000)
        assert budget.consume_tokens(500, 300) is True
        assert budget.input_tokens == 500
        assert budget.output_tokens == 300
        assert budget.total_tokens == 800
        assert budget.remaining_tokens == 200

    def test_token_budget_exceeded(self):
        """Test token budget exceeded."""
        budget = ExecutionBudget(max_total=10, max_tokens=1000)
        assert budget.consume_tokens(500, 600) is True
        assert budget.consume_tokens(100, 100) is False


class TestUnifiedToolRegistry:
    """Test UnifiedToolRegistry functionality."""

    def test_register_tool(self):
        """Test registering a tool."""
        registry = UnifiedToolRegistry()
        spec = ButlerToolSpec(
            name="test_tool",
            description="Test tool",
            parameters={"type": "object", "properties": {}},
            category="test",
            risk_tier="low",
        )
        registry.register(spec)
        assert "test_tool" in registry
        assert len(registry) == 1

    def test_get_tool(self):
        """Test getting a tool."""
        registry = UnifiedToolRegistry()
        spec = ButlerToolSpec(
            name="test_tool",
            description="Test tool",
            parameters={"type": "object", "properties": {}},
            category="test",
            risk_tier="low",
        )
        registry.register(spec)
        retrieved = registry.get("test_tool")
        assert retrieved is not None
        assert retrieved.name == "test_tool"

    def test_get_by_category(self):
        """Test getting tools by category."""
        registry = UnifiedToolRegistry()
        spec1 = ButlerToolSpec(
            name="file_tool",
            description="File tool",
            parameters={"type": "object", "properties": {}},
            category="file",
            risk_tier="medium",
        )
        spec2 = ButlerToolSpec(
            name="web_tool",
            description="Web tool",
            parameters={"type": "object", "properties": {}},
            category="web",
            risk_tier="low",
        )
        registry.register(spec1)
        registry.register(spec2)

        file_tools = registry.get_by_category("file")
        assert len(file_tools) == 1
        assert file_tools[0].name == "file_tool"

    def test_get_visible(self):
        """Test getting visible tools by risk tier."""
        registry = UnifiedToolRegistry()
        spec1 = ButlerToolSpec(
            name="low_risk_tool",
            description="Low risk",
            parameters={"type": "object", "properties": {}},
            category="test",
            risk_tier="low",
        )
        spec2 = ButlerToolSpec(
            name="high_risk_tool",
            description="High risk",
            parameters={"type": "object", "properties": {}},
            category="test",
            risk_tier="high",
        )
        registry.register(spec1)
        registry.register(spec2)

        visible = registry.get_visible(risk_tier_limit="low")
        assert len(visible) == 1
        assert visible[0].name == "low_risk_tool"

    def test_enable_disable(self):
        """Test enabling/disabling tools."""
        registry = UnifiedToolRegistry()
        spec = ButlerToolSpec(
            name="test_tool",
            description="Test tool",
            parameters={"type": "object", "properties": {}},
            category="test",
            risk_tier="low",
            enabled=True,
        )
        registry.register(spec)

        assert registry.disable("test_tool") is True
        assert registry.get("test_tool").enabled is False

        assert registry.enable("test_tool") is True
        assert registry.get("test_tool").enabled is True

    def test_unregister(self):
        """Test unregistering a tool."""
        registry = UnifiedToolRegistry()
        spec = ButlerToolSpec(
            name="test_tool",
            description="Test tool",
            parameters={"type": "object", "properties": {}},
            category="test",
            risk_tier="low",
        )
        registry.register(spec)
        assert "test_tool" in registry

        assert registry.unregister("test_tool") is True
        assert "test_tool" not in registry


class TestSchemaConverter:
    """Test Hermes schema conversion."""

    def test_basic_conversion(self):
        """Test basic schema conversion."""
        hermes_schema = {
            "description": "A test tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "input": {"type": "string"},
                },
            },
        }

        butler_spec = convert_hermes_schema_to_butler_spec(
            "test_tool", hermes_schema, category="test"
        )

        assert butler_spec.name == "test_tool"
        assert butler_spec.description == "A test tool"
        assert butler_spec.category == "test"
        assert butler_spec.source == "hermes"

    def test_risk_tier_auto_assignment(self):
        """Test automatic risk tier assignment."""
        hermes_schema = {
            "description": "Shell tool",
            "parameters": {"type": "object", "properties": {}},
        }

        shell_spec = convert_hermes_schema_to_butler_spec(
            "shell_tool", hermes_schema, category="shell"
        )
        assert shell_spec.risk_tier == "high"

        web_spec = convert_hermes_schema_to_butler_spec("web_tool", hermes_schema, category="web")
        assert web_spec.risk_tier == "low"


class TestUtilityTools:
    """Test ButlerHermesUtilityTools."""

    @pytest.mark.asyncio
    async def test_fuzzy_find_and_replace(self):
        """Test fuzzy find and replace."""
        tools = ButlerHermesUtilityTools()

        result = await tools.fuzzy_find_and_replace(
            content="hello world",
            search="world",
            replace="universe",
        )

        assert result["new_content"] == "hello universe"
        assert result["match_count"] == 1
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_fuzzy_no_match(self):
        """Test fuzzy find and replace with no match."""
        tools = ButlerHermesUtilityTools()

        result = await tools.fuzzy_find_and_replace(
            content="hello world",
            search="mars",
            replace="venus",
        )

        assert result["match_count"] == 0
        assert result["error"] == "No matches found"

    def test_strip_ansi(self):
        """Test ANSI escape sequence removal."""
        tools = ButlerHermesUtilityTools()

        text = "\x1b[31mHello\x1b[0m World"
        stripped = tools.strip_ansi(text)

        assert stripped == "Hello World"
        assert "\x1b" not in stripped

    def test_is_safe_url(self):
        """Test URL safety check."""
        tools = ButlerHermesUtilityTools(allow_private_urls=False)

        # Public URL should be safe
        assert tools.is_safe_url("https://example.com") is True

        # Private URL should be blocked
        assert tools.is_safe_url("http://192.168.1.1") is False

    def test_is_safe_url_private_allowed(self):
        """Test URL safety check with private URLs allowed."""
        tools = ButlerHermesUtilityTools(allow_private_urls=True)

        # Private URL should be allowed
        assert tools.is_safe_url("http://192.168.1.1") is True


class TestGraphState:
    """Test ButlerGraphState."""

    def test_state_creation(self):
        """Test creating graph state."""
        from butler_runtime.graph.state import ButlerGraphState

        state = ButlerGraphState(
            account_id="test_account",
            session_id="test_session",
            user_message="hello",
            model="gpt-4",
        )

        assert state.account_id == "test_account"
        assert state.session_id == "test_session"
        assert state.user_message == "hello"
        assert state.model == "gpt-4"
        assert state.iterations == 0

    def test_state_to_dict(self):
        """Test converting state to dictionary."""
        from butler_runtime.graph.state import ButlerGraphState

        state = ButlerGraphState(
            account_id="test_account",
            session_id="test_session",
            user_message="hello",
            model="gpt-4",
        )

        data = state.to_dict()
        assert data["account_id"] == "test_account"
        assert data["user_message"] == "hello"

    def test_state_from_dict(self):
        """Test creating state from dictionary."""
        from butler_runtime.graph.state import ButlerGraphState

        data = {
            "account_id": "test_account",
            "session_id": "test_session",
            "user_message": "hello",
            "model": "gpt-4",
        }

        state = ButlerGraphState.from_dict(data)
        assert state.account_id == "test_account"
        assert state.user_message == "hello"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
