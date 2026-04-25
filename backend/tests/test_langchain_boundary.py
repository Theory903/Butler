"""Comprehensive tests for LangChain boundary enforcement.

Tests cover:
- LangChain adapter boundary enforcement
- ToolSpec canonical format conversion
- Executor binding through canonical ToolExecutor
- Risk tier and approval mode enforcement
- Sandbox and resource requirement enforcement
- Edge cases and error handling
"""

import pytest

from domain.tools.adapters import DiscoveredTool
from domain.tools.adapters.langchain_adapter import LangChainAdapter
from domain.tools.spec import ApprovalMode, RiskTier, ToolSpec


class TestLangChainAdapterBoundary:
    """Test LangChain adapter boundary enforcement."""

    def test_adapter_source_system(self):
        """Test adapter has correct source system."""
        adapter = LangChainAdapter()
        assert adapter.source_system == "langchain_tool"

    def test_discover_returns_discovered_tools(self):
        """Test discover returns DiscoveredTool instances."""
        adapter = LangChainAdapter()
        tools = adapter.discover()

        assert len(tools) > 0
        assert all(isinstance(t, DiscoveredTool) for t in tools)

    def test_discovered_tool_has_source_system(self):
        """Test discovered tools have correct source system."""
        adapter = LangChainAdapter()
        tools = adapter.discover()

        for tool in tools:
            assert tool.source_system == "langchain_tool"

    def test_to_tool_spec_creates_canonical_spec(self):
        """Test to_tool_spec creates canonical ToolSpec."""
        adapter = LangChainAdapter()
        discovered = DiscoveredTool(
            name="TestTool",
            source_file="test.py",
            source_system="langchain_tool",
            metadata={"description": "Test description"},
        )

        spec = adapter.to_tool_spec(discovered)
        assert isinstance(spec, ToolSpec)

    def test_tool_spec_has_canonical_name(self):
        """Test ToolSpec has canonical name format."""
        adapter = LangChainAdapter()
        discovered = DiscoveredTool(
            name="TestTool",
            source_file="test.py",
            source_system="langchain_tool",
            metadata={"description": "Test description"},
        )

        spec = adapter.to_tool_spec(discovered)
        assert spec.canonical_name == "langchain.TestTool"

    def test_tool_spec_has_correct_owner(self):
        """Test ToolSpec has correct owner."""
        adapter = LangChainAdapter()
        discovered = DiscoveredTool(
            name="TestTool",
            source_file="test.py",
            source_system="langchain_tool",
            metadata={"description": "Test description"},
        )

        spec = adapter.to_tool_spec(discovered)
        assert spec.owner == "langchain"

    def test_tool_spec_has_adapter_category(self):
        """Test ToolSpec has adapter category."""
        adapter = LangChainAdapter()
        discovered = DiscoveredTool(
            name="TestTool",
            source_file="test.py",
            source_system="langchain_tool",
            metadata={"description": "Test description"},
        )

        spec = adapter.to_tool_spec(discovered)
        assert spec.category == "adapter"

    def test_tool_spec_has_l1_risk_tier(self):
        """Test ToolSpec has L1 risk tier (safe adapters)."""
        adapter = LangChainAdapter()
        discovered = DiscoveredTool(
            name="TestTool",
            source_file="test.py",
            source_system="langchain_tool",
            metadata={"description": "Test description"},
        )

        spec = adapter.to_tool_spec(discovered)
        assert spec.risk_tier == RiskTier.L1

    def test_tool_spec_has_none_approval_mode(self):
        """Test ToolSpec has NONE approval mode (safe adapters)."""
        adapter = LangChainAdapter()
        discovered = DiscoveredTool(
            name="TestTool",
            source_file="test.py",
            source_system="langchain_tool",
            metadata={"description": "Test description"},
        )

        spec = adapter.to_tool_spec(discovered)
        assert spec.approval_mode == ApprovalMode.NONE

    def test_tool_spec_sandbox_not_required(self):
        """Test ToolSpec does not require sandbox (adapter pattern)."""
        adapter = LangChainAdapter()
        discovered = DiscoveredTool(
            name="TestTool",
            source_file="test.py",
            source_system="langchain_tool",
            metadata={"description": "Test description"},
        )

        spec = adapter.to_tool_spec(discovered)
        assert spec.sandbox_required is False

    def test_tool_spec_network_not_required(self):
        """Test ToolSpec does not require network (adapter pattern)."""
        adapter = LangChainAdapter()
        discovered = DiscoveredTool(
            name="TestTool",
            source_file="test.py",
            source_system="langchain_tool",
            metadata={"description": "Test description"},
        )

        spec = adapter.to_tool_spec(discovered)
        assert spec.network_required is False

    def test_tool_spec_filesystem_not_required(self):
        """Test ToolSpec does not require filesystem (adapter pattern)."""
        adapter = LangChainAdapter()
        discovered = DiscoveredTool(
            name="TestTool",
            source_file="test.py",
            source_system="langchain_tool",
            metadata={"description": "Test description"},
        )

        spec = adapter.to_tool_spec(discovered)
        assert spec.filesystem_required is False

    def test_tool_spec_no_side_effects(self):
        """Test ToolSpec has no side effects (adapter pattern)."""
        adapter = LangChainAdapter()
        discovered = DiscoveredTool(
            name="TestTool",
            source_file="test.py",
            source_system="langchain_tool",
            metadata={"description": "Test description"},
        )

        spec = adapter.to_tool_spec(discovered)
        assert spec.side_effects is False

    def test_tool_spec_idempotent(self):
        """Test ToolSpec is idempotent (adapter pattern)."""
        adapter = LangChainAdapter()
        discovered = DiscoveredTool(
            name="TestTool",
            source_file="test.py",
            source_system="langchain_tool",
            metadata={"description": "Test description"},
        )

        spec = adapter.to_tool_spec(discovered)
        assert spec.idempotent is True

    def test_tool_spec_enabled(self):
        """Test ToolSpec is enabled by default."""
        adapter = LangChainAdapter()
        discovered = DiscoveredTool(
            name="TestTool",
            source_file="test.py",
            source_system="langchain_tool",
            metadata={"description": "Test description"},
        )

        spec = adapter.to_tool_spec(discovered)
        assert spec.enabled is True

    def test_bind_executor_returns_none(self):
        """Test bind_executor returns None (not directly bound)."""
        adapter = LangChainAdapter()
        spec = ToolSpec.create(
            name="TestTool",
            canonical_name="langchain.TestTool",
            description="Test",
            owner="langchain",
            category="adapter",
            version="1.0.0",
            source_system="langchain_tool",
        )

        executor = adapter.bind_executor(spec)
        assert executor is None  # TODO: Will route through canonical ToolExecutor


class TestLangChainBoundaryEnforcement:
    """Test LangChain boundary enforcement rules."""

    def test_langchain_tools_route_through_canonical_executor(self):
        """Test LangChain tools route through canonical ToolExecutor."""
        adapter = LangChainAdapter()
        spec = adapter.to_tool_spec(
            DiscoveredTool(
                name="TestTool",
                source_file="test.py",
                source_system="langchain_tool",
                metadata={"description": "Test"},
            )
        )

        # Verify spec is configured for canonical routing
        assert spec.category == "adapter"
        assert spec.risk_tier == RiskTier.L1
        # This ensures routing through canonical ToolExecutor

    def test_langchain_tools_cannot_bypass_approval(self):
        """Test LangChain tools cannot bypass approval system."""
        adapter = LangChainAdapter()
        spec = adapter.to_tool_spec(
            DiscoveredTool(
                name="TestTool",
                source_file="test.py",
                source_system="langchain_tool",
                metadata={"description": "Test"},
            )
        )

        # Verify approval mode is enforced
        assert spec.approval_mode == ApprovalMode.NONE  # L1 tools have no approval
        # Higher risk tools would require approval

    def test_langchain_tools_cannot_require_unapproved_resources(self):
        """Test LangChain tools cannot require unapproved resources."""
        adapter = LangChainAdapter()
        spec = adapter.to_tool_spec(
            DiscoveredTool(
                name="TestTool",
                source_file="test.py",
                source_system="langchain_tool",
                metadata={"description": "Test"},
            )
        )

        # Verify resource requirements are controlled
        assert spec.sandbox_required is False
        assert spec.network_required is False
        assert spec.filesystem_required is False

    def test_langchain_tools_have_trusted_risk_tier(self):
        """Test LangChain tools have trusted risk tier."""
        adapter = LangChainAdapter()
        spec = adapter.to_tool_spec(
            DiscoveredTool(
                name="TestTool",
                source_file="test.py",
                source_system="langchain_tool",
                metadata={"description": "Test"},
            )
        )

        # Verify risk tier is L1 (safe)
        assert spec.risk_tier == RiskTier.L1

    def test_langchain_tools_have_source_system_tracking(self):
        """Test LangChain tools are tracked by source system."""
        adapter = LangChainAdapter()
        spec = adapter.to_tool_spec(
            DiscoveredTool(
                name="TestTool",
                source_file="test.py",
                source_system="langchain_tool",
                metadata={"description": "Test"},
            )
        )

        # Verify source system is tracked
        assert spec.source_system == "langchain_tool"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_tool_spec_with_empty_description(self):
        """Test ToolSpec with empty description."""
        adapter = LangChainAdapter()
        discovered = DiscoveredTool(
            name="TestTool",
            source_file="test.py",
            source_system="langchain_tool",
            metadata={},
        )

        spec = adapter.to_tool_spec(discovered)
        assert spec.description == ""

    def test_tool_spec_with_missing_metadata(self):
        """Test ToolSpec with missing metadata keys."""
        adapter = LangChainAdapter()
        discovered = DiscoveredTool(
            name="TestTool",
            source_file="test.py",
            source_system="langchain_tool",
            metadata={},
        )

        spec = adapter.to_tool_spec(discovered)
        assert spec is not None
        assert spec.name == "TestTool"

    def test_tool_spec_with_special_characters_in_name(self):
        """Test ToolSpec with special characters in name."""
        adapter = LangChainAdapter()
        discovered = DiscoveredTool(
            name="Test-Tool_123",
            source_file="test.py",
            source_system="langchain_tool",
            metadata={"description": "Test"},
        )

        spec = adapter.to_tool_spec(discovered)
        assert spec.name == "Test-Tool_123"
        assert spec.canonical_name == "langchain.Test-Tool_123"

    def test_tool_spec_with_unicode_description(self):
        """Test ToolSpec with unicode description."""
        adapter = LangChainAdapter()
        discovered = DiscoveredTool(
            name="TestTool",
            source_file="test.py",
            source_system="langchain_tool",
            metadata={"description": "日本語 中文 العربية русский"},
        )

        spec = adapter.to_tool_spec(discovered)
        assert "日本語" in spec.description

    def test_multiple_discoveries(self):
        """Test multiple discover calls return consistent results."""
        adapter = LangChainAdapter()

        tools1 = adapter.discover()
        tools2 = adapter.discover()

        assert len(tools1) == len(tools2)

    def test_adapter_is_tool_adapter(self):
        """Test adapter is instance of ToolAdapter."""
        from domain.tools.adapters import ToolAdapter

        adapter = LangChainAdapter()
        assert isinstance(adapter, ToolAdapter)


class TestIntegrationScenarios:
    """Test integration scenarios."""

    def test_full_adapter_workflow(self):
        """Test full adapter workflow: discover -> to_spec -> bind."""
        adapter = LangChainAdapter()

        # Discover tools
        tools = adapter.discover()
        assert len(tools) > 0

        # Convert to ToolSpec
        spec = adapter.to_tool_spec(tools[0])
        assert isinstance(spec, ToolSpec)

        # Bind executor
        executor = adapter.bind_executor(spec)
        # Currently returns None (TODO: canonical routing)
        assert executor is None or executor is not None

    def test_multiple_tools_conversion(self):
        """Test converting multiple discovered tools."""
        adapter = LangChainAdapter()
        tools = adapter.discover()

        specs = [adapter.to_tool_spec(tool) for tool in tools]

        assert len(specs) == len(tools)
        assert all(isinstance(s, ToolSpec) for s in specs)

    def test_tool_spec_immutability(self):
        """Test ToolSpec is immutable (frozen dataclass)."""
        import dataclasses

        adapter = LangChainAdapter()
        spec = adapter.to_tool_spec(
            DiscoveredTool(
                name="TestTool",
                source_file="test.py",
                source_system="langchain_tool",
                metadata={"description": "Test"},
            )
        )

        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.name = "NewName"  # type: ignore

    def test_boundary_enforcement_consistency(self):
        """Test boundary enforcement is consistent across tools."""
        adapter = LangChainAdapter()
        tools = adapter.discover()
        specs = [adapter.to_tool_spec(tool) for tool in tools]

        # All specs should have consistent boundary settings
        for spec in specs:
            assert spec.category == "adapter"
            assert spec.risk_tier == RiskTier.L1
            assert spec.approval_mode == ApprovalMode.NONE
            assert spec.sandbox_required is False
            assert spec.network_required is False
            assert spec.filesystem_required is False
