"""Comprehensive tests for TenantNamespace and namespace isolation.

Tests cover:
- TenantNamespace prefix generation for Redis, DB, and logging
- TenantNamespaceEnforcer access control
- Cross-tenant access prevention
- Edge cases and error conditions
- Hardened error handling
"""

import dataclasses

import pytest

from domain.tenant.namespace import (
    TenantNamespace,
    TenantNamespaceEnforcer,
)


class TestTenantNamespace:
    """Test TenantNamespace dataclass and methods."""

    def test_create_tenant_namespace(self):
        """Test creating a TenantNamespace."""
        namespace = TenantNamespace(
            tenant_id="tenant_1",
            account_id="account_1",
        )
        assert namespace.tenant_id == "tenant_1"
        assert namespace.account_id == "account_1"
        assert namespace.region == "default"
        assert namespace.cell == "default"

    def test_create_tenant_namespace_with_region_cell(self):
        """Test creating a TenantNamespace with region and cell."""
        namespace = TenantNamespace(
            tenant_id="tenant_1",
            account_id="account_1",
            region="us-east-1",
            cell="cell-1",
        )
        assert namespace.region == "us-east-1"
        assert namespace.cell == "cell-1"

    def test_create_factory_method(self):
        """Test TenantNamespace factory method."""
        namespace = TenantNamespace.create(
            tenant_id="tenant_1",
            account_id="account_1",
            region="us-west-2",
            cell="cell-2",
        )
        assert namespace.tenant_id == "tenant_1"
        assert namespace.account_id == "account_1"
        assert namespace.region == "us-west-2"
        assert namespace.cell == "cell-2"

    def test_to_redis_prefix(self):
        """Test Redis prefix generation."""
        namespace = TenantNamespace(
            tenant_id="tenant_1",
            account_id="account_1",
        )
        prefix = namespace.to_redis_prefix()
        assert prefix == "butler:tenant:tenant_1:account:account_1"

    def test_to_redis_prefix_with_special_chars(self):
        """Test Redis prefix with special characters in IDs."""
        namespace = TenantNamespace(
            tenant_id="tenant-1_special",
            account_id="account@2#test",
        )
        prefix = namespace.to_redis_prefix()
        assert prefix == "butler:tenant:tenant-1_special:account:account@2#test"

    def test_to_db_schema(self):
        """Test database schema name generation."""
        namespace = TenantNamespace(
            tenant_id="tenant_1",
            account_id="account_1",
        )
        schema = namespace.to_db_schema()
        assert schema == "tenant_tenant_1_account_account_1"

    def test_to_log_prefix(self):
        """Test log prefix with tenant hashing."""
        namespace = TenantNamespace(
            tenant_id="tenant_1",
            account_id="account_1",
        )
        prefix = namespace.to_log_prefix()
        # Verify it follows the pattern t_{hash}_a_{hash}
        assert prefix.startswith("t_")
        assert "_a_" in prefix
        # Hash is 8 chars, so t_8chars_a_8chars = 2+8+3+8 = 21 chars
        assert len(prefix) == 21

    def test_to_log_prefix_consistency(self):
        """Test log prefix hashing is consistent."""
        namespace = TenantNamespace(
            tenant_id="tenant_1",
            account_id="account_1",
        )
        prefix1 = namespace.to_log_prefix()
        prefix2 = namespace.to_log_prefix()
        assert prefix1 == prefix2

    def test_to_log_prefix_different_ids(self):
        """Test log prefix differs for different IDs."""
        namespace1 = TenantNamespace(
            tenant_id="tenant_1",
            account_id="account_1",
        )
        namespace2 = TenantNamespace(
            tenant_id="tenant_2",
            account_id="account_1",
        )
        prefix1 = namespace1.to_log_prefix()
        prefix2 = namespace2.to_log_prefix()
        assert prefix1 != prefix2

    def test_tenant_namespace_frozen(self):
        """Test TenantNamespace is frozen (immutable)."""
        namespace = TenantNamespace(
            tenant_id="tenant_1",
            account_id="account_1",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            namespace.tenant_id = "tenant_2"  # type: ignore

    def test_tenant_namespace_with_empty_tenant_id(self):
        """Test TenantNamespace with empty tenant_id."""
        namespace = TenantNamespace(
            tenant_id="",
            account_id="account_1",
        )
        assert namespace.tenant_id == ""
        assert namespace.to_redis_prefix() == "butler:tenant::account:account_1"

    def test_tenant_namespace_with_empty_account_id(self):
        """Test TenantNamespace with empty account_id."""
        namespace = TenantNamespace(
            tenant_id="tenant_1",
            account_id="",
        )
        assert namespace.account_id == ""
        assert namespace.to_redis_prefix() == "butler:tenant:tenant_1:account:"


class TestTenantNamespaceEnforcer:
    """Test TenantNamespaceEnforcer access control."""

    def test_enforcer_init(self):
        """Test TenantNamespaceEnforcer initialization."""
        enforcer = TenantNamespaceEnforcer()
        assert enforcer.allow_cross_tenant is False

        enforcer = TenantNamespaceEnforcer(allow_cross_tenant=True)
        assert enforcer.allow_cross_tenant is True

    def test_check_access_same_tenant(self):
        """Test access within same tenant is allowed."""
        enforcer = TenantNamespaceEnforcer()
        source = TenantNamespace(tenant_id="tenant_1", account_id="account_1")
        target = TenantNamespace(tenant_id="tenant_1", account_id="account_2")
        assert enforcer.check_access(source, target) is True

    def test_check_access_different_tenant_cross_tenant_disabled(self):
        """Test cross-tenant access is denied when disabled."""
        enforcer = TenantNamespaceEnforcer(allow_cross_tenant=False)
        source = TenantNamespace(tenant_id="tenant_1", account_id="account_1")
        target = TenantNamespace(tenant_id="tenant_2", account_id="account_1")
        assert enforcer.check_access(source, target) is False

    def test_check_access_different_tenant_cross_tenant_enabled(self):
        """Test cross-tenant access is allowed when enabled."""
        enforcer = TenantNamespaceEnforcer(allow_cross_tenant=True)
        source = TenantNamespace(tenant_id="tenant_1", account_id="account_1")
        target = TenantNamespace(tenant_id="tenant_2", account_id="account_1")
        assert enforcer.check_access(source, target) is True

    def test_check_access_same_account(self):
        """Test access within same account is allowed."""
        enforcer = TenantNamespaceEnforcer()
        source = TenantNamespace(tenant_id="tenant_1", account_id="account_1")
        target = TenantNamespace(tenant_id="tenant_1", account_id="account_1")
        assert enforcer.check_access(source, target) is True

    def test_enforce_namespace_valid(self):
        """Test enforcing valid namespace."""
        enforcer = TenantNamespaceEnforcer()
        namespace = TenantNamespace(tenant_id="tenant_1", account_id="account_1")
        result = enforcer.enforce_namespace(namespace)
        assert result is namespace

    def test_enforce_namespace_empty_tenant_id(self):
        """Test enforcing namespace with empty tenant_id raises error."""
        enforcer = TenantNamespaceEnforcer()
        namespace = TenantNamespace(tenant_id="", account_id="account_1")
        with pytest.raises(ValueError, match="must have tenant_id and account_id"):
            enforcer.enforce_namespace(namespace)

    def test_enforce_namespace_empty_account_id(self):
        """Test enforcing namespace with empty account_id raises error."""
        enforcer = TenantNamespaceEnforcer()
        namespace = TenantNamespace(tenant_id="tenant_1", account_id="")
        with pytest.raises(ValueError, match="must have tenant_id and account_id"):
            enforcer.enforce_namespace(namespace)

    def test_enforce_namespace_both_empty(self):
        """Test enforcing namespace with both IDs empty raises error."""
        enforcer = TenantNamespaceEnforcer()
        namespace = TenantNamespace(tenant_id="", account_id="")
        with pytest.raises(ValueError, match="must have tenant_id and account_id"):
            enforcer.enforce_namespace(namespace)


class TestRedisAbstractions:
    """Test Redis abstractions with TenantNamespace."""

    def test_redis_key_construction(self):
        """Test Redis key construction with namespace prefix."""
        namespace = TenantNamespace(tenant_id="tenant_1", account_id="account_1")
        prefix = namespace.to_redis_prefix()

        # Simulate key construction
        cache_key = f"{prefix}:cache:session_123"
        assert cache_key == "butler:tenant:tenant_1:account:account_1:cache:session_123"

    def test_redis_key_isolation(self):
        """Test that different namespaces produce different keys."""
        namespace1 = TenantNamespace(tenant_id="tenant_1", account_id="account_1")
        namespace2 = TenantNamespace(tenant_id="tenant_2", account_id="account_1")

        key1 = f"{namespace1.to_redis_prefix()}:cache:session_123"
        key2 = f"{namespace2.to_redis_prefix()}:cache:session_123"

        assert key1 != key2
        assert "tenant_1" in key1
        assert "tenant_2" in key2

    def test_redis_key_same_namespace(self):
        """Test that same namespace produces same keys."""
        namespace = TenantNamespace(tenant_id="tenant_1", account_id="account_1")

        key1 = f"{namespace.to_redis_prefix()}:cache:session_123"
        key2 = f"{namespace.to_redis_prefix()}:cache:session_123"

        assert key1 == key2

    def test_redis_key_with_multiple_components(self):
        """Test Redis key with multiple components."""
        namespace = TenantNamespace(tenant_id="tenant_1", account_id="account_1")
        prefix = namespace.to_redis_prefix()

        # Complex key with multiple components
        key = f"{prefix}:workflow:task_456:step_789"
        assert key == "butler:tenant:tenant_1:account:account_1:workflow:task_456:step_789"


class TestDatabaseSchema:
    """Test database schema isolation."""

    def test_schema_isolation(self):
        """Test that different namespaces produce different schemas."""
        namespace1 = TenantNamespace(tenant_id="tenant_1", account_id="account_1")
        namespace2 = TenantNamespace(tenant_id="tenant_2", account_id="account_1")

        schema1 = namespace1.to_db_schema()
        schema2 = namespace2.to_db_schema()

        assert schema1 != schema2
        assert "tenant_tenant_1" in schema1
        assert "tenant_tenant_2" in schema2

    def test_schema_same_namespace(self):
        """Test that same namespace produces same schema."""
        namespace = TenantNamespace(tenant_id="tenant_1", account_id="account_1")

        schema1 = namespace.to_db_schema()
        schema2 = namespace.to_db_schema()

        assert schema1 == schema2

    def test_schema_with_special_chars(self):
        """Test schema with special characters in IDs."""
        namespace = TenantNamespace(
            tenant_id="tenant-1",
            account_id="account_1",
        )
        schema = namespace.to_db_schema()
        assert schema == "tenant_tenant-1_account_account_1"


class TestLogPrefix:
    """Test log prefix isolation and PII protection."""

    def test_log_prefix_hashes_tenant_id(self):
        """Test that log prefix hashes tenant_id."""
        namespace = TenantNamespace(tenant_id="tenant_1", account_id="account_1")
        prefix = namespace.to_log_prefix()

        # Verify tenant_id is not in the prefix
        assert "tenant_1" not in prefix
        assert "tenant" not in prefix

    def test_log_prefix_hashes_account_id(self):
        """Test that log prefix hashes account_id."""
        namespace = TenantNamespace(tenant_id="tenant_1", account_id="account_1")
        prefix = namespace.to_log_prefix()

        # Verify account_id is not in the prefix
        assert "account_1" not in prefix
        assert "account" not in prefix

    def test_log_prefix_hash_length(self):
        """Test that log prefix hash is 8 characters."""
        namespace = TenantNamespace(tenant_id="tenant_1", account_id="account_1")
        prefix = namespace.to_log_prefix()

        # Extract tenant hash (between t_ and _a_)
        tenant_hash = prefix.split("_")[1]
        account_hash = prefix.split("_")[3]

        assert len(tenant_hash) == 8
        assert len(account_hash) == 8

    def test_log_prefix_deterministic(self):
        """Test that log prefix is deterministic for same input."""
        namespace = TenantNamespace(tenant_id="tenant_1", account_id="account_1")

        # Generate multiple times
        prefixes = [namespace.to_log_prefix() for _ in range(10)]

        # All should be the same
        assert all(p == prefixes[0] for p in prefixes)

    def test_log_prefix_collision_unlikely(self):
        """Test that log prefix collisions are unlikely."""
        namespace1 = TenantNamespace(tenant_id="tenant_1", account_id="account_1")
        namespace2 = TenantNamespace(tenant_id="tenant_2", account_id="account_2")

        prefix1 = namespace1.to_log_prefix()
        prefix2 = namespace2.to_log_prefix()

        # Should be different for different inputs
        assert prefix1 != prefix2


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_tenant_namespace_with_none_tenant_id(self):
        """Test TenantNamespace with None tenant_id."""
        # Python dataclasses don't enforce type checking at runtime
        # This test documents that None is allowed but should be validated elsewhere
        namespace = TenantNamespace(tenant_id=None, account_id="account_1")  # type: ignore
        assert namespace.tenant_id is None
        assert namespace.to_redis_prefix() == "butler:tenant:None:account:account_1"

    def test_tenant_namespace_with_none_account_id(self):
        """Test TenantNamespace with None account_id."""
        # Python dataclasses don't enforce type checking at runtime
        # This test documents that None is allowed but should be validated elsewhere
        namespace = TenantNamespace(tenant_id="tenant_1", account_id=None)  # type: ignore
        assert namespace.account_id is None
        assert namespace.to_redis_prefix() == "butler:tenant:tenant_1:account:None"

    def test_enforcer_with_none_namespace(self):
        """Test enforcer with None namespace."""
        enforcer = TenantNamespaceEnforcer()
        with pytest.raises(AttributeError):
            enforcer.check_access(
                None, TenantNamespace(tenant_id="tenant_1", account_id="account_1")
            )  # type: ignore

    def test_enforce_namespace_with_none(self):
        """Test enforcing None namespace."""
        enforcer = TenantNamespaceEnforcer()
        with pytest.raises(AttributeError):
            enforcer.enforce_namespace(None)  # type: ignore

    def test_tenant_namespace_with_very_long_ids(self):
        """Test TenantNamespace with very long IDs."""
        long_tenant_id = "a" * 1000
        long_account_id = "b" * 1000

        namespace = TenantNamespace(tenant_id=long_tenant_id, account_id=long_account_id)
        assert namespace.tenant_id == long_tenant_id
        assert namespace.account_id == long_account_id

        # Redis prefix should handle long IDs
        prefix = namespace.to_redis_prefix()
        assert long_tenant_id in prefix
        assert long_account_id in prefix

    def test_tenant_namespace_with_unicode_ids(self):
        """Test TenantNamespace with unicode characters."""
        namespace = TenantNamespace(
            tenant_id="tenant_1_日本語",
            account_id="account_1_中文",
        )
        assert namespace.tenant_id == "tenant_1_日本語"
        assert namespace.account_id == "account_1_中文"

        # Redis prefix should handle unicode
        prefix = namespace.to_redis_prefix()
        assert "tenant_1_日本語" in prefix
        assert "account_1_中文" in prefix


class TestIntegrationScenarios:
    """Test integration scenarios with multiple components."""

    def test_full_namespace_flow(self):
        """Test full namespace flow from creation to usage."""
        # Create namespace
        namespace = TenantNamespace.create(
            tenant_id="tenant_1",
            account_id="account_1",
            region="us-east-1",
        )

        # Enforce namespace
        enforcer = TenantNamespaceEnforcer()
        enforced = enforcer.enforce_namespace(namespace)
        assert enforced is namespace

        # Generate prefixes
        redis_prefix = namespace.to_redis_prefix()
        db_schema = namespace.to_db_schema()
        log_prefix = namespace.to_log_prefix()

        # Verify all prefixes are generated
        assert redis_prefix == "butler:tenant:tenant_1:account:account_1"
        assert db_schema == "tenant_tenant_1_account_account_1"
        assert log_prefix.startswith("t_")

    def test_multi_tenant_isolation(self):
        """Test isolation between multiple tenants."""
        enforcer = TenantNamespaceEnforcer(allow_cross_tenant=False)

        # Create multiple namespaces
        tenant1_account1 = TenantNamespace(tenant_id="tenant_1", account_id="account_1")
        tenant1_account2 = TenantNamespace(tenant_id="tenant_1", account_id="account_2")
        tenant2_account1 = TenantNamespace(tenant_id="tenant_2", account_id="account_1")

        # Check access patterns
        assert enforcer.check_access(tenant1_account1, tenant1_account2) is True
        assert enforcer.check_access(tenant1_account1, tenant2_account1) is False
        assert enforcer.check_access(tenant2_account1, tenant1_account1) is False

    def test_cross_tenant_with_permission(self):
        """Test cross-tenant access with explicit permission."""
        enforcer = TenantNamespaceEnforcer(allow_cross_tenant=True)

        tenant1 = TenantNamespace(tenant_id="tenant_1", account_id="account_1")
        tenant2 = TenantNamespace(tenant_id="tenant_2", account_id="account_1")

        # Cross-tenant access should be allowed
        assert enforcer.check_access(tenant1, tenant2) is True

    def test_redis_key_collision_prevention(self):
        """Test that Redis keys don't collide across namespaces."""
        namespaces = [
            TenantNamespace(tenant_id=f"tenant_{i}", account_id=f"account_{i}") for i in range(100)
        ]

        keys = set()
        for namespace in namespaces:
            key = f"{namespace.to_redis_prefix()}:cache:session_123"
            keys.add(key)

        # All keys should be unique
        assert len(keys) == 100

    def test_log_prefix_uniqueness(self):
        """Test that log prefixes are unique for different namespaces."""
        namespaces = [
            TenantNamespace(tenant_id=f"tenant_{i}", account_id=f"account_{i}") for i in range(100)
        ]

        prefixes = set()
        for namespace in namespaces:
            prefix = namespace.to_log_prefix()
            prefixes.add(prefix)

        # All prefixes should be unique (very high probability)
        assert len(prefixes) == 100
