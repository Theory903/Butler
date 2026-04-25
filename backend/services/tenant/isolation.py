"""
Tenant Isolation Service - Multi-Tenant Isolation Enforcement

Enforces tenant isolation across all system boundaries.
Prevents cross-tenant data leakage and resource interference.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

import structlog

logger = structlog.get_logger(__name__)


class IsolationLevel(StrEnum):
    """Tenant isolation levels."""

    SHARED = "shared"
    DEDICATED_WORKER = "dedicated_worker"
    DEDICATED_VPC = "dedicated_vpc"


@dataclass(frozen=True, slots=True)
class IsolationPolicy:
    """
    Tenant isolation policy.

    Defines isolation requirements for tenant deployment.
    """

    level: IsolationLevel
    require_dedicated_worker: bool
    require_dedicated_vpc: bool
    require_dedicated_database: bool
    require_dedicated_redis: bool
    require_dedicated_storage: bool

    @classmethod
    def from_level(cls, level: IsolationLevel) -> IsolationPolicy:
        """Create policy from isolation level."""
        if level == IsolationLevel.SHARED:
            return cls(
                level=level,
                require_dedicated_worker=False,
                require_dedicated_vpc=False,
                require_dedicated_database=False,
                require_dedicated_redis=False,
                require_dedicated_storage=False,
            )
        if level == IsolationLevel.DEDICATED_WORKER:
            return cls(
                level=level,
                require_dedicated_worker=True,
                require_dedicated_vpc=False,
                require_dedicated_database=False,
                require_dedicated_redis=False,
                require_dedicated_storage=False,
            )
        if level == IsolationLevel.DEDICATED_VPC:
            return cls(
                level=level,
                require_dedicated_worker=True,
                require_dedicated_vpc=True,
                require_dedicated_database=True,
                require_dedicated_redis=True,
                require_dedicated_storage=True,
            )
        raise ValueError(f"Unknown isolation level: {level}")


class TenantIsolationService:
    """
    Tenant isolation enforcement service.

    Enforces tenant isolation across:
    - Database queries (tenant_id scoping)
    - Redis keys (namespace prefixing)
    - File system paths (tenant workspace isolation)
    - Network isolation (VPC, egress policies)
    - Compute isolation (dedicated workers)
    """

    def __init__(self, policy: IsolationPolicy) -> None:
        """Initialize isolation service with policy."""
        self.policy = policy

    def validate_database_query(self, query: str, tenant_id: str) -> bool:
        """
        Validate database query includes tenant scoping.

        Args:
            query: SQL query to validate
            tenant_id: Tenant UUID

        Returns:
            True if query is properly scoped, False otherwise
        """
        # Normalize query
        query_lower = query.lower().strip()

        # Skip validation for schema changes, transactions, and admin queries
        if any(
            keyword in query_lower
            for keyword in [
                "create table",
                "alter table",
                "drop table",
                "begin",
                "commit",
                "rollback",
                "set ",
                "show ",
                "describe ",
            ]
        ):
            return True

        # Check for SELECT, UPDATE, DELETE queries
        if any(keyword in query_lower for keyword in ["select ", "update ", "delete "]):
            # Check if tenant_id is present in WHERE clause
            # This is a simple heuristic - production should use SQL parser
            tenant_pattern = re.compile(rf"tenant_id\s*=\s*['\"]?{tenant_id}['\"]?", re.IGNORECASE)

            if not tenant_pattern.search(query):
                logger.warning(
                    "database_query_missing_tenant_scoping",
                    tenant_id=tenant_id,
                    query=query[:200],  # Log first 200 chars
                )
                return False

        return True

    def validate_redis_key(self, key: str, tenant_id: str) -> bool:
        """
        Validate Redis key includes tenant namespace.

        Args:
            key: Redis key to validate
            tenant_id: Tenant UUID

        Returns:
            True if key is properly namespaced, False otherwise
        """
        expected_prefix = f"tenant:{tenant_id}"
        return key.startswith(expected_prefix)

    def validate_filesystem_path(self, path: str, tenant_id: str) -> bool:
        """
        Validate filesystem path is within tenant workspace.

        Args:
            path: Filesystem path to validate
            tenant_id: Tenant UUID

        Returns:
            True if path is within tenant workspace, False otherwise
        """
        # Normalize path
        normalized_path = path.replace("\\", "/")

        # Check for path traversal attempts
        if ".." in normalized_path:
            logger.warning(
                "filesystem_path_traversal_attempt",
                tenant_id=tenant_id,
                path=path,
            )
            return False

        # Check for symlink escapes (basic check)
        if "/../" in normalized_path or normalized_path.startswith("../"):
            logger.warning(
                "filesystem_symlink_escape_attempt",
                tenant_id=tenant_id,
                path=path,
            )
            return False

        # Check path is within tenant workspace
        expected_prefix = f"/var/butler/tenants/{tenant_id}/"
        return normalized_path.startswith(expected_prefix)

    def validate_network_access(self, target: str, tenant_id: str) -> bool:
        """
        Validate network access is allowed for tenant.

        Args:
            target: Target IP or hostname
            tenant_id: Tenant UUID

        Returns:
            True if network access is allowed, False otherwise
        """
        # Block metadata IPs (AWS, GCP, Azure)
        blocked_ips = [
            "169.254.169.254",  # AWS/GCP/Azure metadata
            "metadata.google.internal",  # GCP
            "169.254.169.254",  # AWS
        ]

        if any(blocked in target for blocked in blocked_ips):
            logger.warning(
                "network_access_blocked_metadata_ip",
                tenant_id=tenant_id,
                target=target,
            )
            return False

        # Block private IPs (RFC 1918) for shared isolation
        if self.policy.level == IsolationLevel.SHARED:
            private_ip_patterns = [
                r"^10\.",
                r"^172\.(1[6-9]|2[0-9]|3[0-1])\.",
                r"^192\.168\.",
            ]

            for pattern in private_ip_patterns:
                if re.match(pattern, target):
                    logger.warning(
                        "network_access_blocked_private_ip",
                        tenant_id=tenant_id,
                        target=target,
                    )
                    return False

        return True

    def get_tenant_database_schema(self, tenant_id: str) -> str:
        """
        Get tenant-specific database schema name.

        Args:
            tenant_id: Tenant UUID

        Returns:
            Schema name for tenant
        """
        # For shared isolation, use public schema with RLS
        # For dedicated database, use tenant-specific schema
        if self.policy.level == IsolationLevel.SHARED:
            return "public"
        return f"tenant_{tenant_id.replace('-', '_')}"

    def get_tenant_redis_namespace(self, tenant_id: str) -> str:
        """
        Get tenant-specific Redis namespace.

        Args:
            tenant_id: Tenant UUID

        Returns:
            Redis namespace prefix for tenant
        """
        return f"tenant:{tenant_id}"

    def get_tenant_workspace_path(self, tenant_id: str, execution_id: str) -> str:
        """
        Get tenant-specific workspace path.

        Args:
            tenant_id: Tenant UUID
            execution_id: Execution UUID

        Returns:
            Workspace path for tenant execution
        """
        return f"/var/butler/tenants/{tenant_id}/executions/{execution_id}/"

    def add_tenant_scoping_to_query(
        self,
        query: str,
        tenant_id: str,
        table_alias: str = "",
    ) -> str:
        """
        Add tenant_id scoping to SQL query.

        Args:
            query: SQL query
            tenant_id: Tenant UUID
            table_alias: Optional table alias for WHERE clause

        Returns:
            Query with tenant_id scoping added
        """
        # This is a simple implementation - production should use SQL parser
        query_lower = query.lower().strip()

        # Skip if already has tenant_id in WHERE
        if "tenant_id" in query_lower:
            return query

        # Add WHERE clause for SELECT, UPDATE, DELETE
        if any(keyword in query_lower for keyword in ["select ", "update ", "delete "]):
            if "where" not in query_lower:
                # Add WHERE clause
                if "select" in query_lower:
                    # For SELECT, add before GROUP BY, ORDER BY, LIMIT
                    keywords = ["group by", "order by", "limit", "offset"]
                    insert_pos = len(query)

                    for keyword in keywords:
                        pos = query_lower.find(keyword)
                        if pos != -1 and pos < insert_pos:
                            insert_pos = pos

                    prefix = query[:insert_pos]
                    suffix = query[insert_pos:]

                    if table_alias:
                        return f"{prefix} WHERE {table_alias}.tenant_id = '{tenant_id}'{suffix}"
                    return f"{prefix} WHERE tenant_id = '{tenant_id}'{suffix}"
                # For UPDATE/DELETE
                if table_alias:
                    return f"{query} WHERE {table_alias}.tenant_id = '{tenant_id}'"
                return f"{query} WHERE tenant_id = '{tenant_id}'"
            # Add AND to existing WHERE
            if table_alias:
                return query + f" AND {table_alias}.tenant_id = '{tenant_id}'"
            return query + f" AND tenant_id = '{tenant_id}'"

        return query
