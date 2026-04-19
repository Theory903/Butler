"""Phase 6d + Phase 7 — Skills Hub, MCP Bridge, and Product Tiers tests.

Tests ButlerSkillsHub (intent matching, plan assembly, registration,
listing, categories), MCPBridgeAdapter (server registration, tool index,
call dispatch, not-found handling, outbound MCP format, parse incoming),
and ProductTiers (capability checks, tier ordering, config lookup,
capability listing).

All fully isolated — no real HTTP, no subprocess, no DB.

Verifies:
  1. SkillsHub: match("search") → research_and_summarize plan
  2. SkillsHub: match("remind") → set_reminder plan
  3. SkillsHub: match("unknown") → None
  4. SkillsHub: plan has correct step count
  5. SkillsHub: plan carries requires_approval from skill definition
  6. SkillsHub: plan resolved_params = passed context
  7. SkillsHub: register() adds new skill
  8. SkillsHub: get() retrieves skill by ID
  9. SkillsHub: list_skills() has all 5 built-ins
  10. SkillsHub: list_skills(category="research") filters correctly
  11. SkillsHub: list_categories() returns sorted unique categories
  12. SkillsHub: skill_count equals registered count
  13. MCPBridge: register_server indexes tools
  14. MCPBridge: find_tool returns registered tool
  15. MCPBridge: find_tool_any_server finds across servers
  16. MCPBridge: deregister_server removes tools from index
  17. MCPBridge: call_tool returns error for unknown tool
  18. MCPBridge: call_tool returns error for disabled server
  19. MCPBridge: call_tool dispatches with simulated transport
  20. MCPBridge: build_tools_list_response formats MCP response
  21. MCPBridge: parse_tool_call_request extracts tool_name + params
  22. MCPBridge: parse_tool_call_request returns None for wrong method
  23. MCPBridge: list_registered_tools returns all tools
  24. MCPBridge: list_servers returns server metadata
  25. ProductTiers: PERSONAL has web_search capability
  26. ProductTiers: PERSONAL lacks code_execution
  27. ProductTiers: PRO has code_execution
  28. ProductTiers: PRO lacks hipaa_mode
  29. ProductTiers: ENTERPRISE has hipaa_mode
  30. ProductTiers: ENTERPRISE has all PRO capabilities
  31. ProductTiers: check_capability allowed=True returns reason=""
  32. ProductTiers: check_capability allowed=False returns reason with tier name
  33. ProductTiers: get_tier_config returns TierConfig
  34. ProductTiers: capabilities_for_tier returns sorted list
  35. ProductTiers: ENTERPRISE rpm_limit > PRO > PERSONAL
  36. ProductTiers: unknown tier returns allowed=False
"""

from __future__ import annotations

import asyncio
import pytest

from services.tools.skills_hub import (
    ButlerSkillsHub,
    SkillDefinition,
    SkillTrigger,
    ToolStep,
    SkillExecutionPlan,
)
from services.tools.mcp_bridge import (
    MCPBridgeAdapter,
    MCPServerConfig,
    MCPTool,
    get_mcp_bridge,
)
from domain.policy.product_tiers import (
    ProductTier,
    CapabilityFlag,
    TierConfig,
    TIER_CONFIGS,
    check_capability,
    get_tier_config,
    capabilities_for_tier,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test 25: ButlerSkillsHub
# ─────────────────────────────────────────────────────────────────────────────

class TestButlerSkillsHub:

    def _hub(self) -> ButlerSkillsHub:
        return ButlerSkillsHub()

    def test_match_search_returns_research_plan(self):
        hub = self._hub()
        plan = hub.match("search", context={"user_message": "what is asyncio"})
        assert plan is not None
        assert plan.skill_id == "research_and_summarize"

    def test_match_remind_returns_reminder_plan(self):
        hub = self._hub()
        plan = hub.match("reminder", context={"user_message": "remind me at 9am"})
        assert plan is not None
        assert plan.skill_id == "set_reminder"

    def test_match_send_returns_send_message_plan(self):
        hub = self._hub()
        plan = hub.match("send", context={})
        assert plan is not None
        assert plan.skill_id == "send_message"

    def test_match_status_returns_check_status_plan(self):
        hub = self._hub()
        plan = hub.match("status")
        assert plan is not None
        assert plan.skill_id == "check_status"

    def test_match_unknown_returns_none(self):
        hub = self._hub()
        plan = hub.match("xyzzy_nonexistent")
        assert plan is None

    def test_plan_has_steps(self):
        hub = self._hub()
        plan = hub.match("search")
        assert len(plan.steps) >= 1

    def test_plan_resolved_params_from_context(self):
        hub = self._hub()
        ctx = {"user_message": "test query", "channel": "email"}
        plan = hub.match("send", context=ctx)
        assert plan.resolved_params == ctx

    def test_send_message_requires_approval(self):
        hub = self._hub()
        plan = hub.match("send")
        assert plan.requires_approval is True

    def test_search_does_not_require_approval(self):
        hub = self._hub()
        plan = hub.match("search")
        assert plan.requires_approval is False

    def test_register_custom_skill(self):
        hub = self._hub()
        custom = SkillDefinition(
            id="custom_test",
            name="Custom Test Skill",
            description="Test skill",
            version="1.0.0",
            trigger=SkillTrigger.INTENT_MATCH,
            intent_labels=["custom_test_intent"],
            steps=[ToolStep(tool_name="web_search", params_template={"query": "{user_message}"})],
            requires_tools=["web_search"],
            category="test",
        )
        hub.register(custom)
        plan = hub.match("custom_test_intent")
        assert plan is not None
        assert plan.skill_id == "custom_test"

    def test_get_returns_skill_by_id(self):
        hub = self._hub()
        skill = hub.get("research_and_summarize")
        assert skill is not None
        assert skill.name == "Research and Summarize"

    def test_get_missing_returns_none(self):
        hub = self._hub()
        assert hub.get("nonexistent_skill_xyz") is None

    def test_list_skills_returns_all_builtins(self):
        hub = self._hub()
        skills = hub.list_skills()
        assert len(skills) >= 5
        ids = {s["id"] for s in skills}
        assert "research_and_summarize" in ids
        assert "send_message" in ids
        assert "set_reminder" in ids

    def test_list_skills_category_filter(self):
        hub = self._hub()
        research = hub.list_skills(category="research")
        assert all(s["category"] == "research" for s in research)
        assert len(research) >= 1

    def test_list_categories_sorted(self):
        hub = self._hub()
        cats = hub.list_categories()
        assert cats == sorted(cats)

    def test_skill_count(self):
        hub = self._hub()
        assert hub.skill_count == 5  # 5 built-in skills

    def test_case_insensitive_match(self):
        hub = self._hub()
        plan = hub.match("SEARCH")
        assert plan is not None

    def test_analyst_intent_matches_read_and_analyze(self):
        hub = self._hub()
        plan = hub.match("analyze")
        assert plan is not None
        assert plan.skill_id == "read_and_analyze"


# ─────────────────────────────────────────────────────────────────────────────
# Test 26: MCPBridgeAdapter
# ─────────────────────────────────────────────────────────────────────────────

def _make_server(server_id="srv1", transport="http", url="http://localhost:9000") -> MCPServerConfig:
    tool = MCPTool(
        name="my_tool",
        description="A test tool",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        server_id=server_id,
    )
    return MCPServerConfig(
        server_id=server_id,
        name="Test MCP Server",
        transport=transport,
        url=url,
        tools=[tool],
    )


class TestMCPBridgeAdapter:

    def _bridge(self) -> MCPBridgeAdapter:
        return MCPBridgeAdapter()

    def test_register_server_indexes_tools(self):
        bridge = self._bridge()
        bridge.register_server(_make_server())
        assert bridge.find_tool("srv1", "my_tool") is not None

    def test_find_tool_returns_correct_tool(self):
        bridge = self._bridge()
        bridge.register_server(_make_server())
        tool = bridge.find_tool("srv1", "my_tool")
        assert tool.name == "my_tool"
        assert tool.server_id == "srv1"

    def test_find_tool_any_server_finds_across_servers(self):
        bridge = self._bridge()
        bridge.register_server(_make_server(server_id="srv1"))
        bridge.register_server(_make_server(server_id="srv2"))
        tool = bridge.find_tool_any_server("my_tool")
        assert tool is not None
        assert tool.name == "my_tool"

    def test_find_tool_missing_returns_none(self):
        bridge = self._bridge()
        assert bridge.find_tool("srv1", "nonexistent") is None

    def test_deregister_server_removes_tools(self):
        bridge = self._bridge()
        bridge.register_server(_make_server())
        count = bridge.deregister_server("srv1")
        assert count == 1
        assert bridge.find_tool("srv1", "my_tool") is None

    def test_deregister_missing_server_returns_zero(self):
        bridge = self._bridge()
        assert bridge.deregister_server("ghost_server") == 0

    def test_call_tool_not_found_returns_error(self):
        bridge = self._bridge()
        bridge.register_server(_make_server())
        result = asyncio.run(bridge.call_tool("srv1", "ghost_tool", {}))
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_call_tool_disabled_server_returns_error(self):
        bridge = self._bridge()
        config = _make_server()
        config.enabled = False
        bridge.register_server(config)
        result = asyncio.run(bridge.call_tool("srv1", "my_tool", {}))
        assert result.success is False

    def test_call_tool_simulated_transport(self):
        bridge = self._bridge()
        config = MCPServerConfig(
            server_id="sim",
            name="Simulated",
            transport="simulated",  # unknown → falls to default simulated path
            tools=[MCPTool(name="sim_tool", description="", input_schema={}, server_id="sim")],
        )
        bridge.register_server(config)
        result = asyncio.run(bridge.call_tool("sim", "sim_tool", {}))
        assert result.success is True
        assert len(result.content) >= 1

    def test_build_tools_list_response_format(self):
        bridge = self._bridge()
        butler_tools = [
            {"name": "web_search", "description": "Search the web", "input_schema": {"type": "object"}}
        ]
        resp = bridge.build_tools_list_response(butler_tools)
        assert "result" in resp
        assert "tools" in resp["result"]
        assert resp["result"]["tools"][0]["name"] == "web_search"
        assert resp["jsonrpc"] == "2.0"

    def test_parse_tool_call_request_valid(self):
        bridge = self._bridge()
        mcp_req = {
            "jsonrpc": "2.0",
            "id": "r1",
            "method": "tools/call",
            "params": {"name": "web_search", "arguments": {"query": "python"}},
        }
        result = bridge.parse_tool_call_request(mcp_req)
        assert result is not None
        tool_name, args = result
        assert tool_name == "web_search"
        assert args["query"] == "python"

    def test_parse_tool_call_request_wrong_method(self):
        bridge = self._bridge()
        mcp_req = {"method": "tools/list", "params": {}}
        assert bridge.parse_tool_call_request(mcp_req) is None

    def test_list_registered_tools(self):
        bridge = self._bridge()
        bridge.register_server(_make_server("srv1"))
        bridge.register_server(_make_server("srv2"))
        tools = bridge.list_registered_tools()
        assert len(tools) == 2

    def test_list_registered_tools_filtered_by_server(self):
        bridge = self._bridge()
        bridge.register_server(_make_server("srv1"))
        bridge.register_server(_make_server("srv2"))
        tools = bridge.list_registered_tools(server_id="srv1")
        assert all(t["server_id"] == "srv1" for t in tools)

    def test_list_servers(self):
        bridge = self._bridge()
        bridge.register_server(_make_server("srv1"))
        servers = bridge.list_servers()
        assert len(servers) == 1
        assert servers[0]["server_id"] == "srv1"

    def test_call_tool_returns_call_id(self):
        bridge = self._bridge()
        bridge.register_server(_make_server())
        result = asyncio.run(bridge.call_tool("srv1", "ghost_tool", {}))
        assert isinstance(result.call_id, str)
        assert len(result.call_id) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Test 27: ProductTiers
# ─────────────────────────────────────────────────────────────────────────────

class TestProductTiers:

    def test_personal_has_web_search(self):
        r = check_capability(ProductTier.PERSONAL, CapabilityFlag.WEB_SEARCH)
        assert r.allowed is True

    def test_personal_lacks_code_execution(self):
        r = check_capability(ProductTier.PERSONAL, CapabilityFlag.CODE_EXECUTION)
        assert r.allowed is False

    def test_personal_lacks_hipaa(self):
        r = check_capability(ProductTier.PERSONAL, CapabilityFlag.HIPAA_MODE)
        assert r.allowed is False

    def test_pro_has_code_execution(self):
        r = check_capability(ProductTier.PRO, CapabilityFlag.CODE_EXECUTION)
        assert r.allowed is True

    def test_pro_has_mcp_bridge(self):
        r = check_capability(ProductTier.PRO, CapabilityFlag.MCP_BRIDGE)
        assert r.allowed is True

    def test_pro_lacks_hipaa(self):
        r = check_capability(ProductTier.PRO, CapabilityFlag.HIPAA_MODE)
        assert r.allowed is False

    def test_enterprise_has_hipaa(self):
        r = check_capability(ProductTier.ENTERPRISE, CapabilityFlag.HIPAA_MODE)
        assert r.allowed is True

    def test_enterprise_has_fedramp(self):
        r = check_capability(ProductTier.ENTERPRISE, CapabilityFlag.FEDRAMP_MODE)
        assert r.allowed is True

    def test_enterprise_has_rbac(self):
        r = check_capability(ProductTier.ENTERPRISE, CapabilityFlag.RBAC)
        assert r.allowed is True

    def test_enterprise_includes_all_pro_capabilities(self):
        """Every PRO capability must be present in ENTERPRISE."""
        pro = TIER_CONFIGS[ProductTier.PRO].capabilities
        ent = TIER_CONFIGS[ProductTier.ENTERPRISE].capabilities
        assert pro.issubset(ent)

    def test_pro_includes_all_personal_capabilities(self):
        """Every PERSONAL capability must be present in PRO."""
        personal = TIER_CONFIGS[ProductTier.PERSONAL].capabilities
        pro = TIER_CONFIGS[ProductTier.PRO].capabilities
        assert personal.issubset(pro)

    def test_check_capability_allowed_reason_empty(self):
        r = check_capability(ProductTier.ENTERPRISE, CapabilityFlag.HIPAA_MODE)
        assert r.reason == ""

    def test_check_capability_denied_reason_has_tier(self):
        r = check_capability(ProductTier.PERSONAL, CapabilityFlag.CODE_EXECUTION)
        assert "personal" in r.reason.lower() or "pro" in r.reason.lower()

    def test_get_tier_config_returns_config(self):
        cfg = get_tier_config(ProductTier.PRO)
        assert cfg is not None
        assert cfg.tier == ProductTier.PRO
        assert cfg.rpm_limit == 100_000

    def test_get_tier_config_unknown_returns_none(self):
        assert get_tier_config("nonexistent_tier") is None  # type: ignore[arg-type]

    def test_capabilities_for_tier_sorted(self):
        caps = capabilities_for_tier(ProductTier.PERSONAL)
        assert caps == sorted(caps)

    def test_rpm_limit_ordering(self):
        personal_rpm = TIER_CONFIGS[ProductTier.PERSONAL].rpm_limit
        pro_rpm = TIER_CONFIGS[ProductTier.PRO].rpm_limit
        enterprise_rpm = TIER_CONFIGS[ProductTier.ENTERPRISE].rpm_limit
        assert personal_rpm < pro_rpm < enterprise_rpm

    def test_unknown_tier_check_returns_not_allowed(self):
        r = check_capability("fake_tier", CapabilityFlag.WEB_SEARCH)  # type: ignore[arg-type]
        assert r.allowed is False

    def test_enterprise_unlimited_users(self):
        cfg = get_tier_config(ProductTier.ENTERPRISE)
        assert cfg.max_users == -1

    def test_personal_single_device(self):
        cfg = get_tier_config(ProductTier.PERSONAL)
        assert cfg.max_devices == 1
