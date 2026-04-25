from services.tools.registry import ToolRegistry, ToolSpec


def test_tool_spec_risk_tier():
    spec = ToolSpec(name="test", description="test tool", risk_tier=0)
    assert spec.risk_tier == 0

    spec_high = ToolSpec(name="delete", description="delete", risk_tier=4)
    assert spec_high.risk_tier == 4


def test_tool_registry():
    registry = ToolRegistry
    tool = registry.get_tool("nonexistent")
    assert tool is None
