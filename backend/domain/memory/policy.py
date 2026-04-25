"""MemoryPolicy - memory access control and retention policies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import Enum


class RetentionPolicy(str, Enum):
    """Memory retention policies."""

    INDEFINITE = "indefinite"
    SESSION_ONLY = "session_only"
    DAYS_7 = "7_days"
    DAYS_30 = "30_days"
    DAYS_90 = "90_days"
    YEARS_1 = "1_year"


class AccessLevel(str, Enum):
    """Memory access levels."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"


@dataclass(frozen=True, slots=True)
class MemoryPolicy:
    """Memory access and retention policy.

    Rule: All memory operations must check policy before access.
    """

    retention: RetentionPolicy
    max_size_mb: int
    allowed_access: frozenset[AccessLevel]
    pii_allowed: bool
    requires_encryption: bool
    right_to_erasure: bool

    @classmethod
    def default(cls) -> MemoryPolicy:
        """Default memory policy for session memory."""
        return cls(
            retention=RetentionPolicy.DAYS_30,
            max_size_mb=100,
            allowed_access=frozenset({AccessLevel.READ, AccessLevel.WRITE}),
            pii_allowed=False,
            requires_encryption=True,
            right_to_erasure=True,
        )

    @classmethod
    def long_term(cls) -> MemoryPolicy:
        """Long-term memory policy for user memory."""
        return cls(
            retention=RetentionPolicy.DAYS_90,
            max_size_mb=1000,
            allowed_access=frozenset({AccessLevel.READ, AccessLevel.WRITE}),
            pii_allowed=True,
            requires_encryption=True,
            right_to_erasure=True,
        )

    @classmethod
    def agent_memory(cls) -> MemoryPolicy:
        """Agent memory policy."""
        return cls(
            retention=RetentionPolicy.INDEFINITE,
            max_size_mb=10000,
            allowed_access=frozenset({AccessLevel.READ, AccessLevel.WRITE}),
            pii_allowed=False,
            requires_encryption=False,
            right_to_erasure=False,
        )

    def get_retention_ttl(self) -> timedelta:
        """Get retention TTL based on policy."""
        ttl_map = {
            RetentionPolicy.INDEFINITE: timedelta(days=365 * 10),
            RetentionPolicy.SESSION_ONLY: timedelta(hours=24),
            RetentionPolicy.DAYS_7: timedelta(days=7),
            RetentionPolicy.DAYS_30: timedelta(days=30),
            RetentionPolicy.DAYS_90: timedelta(days=90),
            RetentionPolicy.YEARS_1: timedelta(days=365),
        }
        return ttl_map.get(self.retention, timedelta(days=30))

    def can_access(self, level: AccessLevel) -> bool:
        """Check if access level is allowed."""
        return level in self.allowed_access

    def can_delete(self) -> bool:
        """Check if delete is allowed."""
        return AccessLevel.DELETE in self.allowed_access or self.right_to_erasure
