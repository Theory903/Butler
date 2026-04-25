"""TenantNamespace - tenant isolation enforcement."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantNamespace:
    """Tenant namespace for isolation enforcement.

    Rule: All data access must be scoped to tenant namespace.
    """

    tenant_id: str
    account_id: str
    region: str = "default"
    cell: str = "default"

    def to_redis_prefix(self) -> str:
        """Convert to Redis key prefix with TenantNamespace pattern."""
        return f"butler:tenant:{self.tenant_id}:account:{self.account_id}"

    def to_db_schema(self) -> str:
        """Convert to database schema name."""
        return f"tenant_{self.tenant_id}_account_{self.account_id}"

    def to_log_prefix(self) -> str:
        """Convert to log prefix with tenant hashing."""
        import hashlib

        tenant_hash = hashlib.sha256(self.tenant_id.encode()).hexdigest()[:8]
        account_hash = hashlib.sha256(self.account_id.encode()).hexdigest()[:8]
        return f"t_{tenant_hash}_a_{account_hash}"

    @classmethod
    def create(
        cls,
        tenant_id: str,
        account_id: str,
        region: str = "default",
        cell: str = "default",
    ) -> TenantNamespace:
        """Factory method to create a TenantNamespace."""
        return cls(
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            cell=cell,
        )


class TenantNamespaceEnforcer:
    """Enforce tenant namespace isolation.

    Rule: All cross-tenant access must be explicitly allowed.
    """

    def __init__(self, allow_cross_tenant: bool = False) -> None:
        self.allow_cross_tenant = allow_cross_tenant

    def check_access(
        self,
        source_namespace: TenantNamespace,
        target_namespace: TenantNamespace,
    ) -> bool:
        """Check if source can access target namespace."""
        if source_namespace.tenant_id == target_namespace.tenant_id:
            return True

        if self.allow_cross_tenant:
            return True

        return False

    def enforce_namespace(self, namespace: TenantNamespace) -> TenantNamespace:
        """Enforce namespace on operation."""
        if not namespace.tenant_id or not namespace.account_id:
            raise ValueError("TenantNamespace must have tenant_id and account_id")
        return namespace
