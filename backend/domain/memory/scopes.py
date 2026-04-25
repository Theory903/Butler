"""MemoryScope - memory isolation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MemoryScope(str, Enum):
    """Memory scope for isolation.

    SESSION: Single conversation session
    USER: All sessions for a user
    TENANT: All users within a tenant
    AGENT: Agent-specific memory
    GLOBAL: Cross-tenant shared memory (rare, requires explicit approval)
    """

    SESSION = "session"
    USER = "user"
    TENANT = "tenant"
    AGENT = "agent"
    GLOBAL = "global"


@dataclass(frozen=True, slots=True)
class MemoryScopeKey:
    """Canonical memory scope key for tenant/account/session isolation.

    Rule: All memory operations must include a MemoryScopeKey.
    """

    tenant_id: str
    account_id: str
    session_id: str | None
    user_id: str | None
    agent_id: str | None
    scope: MemoryScope

    @classmethod
    def create(
        cls,
        tenant_id: str,
        account_id: str,
        scope: MemoryScope = MemoryScope.SESSION,
        session_id: str | None = None,
        user_id: str | None = None,
        agent_id: str | None = None,
    ) -> MemoryScopeKey:
        """Factory method to create a MemoryScopeKey."""
        return cls(
            tenant_id=tenant_id,
            account_id=account_id,
            session_id=session_id,
            user_id=user_id,
            agent_id=agent_id,
            scope=scope,
        )

    def to_redis_key(self) -> str:
        """Convert to Redis key with TenantNamespace pattern."""
        parts = [
            "butler",
            "memory",
            self.scope.value,
            self.tenant_id,
            self.account_id,
        ]
        if self.session_id:
            parts.append(self.session_id)
        if self.user_id:
            parts.append(self.user_id)
        if self.agent_id:
            parts.append(self.agent_id)
        return ":".join(parts)

    def to_vector_collection_name(self) -> str:
        """Convert to Qdrant collection name."""
        parts = [
            "memory",
            self.scope.value,
            self.tenant_id,
            self.account_id,
        ]
        if self.session_id:
            parts.append(self.session_id)
        return "_".join(parts)
