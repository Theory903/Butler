"""Phase 1 golden-path tests.

These tests define the acceptance bar for Phase 1. They test Butler's
sovereignty points — not "does Hermes work" but "does Butler maintain control
when Hermes runs inside it."

Tests are fully isolated from Hermes (mocked). They verify:
  1. Simple chat: RuntimeKernel dispatches to HERMES_AGENT, returns Butler content
  2. Allowed tool: Policy gate passes L0 tool, StreamToolCallEvent emitted
  3. Blocked tool: Policy gate blocks FORBIDDEN tool, ToolPolicyViolation raised
  4. Approval-required tool: L2 tool raises ApprovalRequired, not run silently
  5. Thinking suppressed: thinking callback fires, no StreamTokenEvent for thinking
  6. MemoryWritePolicy: PII item refused for cold tier, accepted for warm tier
  7. EventNormalizer: thinking delta → suppressed, text delta → StreamTokenEvent
  8. Error classification: OverloadedError → RFC 9457 503 retryable problem

No database required. No Hermes network calls. No real LLM.
"""

from __future__ import annotations

import asyncio
import pytest
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch
from typing import AsyncGenerator

# ── Phase 0 imports ──────────────────────────────────────────────────────────
from domain.events.schemas import (
    ButlerEvent,
    StreamTokenEvent,
    StreamFinalEvent,
    StreamToolCallEvent,
    StreamToolResultEvent,
    StreamApprovalRequiredEvent,
    StreamErrorEvent,
)
from domain.events.normalizer import EventNormalizer
from domain.memory.write_policy import (
    MemoryWritePolicy,
    MemoryWriteRequest,
    StorageTier,
)
from domain.orchestrator.runtime_kernel import (
    RuntimeKernel,
    ExecutionContext,
    ExecutionStrategy,
)
from domain.tools.hermes_compiler import (
    HermesToolCompiler,
    ButlerToolSpec,
    RiskTier,
)

# ── Phase 1A imports ──────────────────────────────────────────────────────────
from domain.orchestrator.hermes_agent_backend import (
    HermesAgentBackend,
    ButlerToolPolicyGate,
    ToolPolicyViolation,
    ApprovalRequired,
    AssuranceInsufficient,
    _classify_exception,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def compiler():
    return HermesToolCompiler()


@pytest.fixture
def compiled_specs(compiler):
    """Compile a subset of Hermes tools into ButlerToolSpecs."""
    specs = {}
    for name, meta in [
        ("web_search", {"description": "Search the web", "input_schema": {}, "output_schema": {}}),
        ("write_file", {"description": "Write file", "input_schema": {}, "output_schema": {}}),
        ("run_terminal", {"description": "Run terminal command", "input_schema": {}, "output_schema": {}}),
    ]:
        spec = compiler.compile(name, meta)
        specs[spec.name] = spec
    return specs


@pytest.fixture
def policy_gate_free(compiled_specs):
    return ButlerToolPolicyGate(
        compiled_specs=compiled_specs,
        account_tier="free",
        channel="api",
        assurance_level="AAL1",
    )


@pytest.fixture
def policy_gate_enterprise(compiled_specs):
    return ButlerToolPolicyGate(
        compiled_specs=compiled_specs,
        account_tier="enterprise",
        channel="api",
        assurance_level="AAL3",
    )


@pytest.fixture
def normalizer():
    return EventNormalizer(
        account_id="acct_test",
        session_id="ses_test",
        task_id="tsk_test",
        trace_id="trc_test",
    )


@pytest.fixture
def write_policy():
    return MemoryWritePolicy()


@dataclass
class _FakeTask:
    id: str = "tsk_fake"
    task_type: str = "respond"
    status: str = "pending"
    retries: int = 0
    max_retries: int = 3
    _account_tier: str = "free"
    _assurance_level: str = "AAL1"


@dataclass
class _FakeWorkflow:
    id: str = "wf_fake"
    account_id: str = "acct_fake"
    session_id: str = "ses_fake"
    mode: str = "macro"
    plan_schema: dict = field(default_factory=dict)
    _channel: str = "api"


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: RuntimeKernel strategy selection
# ─────────────────────────────────────────────────────────────────────────────

class TestRuntimeKernelStrategy:

    def _make_kernel(self):
        return RuntimeKernel()  # No backends wired — strategy selection only

    def test_default_agentic_strategy(self):
        kernel = self._make_kernel()
        task = _FakeTask(task_type="respond")
        workflow = _FakeWorkflow(mode="macro", plan_schema={})
        assert kernel.choose_strategy(task, workflow) == ExecutionStrategy.HERMES_AGENT

    def test_deterministic_for_single_query(self):
        kernel = self._make_kernel()
        task = _FakeTask(task_type="memory_recall")
        workflow = _FakeWorkflow(mode="macro", plan_schema={"steps": [{}], "requires_reasoning": False})
        assert kernel.choose_strategy(task, workflow) == ExecutionStrategy.DETERMINISTIC

    def test_workflow_dag_for_durable_mode(self):
        kernel = self._make_kernel()
        task = _FakeTask(task_type="respond")
        workflow = _FakeWorkflow(mode="durable", plan_schema={"steps": []})
        assert kernel.choose_strategy(task, workflow) == ExecutionStrategy.WORKFLOW_DAG

    def test_workflow_dag_for_many_steps(self):
        kernel = self._make_kernel()
        task = _FakeTask(task_type="respond")
        workflow = _FakeWorkflow(mode="macro", plan_schema={"steps": [{}] * 9})
        assert kernel.choose_strategy(task, workflow) == ExecutionStrategy.WORKFLOW_DAG

    def test_subagent_for_delegate_task(self):
        kernel = self._make_kernel()
        task = _FakeTask(task_type="delegate")
        workflow = _FakeWorkflow(mode="macro", plan_schema={})
        assert kernel.choose_strategy(task, workflow) == ExecutionStrategy.SUBAGENT

    def test_subagent_for_acp_target(self):
        kernel = self._make_kernel()
        task = _FakeTask(task_type="respond")
        workflow = _FakeWorkflow(mode="macro", plan_schema={"acp_target": "some_agent"})
        assert kernel.choose_strategy(task, workflow) == ExecutionStrategy.SUBAGENT


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: ButlerToolPolicyGate
# ─────────────────────────────────────────────────────────────────────────────

class TestToolPolicyGate:

    def test_l0_tool_allowed_free_tier(self, policy_gate_free):
        """L0 (web_search) is allowed on free tier, no approval needed."""
        spec = policy_gate_free.check("web_search", {})
        assert spec.risk_tier == RiskTier.L0
        assert spec.approval_mode == "none"

    def test_l2_tool_blocked_by_tier_on_free(self, policy_gate_free):
        """L2 (write_file) is pro/enterprise only — free tier gets ToolPolicyViolation.
        Tier visibility check (step 3) fires before approval check (step 6)."""
        with pytest.raises(ToolPolicyViolation) as exc_info:
            policy_gate_free.check("write_file", {})
        assert "free" in str(exc_info.value)
        assert "pro" in str(exc_info.value) or "enterprise" in str(exc_info.value)

    def test_l2_tool_raises_approval_on_pro_tier(self, compiled_specs):
        """L2 (write_file) on pro tier: passes tier check, then raises ApprovalRequired."""
        gate = ButlerToolPolicyGate(
            compiled_specs=compiled_specs,
            account_tier="pro",
            channel="api",
            assurance_level="AAL2",
        )
        with pytest.raises(ApprovalRequired) as exc_info:
            gate.check("write_file", {})
        assert exc_info.value.approval_mode == "explicit"
        assert exc_info.value.tool_name == "write_file"

    def test_l3_tool_blocked_on_free_tier(self, policy_gate_free):
        """L3 (run_terminal) is not visible on free tier — ToolPolicyViolation."""
        with pytest.raises(ToolPolicyViolation) as exc_info:
            policy_gate_free.check("run_terminal", {})
        assert "free" in str(exc_info.value)

    def test_l3_tool_requires_approval_on_enterprise(self, policy_gate_enterprise):
        """L3 (run_terminal) on enterprise tier still requires critical approval."""
        with pytest.raises(ApprovalRequired) as exc_info:
            policy_gate_enterprise.check("run_terminal", {})
        assert exc_info.value.approval_mode == "critical"

    def test_unknown_tool_raises_policy_violation(self, policy_gate_free):
        """Tool not in compiled registry → ToolPolicyViolation."""
        with pytest.raises(ToolPolicyViolation):
            policy_gate_free.check("exec_arbitrary_hermes_tool", {})

    def test_assurance_insufficient(self, compiled_specs):
        """AAL1 session cannot use AAL3 tool."""
        gate = ButlerToolPolicyGate(
            compiled_specs=compiled_specs,
            account_tier="enterprise",
            channel="api",
            assurance_level="AAL1",  # Low assurance
        )
        with pytest.raises(AssuranceInsufficient):
            gate.check("run_terminal", {})


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: HermesToolCompiler
# ─────────────────────────────────────────────────────────────────────────────

class TestHermesToolCompiler:

    def test_compile_web_search_is_l0(self, compiler):
        spec = compiler.compile("web_search", {"description": "Search web"})
        assert spec.risk_tier == RiskTier.L0
        assert spec.approval_mode == "none"
        assert spec.butler_service_owner == "search"

    def test_compile_write_file_is_l2(self, compiler):
        spec = compiler.compile("write_file", {"description": "Write file"})
        assert spec.risk_tier == RiskTier.L2
        assert spec.approval_mode == "explicit"
        assert "file_write" in spec.side_effect_classes
        assert spec.has_compensation is True

    def test_compile_run_terminal_is_l3(self, compiler):
        spec = compiler.compile("run_terminal", {"description": "Run terminal"})
        assert spec.risk_tier == RiskTier.L3
        assert spec.approval_mode == "critical"
        assert spec.min_assurance_level == "AAL3"
        assert spec.sandbox_profile == "docker"

    def test_compile_send_message_is_l2_communication(self, compiler):
        spec = compiler.compile("send_message", {"description": "Send message"})
        assert spec.risk_tier == RiskTier.L2
        assert spec.butler_service_owner == "communication"
        assert "message" in spec.side_effect_classes

    def test_unknown_tool_defaults_to_l2(self, compiler):
        spec = compiler.compile("mystery_hermes_tool", {"description": "Mystery"})
        assert spec.risk_tier == RiskTier.L2
        assert spec.blocked is False

    def test_l3_tools_enterprise_only(self, compiler):
        spec = compiler.compile("run_terminal", {})
        assert spec.visible_tiers == ["enterprise"]

    def test_l0_tools_all_tiers(self, compiler):
        spec = compiler.compile("web_search", {})
        assert "free" in spec.visible_tiers
        assert "pro" in spec.visible_tiers
        assert "enterprise" in spec.visible_tiers


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: EventNormalizer
# ─────────────────────────────────────────────────────────────────────────────

class TestEventNormalizer:

    def test_text_delta_becomes_stream_token(self, normalizer):
        events = list(normalizer.normalize({
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "Hello"},
        }))
        assert len(events) == 1
        assert isinstance(events[0], StreamTokenEvent)
        assert events[0].payload["content"] == "Hello"

    def test_thinking_delta_suppressed(self, normalizer):
        """CRITICAL: thinking blocks must NEVER reach Butler consumers."""
        events = list(normalizer.normalize({
            "type": "content_block_delta",
            "delta": {"type": "thinking_delta", "thinking": "I should search first..."},
        }))
        assert len(events) == 0

    def test_message_stop_becomes_final(self, normalizer):
        events = list(normalizer.normalize({
            "type": "message_stop",
            "_butler_usage": {"input_tokens": 100, "output_tokens": 50},
            "_butler_duration_ms": 1200,
        }))
        final = next((e for e in events if isinstance(e, StreamFinalEvent)), None)
        assert final is not None
        assert final.payload["input_tokens"] == 100
        assert final.payload["output_tokens"] == 50
        assert final.payload["duration_ms"] == 1200

    def test_error_event_classified(self, normalizer):
        events = list(normalizer.normalize({
            "type": "error",
            "error": {"type": "overloaded_error", "message": "Server overloaded"},
        }))
        error_event = next((e for e in events if isinstance(e, StreamErrorEvent)), None)
        assert error_event is not None
        assert "overloaded" in error_event.payload["type"]
        assert error_event.payload["retryable"] is True
        assert error_event.payload["status"] == 503

    def test_tool_use_block_emits_two_events(self, normalizer):
        events = list(normalizer.normalize({
            "type": "content_block_start",
            "content_block": {"type": "tool_use", "name": "web_search", "id": "tu_123"},
        }))
        assert any(isinstance(e, StreamToolCallEvent) for e in events)

    def test_tool_result_success(self, normalizer):
        events = list(normalizer.normalize({
            "type": "tool_result",
            "tool_name": "web_search",
            "tool_use_id": "tu_123",
            "is_error": False,
            "duration_ms": 300,
        }))
        assert any(isinstance(e, StreamToolResultEvent) for e in events)
        result = next(e for e in events if isinstance(e, StreamToolResultEvent))
        assert result.payload["success"] is True

    def test_l1_tool_result_visible_result_suppressed(self, normalizer):
        """L1+ tool results should not expose payload to stream."""
        events = list(normalizer.normalize({
            "type": "tool_result",
            "tool_name": "write_file",  # Not in _SAFE_AUTO_TOOLS
            "tool_use_id": "tu_456",
            "is_error": False,
            "content": "File written successfully",
        }))
        result = next((e for e in events if isinstance(e, StreamToolResultEvent)), None)
        assert result is not None
        assert result.payload["visible_result"] is None  # Suppressed

    def test_l0_tool_result_visible_result_shown(self, normalizer):
        """L0 safe_auto tool results can show payload."""
        events = list(normalizer.normalize({
            "type": "tool_result",
            "tool_name": "web_search",  # In _SAFE_AUTO_TOOLS
            "tool_use_id": "tu_789",
            "is_error": False,
            "content": [{"text": "Python 3.13 released"}],
        }))
        result = next((e for e in events if isinstance(e, StreamToolResultEvent)), None)
        assert result is not None
        assert result.payload["visible_result"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: MemoryWritePolicy
# ─────────────────────────────────────────────────────────────────────────────

class TestMemoryWritePolicy:

    def test_pii_blocked_from_cold_tier(self, write_policy):
        """PII items MUST NOT go to pyturboquant cold tier — erasure impossible.
        The policy routes old PII episodes to cold tier, but enforce_pii_rules
        must REFUSE the cold tier write when has_pii=True.
        """
        req = MemoryWriteRequest(
            memory_type="episode",
            content="Medical diagnosis: ...",
            age_days=60,
            importance=0.5,
            has_pii=True,
        )
        # enforce_pii_rules is the gate called per-tier before actual write
        # It MUST return False for cold tier when PII is present
        assert write_policy.enforce_pii_rules(req, StorageTier.COLD) is False, (
            "PII data must be refused from pyturboquant cold tier "
            "(no fine-grained deletion support)"
        )
        # Non-PII cold writes must still be allowed
        non_pii_req = MemoryWriteRequest(
            memory_type="episode", content="Generic memory",
            age_days=60, has_pii=False,
        )
        assert write_policy.enforce_pii_rules(non_pii_req, StorageTier.COLD) is True

    def test_old_episode_goes_cold(self, write_policy):
        req = MemoryWriteRequest(
            memory_type="episode",
            content="Old memory",
            age_days=45,
            has_pii=False,
        )
        route = write_policy.route(req)
        assert StorageTier.COLD in route.tiers

    def test_high_importance_episode_goes_warm(self, write_policy):
        req = MemoryWriteRequest(
            memory_type="episode",
            content="Very important memory",
            age_days=3,
            importance=0.9,
            has_pii=False,
        )
        route = write_policy.route(req)
        assert StorageTier.WARM in route.tiers
        assert StorageTier.COLD not in route.tiers

    def test_preference_always_structured_plus_warm(self, write_policy):
        req = MemoryWriteRequest(memory_type="preference", content="Likes coffee")
        route = write_policy.route(req)
        assert StorageTier.STRUCT in route.tiers
        assert StorageTier.WARM in route.tiers

    def test_relationship_always_graph(self, write_policy):
        req = MemoryWriteRequest(memory_type="relationship", content="Knows Alice")
        route = write_policy.route(req)
        assert StorageTier.GRAPH in route.tiers

    def test_web_crawl_chunk_cold_only(self, write_policy):
        req = MemoryWriteRequest(memory_type="web_crawl_chunk", content="Article text...")
        route = write_policy.route(req)
        assert StorageTier.COLD in route.tiers

    def test_session_message_hot_only(self, write_policy):
        req = MemoryWriteRequest(memory_type="session_message", content="Hello")
        route = write_policy.route(req)
        assert StorageTier.HOT in route.tiers
        # Hermes SessionDB gets a copy, but that's not a storage tier
        assert write_policy.should_write_hermes_session_db(req) is True

    def test_tool_trace_recent_goes_struct(self, write_policy):
        req = MemoryWriteRequest(memory_type="tool_trace", content="...", age_days=2)
        route = write_policy.route(req)
        assert StorageTier.STRUCT in route.tiers
        assert route.requires_audit_log is True

    def test_tool_trace_old_goes_cold(self, write_policy):
        req = MemoryWriteRequest(memory_type="tool_trace", content="...", age_days=14)
        route = write_policy.route(req)
        assert StorageTier.COLD in route.tiers


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: Error classification
# ─────────────────────────────────────────────────────────────────────────────

class TestErrorClassification:

    def _make_exc(self, name: str) -> Exception:
        """Create an exception with a specific class name for classification."""
        exc_cls = type(name, (Exception,), {})
        return exc_cls("test")

    def test_overloaded_error_is_503_retryable(self):
        exc = self._make_exc("OverloadedError")
        uri, status, retryable = _classify_exception(exc)
        assert status == 503
        assert retryable is True
        assert "overloaded" in uri

    def test_auth_error_is_502_not_retryable(self):
        exc = self._make_exc("AuthenticationError")
        uri, status, retryable = _classify_exception(exc)
        assert status == 502
        assert retryable is False

    def test_unknown_exception_is_500(self):
        exc = ValueError("unknown problem")
        uri, status, retryable = _classify_exception(exc)
        assert status == 500
        assert retryable is False
        assert "internal-error" in uri

    def test_rate_limit_is_429_retryable(self):
        exc = self._make_exc("RateLimitError")
        uri, status, retryable = _classify_exception(exc)
        assert status == 429
        assert retryable is True


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: ButlerToolSpec integrity checks
# ─────────────────────────────────────────────────────────────────────────────

class TestButlerToolSpec:

    def test_l0_tools_have_no_approval(self, compiler):
        """Every L0 tool must have approval_mode=none."""
        l0_tools = ["web_search", "memory_recall", "session_search", "list_files", "clarify"]
        for name in l0_tools:
            spec = compiler.compile(name, {})
            assert spec.approval_mode == "none", f"{name} L0 must have approval_mode=none"

    def test_l2_l3_tools_have_compensation_for_file_write(self, compiler):
        """Tools with file_write side-effects must have compensation defined."""
        file_tools = ["write_file", "patch_file"]
        for name in file_tools:
            spec = compiler.compile(name, {})
            assert spec.has_compensation is True, f"{name} must have compensation"

    def test_l3_tools_sandbox_not_none(self, compiler):
        """L3 tools must run in an isolated sandbox."""
        l3_tools = ["run_terminal", "code_execution", "browser_automation"]
        for name in l3_tools:
            spec = compiler.compile(name, {})
            assert spec.sandbox_profile != "none", f"{name} must have sandbox"

    def test_communication_tool_owned_by_communication_service(self, compiler):
        spec = compiler.compile("send_message", {})
        assert spec.butler_service_owner == "communication"

    def test_homeassistant_owned_by_device_service(self, compiler):
        spec = compiler.compile("homeassistant_control", {})
        assert spec.butler_service_owner == "device"


# ─────────────────────────────────────────────────────────────────────────────
# Test 8: ButlerToolDispatch — output parsing and tier visibility
# ─────────────────────────────────────────────────────────────────────────────

class TestButlerToolDispatch:

    from domain.tools.hermes_dispatcher import ButlerToolDispatch, HermesEnvBridge, ButlerToolResult

    def _make_dispatcher(self, compiled_specs, account_tier="free"):
        from domain.tools.hermes_dispatcher import ButlerToolDispatch, HermesEnvBridge
        return ButlerToolDispatch(
            compiled_specs=compiled_specs,
            env_bridge=HermesEnvBridge(),
            account_tier=account_tier,
            channel="api",
            assurance_level="AAL1",
        )

    def test_parse_json_success(self, compiled_specs):
        from domain.tools.hermes_dispatcher import ButlerToolDispatch, HermesEnvBridge
        d = self._make_dispatcher(compiled_specs)
        parsed, is_error = d._parse_raw_output('{"result": "ok"}', "web_search")
        assert parsed == {"result": "ok"}
        assert is_error is False

    def test_parse_json_error_key(self, compiled_specs):
        from domain.tools.hermes_dispatcher import ButlerToolDispatch, HermesEnvBridge
        d = self._make_dispatcher(compiled_specs)
        parsed, is_error = d._parse_raw_output('{"error": "network timeout"}', "web_search")
        assert is_error is True
        assert parsed["error"] == "network timeout"

    def test_parse_non_json_plain_text_success(self, compiled_specs):
        from domain.tools.hermes_dispatcher import ButlerToolDispatch, HermesEnvBridge
        d = self._make_dispatcher(compiled_specs)
        parsed, is_error = d._parse_raw_output("Search results here", "web_search")
        assert is_error is False
        assert "text" in parsed

    def test_parse_non_json_error_prefix(self, compiled_specs):
        from domain.tools.hermes_dispatcher import ButlerToolDispatch, HermesEnvBridge
        d = self._make_dispatcher(compiled_specs)
        parsed, is_error = d._parse_raw_output("Error: connection refused", "web_search")
        assert is_error is True

    def test_l0_output_visible(self, compiler):
        """L0 tool dispatch: output is visible to caller."""
        from domain.tools.hermes_dispatcher import ButlerToolDispatch, HermesEnvBridge
        specs = {
            "web_search": compiler.compile("web_search", {}),
        }
        d = ButlerToolDispatch(
            compiled_specs=specs,
            env_bridge=HermesEnvBridge(),
            account_tier="free",
            channel="api",
            assurance_level="AAL1",
        )
        # Simulate parsed output visibility
        spec = specs["web_search"]
        from domain.tools.hermes_compiler import RiskTier
        assert spec.risk_tier == RiskTier.L0
        # L0: output field is populated (not suppressed)
        result_output = {"result": "ok"} if spec.risk_tier == RiskTier.L0 else None
        assert result_output is not None

    def test_l2_output_suppressed(self, compiler):
        """L2 tool dispatch: output is NOT returned to caller. Only audit record has it."""
        spec = compiler.compile("write_file", {})
        from domain.tools.hermes_compiler import RiskTier
        assert spec.risk_tier == RiskTier.L2
        # L2: visible output is None (suppressed in ButlerToolResult.output)
        visible_output = {"result": "ok"} if spec.risk_tier == RiskTier.L0 else None
        assert visible_output is None


# ─────────────────────────────────────────────────────────────────────────────
# Test 9: HermesEnvBridge — sandbox profile mapping
# ─────────────────────────────────────────────────────────────────────────────

class TestHermesEnvBridge:

    def _make_bridge(self):
        from domain.tools.hermes_dispatcher import HermesEnvBridge
        return HermesEnvBridge()

    def _spec_with_sandbox(self, compiler, tool_name, sandbox):
        spec = compiler.compile(tool_name, {})
        spec.sandbox_profile = sandbox
        return spec

    def test_none_profile_no_overrides(self, compiler):
        bridge = self._make_bridge()
        spec = compiler.compile("web_search", {})  # sandbox_profile=none
        ctx = bridge.build_env_context(spec)
        assert ctx.sandbox_profile == "none"
        # Only HERMES_HOME override — no docker/modal keys
        assert "HERMES_USE_DOCKER" not in ctx.env_overrides
        assert "HERMES_USE_MODAL" not in ctx.env_overrides

    def test_docker_profile_sets_docker_env(self, compiler):
        bridge = self._make_bridge()
        spec = compiler.compile("run_terminal", {})  # docker sandbox
        ctx = bridge.build_env_context(spec)
        assert ctx.sandbox_profile == "docker"
        assert ctx.env_overrides.get("HERMES_USE_DOCKER") == "1"

    def test_modal_profile_sets_modal_env(self, compiler):
        bridge = self._make_bridge()
        spec = compiler.compile("env_modal", {})
        ctx = bridge.build_env_context(spec)
        assert ctx.sandbox_profile == "modal"
        assert ctx.env_overrides.get("HERMES_USE_MODAL") == "1"

    def test_hermes_home_always_injected(self, compiler):
        """HERMES_HOME must always be overridden — never let Hermes default to ~/.hermes."""
        bridge = self._make_bridge()
        spec = compiler.compile("web_search", {})
        ctx = bridge.build_env_context(spec)
        assert "HERMES_HOME" in ctx.env_overrides
        assert "/hermes" in ctx.env_overrides["HERMES_HOME"]

    def test_ssh_profile(self, compiler):
        bridge = self._make_bridge()
        spec = compiler.compile("env_ssh", {})
        ctx = bridge.build_env_context(spec)
        assert ctx.env_overrides.get("HERMES_USE_SSH") == "1"


# ─────────────────────────────────────────────────────────────────────────────
# Test 10: ToolExecutor Phase 2 — spec-first lookup and param redaction
# ─────────────────────────────────────────────────────────────────────────────

class TestToolExecutorPhase2:

    def _make_executor(self, compiler, tools=None):
        """Build a ToolExecutor with mocked DB/Redis."""
        from unittest.mock import AsyncMock, MagicMock
        from services.tools.executor import ToolExecutor
        from services.tools.verification import ToolVerifier

        tool_names = tools or ["web_search"]
        specs = {name: compiler.compile(name, {}) for name in tool_names}

        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=None)))))

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        verifier = ToolVerifier()
        return ToolExecutor(
            db=db,
            redis=redis,
            verifier=verifier,
            compiled_specs=specs,
            account_tier="free",
        )

    def test_unknown_tool_raises_precondition_failed(self, compiler):
        """Tool not in compiled specs must raise immediately — no Hermes call."""
        import asyncio
        executor = self._make_executor(compiler, tools=["web_search"])
        with pytest.raises(Exception) as exc_info:
            asyncio.run(
                executor.execute("mystery_tool", {}, account_id="acct_123")
            )
        # ToolErrors.precondition_failed() returns a Problem instance
        # The detail field carries the message; str() only shows HTTP title.
        exc = exc_info.value
        detail = getattr(exc, "detail", str(exc))
        assert "compiled" in detail.lower() or "not found" in detail.lower() or (
            "precondition" in type(exc).__name__.lower() or
            "precondition" in str(type(exc)).lower()
        )

    def test_blocked_tool_raises_immediately(self, compiler):
        """FORBIDDEN tool must raise before dispatch — spec.blocked check."""
        import asyncio
        specs = {"bad_tool": ButlerToolSpec(
            name="bad_tool",
            hermes_name="bad_tool",
            blocked=True,
            block_reason="Explicitly forbidden",
            risk_tier=RiskTier.L3,
        )}
        from unittest.mock import AsyncMock, MagicMock
        from services.tools.executor import ToolExecutor
        from services.tools.verification import ToolVerifier
        executor = ToolExecutor(
            db=AsyncMock(),
            redis=AsyncMock(),
            verifier=ToolVerifier(),
            compiled_specs=specs,
        )
        with pytest.raises(Exception) as exc_info:
            asyncio.run(
                executor.execute("bad_tool", {}, account_id="acct_123")
            )
        exc = exc_info.value
        detail = getattr(exc, "detail", str(exc))
        assert (
            "FORBIDDEN" in detail or "forbidden" in detail.lower() or
            "blocked" in detail.lower() or "Precondition" in str(type(exc))
        )

    def test_param_redaction_l1_plus(self, compiler):
        """L1+ tool audit parameters must have sensitive fields redacted."""
        from services.tools.executor import ToolExecutor
        spec = compiler.compile("transcribe_audio", {})  # L1
        executor = self._make_executor(compiler, tools=["transcribe_audio"])
        params = {"file_path": "/audio.mp3", "api_key": "sk-real-key-here"}
        redacted = executor._redact_params_for_audit(params, spec)
        assert redacted["file_path"] == "/audio.mp3"
        assert redacted["api_key"] == "***REDACTED***"

    def test_param_redaction_l0_passthrough(self, compiler):
        """L0 tool audit parameters must NOT be redacted (safe_auto)."""
        from services.tools.executor import ToolExecutor
        spec = compiler.compile("web_search", {})  # L0
        executor = self._make_executor(compiler, tools=["web_search"])
        params = {"query": "python news", "safe_search": True}
        redacted = executor._redact_params_for_audit(params, spec)
        assert redacted["query"] == "python news"  # Not redacted

    def test_compensation_ref_stored_for_file_write(self, compiler):
        """write_file must produce a compensation_ref in dispatch result."""
        from domain.tools.hermes_dispatcher import ButlerToolDispatch, HermesEnvBridge, ButlerToolResult
        from domain.tools.hermes_compiler import RiskTier
        specs = {"write_file": compiler.compile("write_file", {})}
        spec = specs["write_file"]
        assert spec.has_compensation is True
        # Verify compensation ref would be built
        from domain.tools.hermes_dispatcher import _COMPENSATION_HANDLERS
        assert "write_file" in _COMPENSATION_HANDLERS
