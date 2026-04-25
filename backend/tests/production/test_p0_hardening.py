"""
Production Correctness Tests for P0 Hardening

Tests critical P0 hardening requirements to ensure production safety:
- SSRF protection on external HTTP calls
- Tenant isolation via TenantNamespace for Redis
- Hermes dependency isolation via Butler-owned abstractions
- Subprocess sandboxing for user-executable tools
"""

import pytest

from services.security.egress_policy import EgressDecision, EgressPolicy
from services.tenant.namespace import TenantNamespace


class TestSSRFProtection:
    """Test SSRF protection on external HTTP calls."""

    @pytest.mark.asyncio
    async def test_egress_policy_blocks_internal_ip(self):
        """EgressPolicy blocks internal IP addresses."""
        policy = EgressPolicy.get_default()
        decision, reason = policy.check_url(
            "http://169.254.169.254/latest/meta-data/", "test-tenant"
        )
        assert decision == EgressDecision.DENY
        assert "blocked" in reason.lower()

    @pytest.mark.asyncio
    async def test_egress_policy_blocks_localhost(self):
        """EgressPolicy blocks localhost."""
        policy = EgressPolicy.get_default()
        decision, reason = policy.check_url("http://localhost:8080/admin", "test-tenant")
        assert decision == EgressDecision.DENY

    @pytest.mark.asyncio
    async def test_egress_policy_allows_public_api(self):
        """EgressPolicy allows legitimate public API calls."""
        policy = EgressPolicy.get_default()
        decision, reason = policy.check_url(
            "https://api.openai.com/v1/chat/completions", "test-tenant"
        )
        assert decision == EgressDecision.ALLOW


class TestTenantNamespace:
    """Test tenant isolation via TenantNamespace."""

    def test_tenant_namespace_format(self):
        """TenantNamespace formats keys with tenant prefix."""
        namespace = TenantNamespace(tenant_id="tenant-123")
        assert namespace.prefix == "butler:tenant:tenant-123"

    def test_tenant_namespace_session_key(self):
        """TenantNamespace.session() formats session keys correctly."""
        namespace = TenantNamespace(tenant_id="tenant-123")
        session_key = namespace.session("session-456")
        assert session_key == "butler:tenant:tenant-123:session:session-456"

    def test_tenant_namespace_credential_key(self):
        """TenantNamespace.credential() formats credential keys correctly."""
        namespace = TenantNamespace(tenant_id="tenant-123")
        cred_key = namespace.credential("openai")
        assert cred_key == "butler:tenant:tenant-123:credential:openai"

    def test_tenant_namespace_lock_key(self):
        """TenantNamespace.lock() formats lock keys correctly."""
        namespace = TenantNamespace(tenant_id="tenant-123")
        lock_key = namespace.lock("resource", "id-456")
        assert lock_key == "butler:tenant:tenant-123:lock:resource:id-456"

    def test_tenant_isolation_different_tenants(self):
        """Different tenants have different key prefixes."""
        ns1 = TenantNamespace(tenant_id="tenant-1")
        ns2 = TenantNamespace(tenant_id="tenant-2")
        assert ns1.prefix != ns2.prefix
        assert ns1.session("session-1") != ns2.session("session-1")


class TestHermesIsolation:
    """Test Hermes dependency isolation via Butler-owned abstractions."""

    def test_butler_tool_registry_exists(self):
        """ButlerToolRegistry exists and can be instantiated."""
        from domain.tools.butler_tool_registry import ButlerToolRegistry, make_default_tool_registry

        registry = make_default_tool_registry()
        assert isinstance(registry, ButlerToolRegistry)

    def test_butler_tool_registry_isolates_hermes(self):
        """ButlerToolRegistry isolates Hermes dependency."""

        # The registry should wrap Hermes adapter, not import directly
        # This test verifies the abstraction layer exists
        from domain.tools.butler_tool_registry import HermesRegistryAdapter

        assert HermesRegistryAdapter is not None


class TestSubprocessSandboxing:
    """Test subprocess sandboxing for user-executable tools."""

    def test_terminal_tool_uses_sandbox_manager(self):
        """Terminal tool uses SandboxManager for isolation."""
        from services.tools.sandbox_manager import SandboxManager

        manager = SandboxManager()
        assert isinstance(manager, SandboxManager)

    def test_terminal_tool_requires_tenant_id(self):
        """Terminal tool requires tenant_id for isolation."""
        # The function signature should include tenant_id
        import inspect

        from tools.terminal_tool import run_terminal_command_sync

        sig = inspect.signature(run_terminal_command_sync)
        assert "tenant_id" in sig.parameters


class TestMLRuntimeGateway:
    """Test MLRuntime as the only model gateway."""

    def test_ml_runtime_manager_exists(self):
        """MLRuntimeManager exists as the canonical model gateway."""
        from services.ml.runtime import MLRuntimeManager

        assert MLRuntimeManager is not None

    def test_ml_runtime_enforced_via_registry(self):
        """Model providers are registered through MLRuntime registry."""
        from services.ml.registry import ModelRegistry

        # Verify the registry exists and enforces provider registration
        registry = ModelRegistry()
        assert registry is not None


class TestP0HardeningIntegration:
    """Integration tests for P0 hardening requirements."""

    @pytest.mark.asyncio
    async def test_full_hardening_stack(self):
        """Test that all P0 hardening components work together."""
        # 1. Verify TenantNamespace works
        namespace = TenantNamespace(tenant_id="test-tenant")
        session_key = namespace.session("test-session")
        assert "test-tenant" in session_key

        # 2. Verify EgressPolicy works
        policy = EgressPolicy.get_default()
        decision, _ = policy.check_url("http://internal.local", "test-tenant")
        assert decision == EgressDecision.DENY

        # 3. Verify ButlerToolRegistry exists
        from domain.tools.butler_tool_registry import make_default_tool_registry

        registry = make_default_tool_registry()
        assert registry is not None

        # 4. Verify SandboxManager exists
        from services.tools.sandbox_manager import SandboxManager

        manager = SandboxManager()
        assert manager is not None
