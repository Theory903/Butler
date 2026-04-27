"""Tool Policy Enforcement Tests.

Tests for the ToolPolicy domain class and ToolPolicyService service layer.
Verifies that tool execution is properly governed by policy rules.
"""

from __future__ import annotations

import pytest

from domain.runtime.context import RuntimeContext
from domain.tools.policy import (
    ApprovalMode,
    RiskTier,
    ToolPolicy,
    ToolPolicyDecision,
)
from domain.tools.spec import ToolSpec


@pytest.fixture
def l0_safe_tool() -> ToolSpec:
    """Create a safe L0 tool spec."""
    return ToolSpec.l0_safe(
        name="safe_tool",
        canonical_name="butler.safe_tool",
        owner="butler",
        category="utility",
    )


@pytest.fixture
def l2_write_tool() -> ToolSpec:
    """Create a write L2 tool spec."""
    return ToolSpec.l2_write(
        name="write_tool",
        canonical_name="butler.write_tool",
        owner="butler",
        category="filesystem",
    )


@pytest.fixture
def l3_destructive_tool() -> ToolSpec:
    """Create a destructive L3 tool spec."""
    return ToolSpec.l3_destructive(
        name="destructive_tool",
        canonical_name="butler.destructive_tool",
        owner="butler",
        category="system",
    )


@pytest.fixture
def l4_critical_tool() -> ToolSpec:
    """Create a critical L4 tool spec."""
    return ToolSpec.l4_critical(
        name="critical_tool",
        canonical_name="butler.critical_tool",
        owner="butler",
        category="security",
    )


@pytest.fixture
def valid_context() -> RuntimeContext:
    """Create a valid runtime context."""
    return RuntimeContext.create(
        tenant_id="tenant_123",
        account_id="account_456",
        session_id="session_789",
        request_id="req_abc",
        trace_id="trace_xyz",
        channel="api",
        user_id="user_123",
    )


class TestToolPolicy:
    """Tests for ToolPolicy domain class."""

    def test_allow_l0_tool_with_valid_context(
        self, l0_safe_tool: ToolSpec, valid_context: RuntimeContext
    ) -> None:
        """L0 tools should be allowed with valid context."""
        policy = ToolPolicy()
        decision = policy.evaluate(
            context=valid_context,
            spec=l0_safe_tool,
            user_permissions=frozenset(),
            approval_id=None,
        )
        assert decision.allowed is True
        assert decision.requires_approval is False
        assert decision.requires_sandbox is False

    def test_l2_tool_requires_approval(
        self, l2_write_tool: ToolSpec, valid_context: RuntimeContext
    ) -> None:
        """L2 tools should require approval by default."""
        policy = ToolPolicy()
        decision = policy.evaluate(
            context=valid_context,
            spec=l2_write_tool,
            user_permissions=frozenset(),
            approval_id=None,
        )
        assert decision.allowed is False
        assert decision.requires_approval is True
        assert decision.requires_sandbox is True

    def test_l2_tool_allowed_with_approval(
        self, l2_write_tool: ToolSpec, valid_context: RuntimeContext
    ) -> None:
        """L2 tools should be allowed with valid approval ID."""
        policy = ToolPolicy()
        decision = policy.evaluate(
            context=valid_context,
            spec=l2_write_tool,
            user_permissions=frozenset(),
            approval_id="approval_123",
        )
        assert decision.allowed is True
        assert decision.requires_approval is False
        assert decision.requires_sandbox is True

    def test_l3_tool_requires_explicit_approval(
        self, l3_destructive_tool: ToolSpec, valid_context: RuntimeContext
    ) -> None:
        """L3 tools should require explicit approval."""
        policy = ToolPolicy()
        decision = policy.evaluate(
            context=valid_context,
            spec=l3_destructive_tool,
            user_permissions=frozenset(),
            approval_id=None,
        )
        assert decision.allowed is False
        assert decision.requires_approval is True
        assert decision.requires_sandbox is True

    def test_l4_tool_blocked_without_permission(
        self, l4_critical_tool: ToolSpec, valid_context: RuntimeContext
    ) -> None:
        """L4 tools should be blocked without proper permissions."""
        policy = ToolPolicy()
        decision = policy.evaluate(
            context=valid_context,
            spec=l4_critical_tool,
            user_permissions=frozenset(),
            approval_id=None,
        )
        assert decision.allowed is False
        assert decision.requires_approval is True
        assert decision.requires_sandbox is True

    def test_disabled_tool_denied(self, valid_context: RuntimeContext) -> None:
        """Disabled tools should be denied regardless of other factors."""
        disabled_tool = ToolSpec.l0_safe(
            name="disabled_tool",
            canonical_name="butler.disabled_tool",
            owner="butler",
            category="utility",
        )
        # Create a disabled version by modifying the spec
        disabled_tool = ToolSpec(
            name=disabled_tool.name,
            canonical_name=disabled_tool.canonical_name,
            description=disabled_tool.description,
            owner=disabled_tool.owner,
            category=disabled_tool.category,
            version=disabled_tool.version,
            source_system=disabled_tool.source_system,
            risk_tier=disabled_tool.risk_tier,
            approval_mode=disabled_tool.approval_mode,
            required_permissions=disabled_tool.required_permissions,
            required_scopes=disabled_tool.required_scopes,
            input_schema=disabled_tool.input_schema,
            output_schema=disabled_tool.output_schema,
            timeout_seconds=disabled_tool.timeout_seconds,
            max_retries=disabled_tool.max_retries,
            idempotent=disabled_tool.idempotent,
            side_effects=disabled_tool.side_effects,
            sandbox_required=disabled_tool.sandbox_required,
            network_required=disabled_tool.network_required,
            filesystem_required=disabled_tool.filesystem_required,
            credential_access_required=disabled_tool.credential_access_required,
            tenant_scope_required=disabled_tool.tenant_scope_required,
            audit_required=disabled_tool.audit_required,
            pii_possible=disabled_tool.pii_possible,
            compensation_handler=disabled_tool.compensation_handler,
            enabled=False,
            tags=disabled_tool.tags,
        )
        policy = ToolPolicy()
        decision = policy.evaluate(
            context=valid_context,
            spec=disabled_tool,
            user_permissions=frozenset(),
            approval_id=None,
        )
        assert decision.allowed is False
        assert "disabled" in decision.reason.lower()

    def test_missing_context_denied(self, l0_safe_tool: ToolSpec) -> None:
        """Tools should be denied without context."""
        policy = ToolPolicy()
        decision = policy.evaluate(
            context=None,
            spec=l0_safe_tool,
            user_permissions=frozenset(),
            approval_id=None,
        )
        assert decision.allowed is False
        assert "context" in decision.reason.lower()

    def test_missing_tenant_id_denied(
        self, l0_safe_tool: ToolSpec, valid_context: RuntimeContext
    ) -> None:
        """Tools should be denied without tenant_id."""
        invalid_context = RuntimeContext.create(
            tenant_id="",
            account_id="account_456",
            session_id="session_789",
            request_id="req_abc",
            trace_id="trace_xyz",
            channel="api",
            user_id="user_123",
        )
        policy = ToolPolicy()
        decision = policy.evaluate(
            context=invalid_context,
            spec=l0_safe_tool,
            user_permissions=frozenset(),
            approval_id=None,
        )
        assert decision.allowed is False
        assert "tenant" in decision.reason.lower()

    def test_degraded_mode_allows_l0(
        self, l0_safe_tool: ToolSpec, valid_context: RuntimeContext
    ) -> None:
        """Degraded mode should allow L0 tools."""
        # Note: ToolPolicy doesn't currently support degraded_mode parameter
        # This test is a placeholder for future degraded mode support
        policy = ToolPolicy()
        decision = policy.evaluate(
            context=valid_context,
            spec=l0_safe_tool,
            user_permissions=frozenset(),
            approval_id=None,
        )
        assert decision.allowed is True

    def test_degraded_mode_blocks_l2(
        self, l2_write_tool: ToolSpec, valid_context: RuntimeContext
    ) -> None:
        """Degraded mode should block L2 tools."""
        # Note: ToolPolicy doesn't currently support degraded_mode parameter
        # This test is a placeholder for future degraded mode support
        policy = ToolPolicy()
        decision = policy.evaluate(
            context=valid_context,
            spec=l2_write_tool,
            user_permissions=frozenset(),
            approval_id=None,
        )
        assert decision.allowed is False

    def test_tool_with_required_scope_denied_without_permission(
        self, valid_context: RuntimeContext
    ) -> None:
        """Tools requiring specific scopes should be denied without permission."""
        tool_with_scope = ToolSpec.create(
            name="scoped_tool",
            canonical_name="butler.scoped_tool",
            description="Tool requiring filesystem scope",
            owner="butler",
            category="filesystem",
            risk_tier=RiskTier.L2,
            approval_mode=ApprovalMode.EXPLICIT,
            required_scopes=frozenset(["write:filesystem"]),
        )
        policy = ToolPolicy()
        decision = policy.evaluate(
            context=valid_context,
            spec=tool_with_scope,
            user_permissions=frozenset(),
            approval_id=None,
        )
        assert decision.allowed is False
        assert "permission" in decision.reason.lower() or "scope" in decision.reason.lower()

    def test_tool_with_required_scope_allowed_with_permission(
        self, valid_context: RuntimeContext
    ) -> None:
        """Tools requiring specific scopes should be allowed with permission."""
        tool_with_scope = ToolSpec.create(
            name="scoped_tool",
            canonical_name="butler.scoped_tool",
            description="Tool requiring filesystem scope",
            owner="butler",
            category="filesystem",
            risk_tier=RiskTier.L2,
            approval_mode=ApprovalMode.EXPLICIT,
            required_scopes=frozenset(["write:filesystem"]),
        )
        policy = ToolPolicy()
        decision = policy.evaluate(
            context=valid_context,
            spec=tool_with_scope,
            user_permissions=frozenset(["write:filesystem"]),
            approval_id="approval_123",
        )
        assert decision.allowed is True


class TestToolPolicyDecision:
    """Tests for ToolPolicyDecision dataclass."""

    def test_decision_allow_factory(self) -> None:
        """ToolPolicyDecision.allow() should create an allow decision."""
        decision = ToolPolicyDecision.allow(reason="Tool is safe")
        assert decision.allowed is True
        assert decision.requires_approval is False
        assert decision.requires_sandbox is False
        assert decision.reason == "Tool is safe"
        assert decision.degraded_mode is None
        assert decision.audit_required is True

    def test_decision_deny_factory(self) -> None:
        """ToolPolicyDecision.deny() should create a deny decision."""
        decision = ToolPolicyDecision.deny(reason="Tool not allowed")
        assert decision.allowed is False
        assert decision.requires_approval is False
        assert decision.requires_sandbox is False
        assert decision.reason == "Tool not allowed"
        assert decision.degraded_mode is None
        assert decision.audit_required is True

    def test_decision_require_approval_factory(self) -> None:
        """ToolPolicyDecision.require_approval() should create an approval decision."""
        decision = ToolPolicyDecision.require_approval(reason="Approval required")
        assert decision.allowed is False
        assert decision.requires_approval is True
        assert decision.requires_sandbox is False
        assert decision.reason == "Approval required"
        assert decision.degraded_mode is None
        assert decision.audit_required is True

    def test_decision_require_sandbox_factory(self) -> None:
        """ToolPolicyDecision.require_sandbox() should create a sandbox decision."""
        decision = ToolPolicyDecision.require_sandbox(reason="Sandbox required")
        assert decision.allowed is False
        assert decision.requires_approval is False
        assert decision.requires_sandbox is True
        assert decision.reason == "Sandbox required"
        assert decision.degraded_mode is None
        assert decision.audit_required is True
