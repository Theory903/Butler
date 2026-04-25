"""
Tenant Namespace - Redis Key Namespace Safety

Never hand-write Redis keys. Use TenantNamespace.
All Redis keys must be tenant-scoped to prevent cross-tenant data leakage.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantNamespace:
    """
    Tenant-scoped Redis namespace manager.

    All Redis keys must be created through this class.
    Never hand-write Redis keys with string formatting.
    Never use raw Redis keys without tenant prefix.

    Key format: butler:tenant:{tenant_id}:{resource}:{key}

    Attributes:
        tenant_id: UUID of tenant
        prefix: full tenant prefix (butler:tenant:{tenant_id})
    """

    tenant_id: str

    @property
    def prefix(self) -> str:
        return f"butler:tenant:{self.tenant_id}"

    def credential(self, provider: str) -> str:
        """Credential key for provider."""
        return f"{self.prefix}:credential:{provider}"

    def rate_limit(self, provider: str, window: str) -> str:
        """Rate limit key for provider in time window."""
        return f"{self.prefix}:ratelimit:{provider}:{window}"

    def cache(self, provider: str, key: str) -> str:
        """Cache key for provider and key."""
        return f"{self.prefix}:cache:{provider}:{key}"

    def lock(self, resource: str, id: str) -> str:
        """Lock key for resource and ID."""
        return f"{self.prefix}:lock:{resource}:{id}"

    def usage(self, provider: str, date: str) -> str:
        """Usage tracking key for provider and date."""
        return f"{self.prefix}:usage:{provider}:{date}"

    def session(self, session_id: str) -> str:
        """Session key for session ID."""
        return f"{self.prefix}:session:{session_id}"

    def workspace(self, execution_id: str) -> str:
        """Workspace key for execution ID."""
        return f"{self.prefix}:workspace:{execution_id}"

    def approval(self, request_id: str) -> str:
        """Approval key for request ID."""
        return f"{self.prefix}:approval:{request_id}"


def get_tenant_namespace(tenant_id: str) -> TenantNamespace:
    """Provide a tenant-specific namespace for Redis keys.

    This function is here to avoid circular imports with core/deps.py.
    """
    return TenantNamespace(tenant_id=tenant_id)
