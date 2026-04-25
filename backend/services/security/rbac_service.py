"""
RBAC Service - Role-Based Access Control

Implements Role-Based Access Control with fine-grained permissions.
Supports role hierarchy, permission inheritance, and resource-level access.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class Permission(StrEnum):
    """Permission types."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    ADMIN = "admin"
    EXECUTE = "execute"


@dataclass(frozen=True, slots=True)
class Role:
    """Role definition."""

    role_id: str
    name: str
    permissions: list[str]  # Resource:permission format
    parent_role_id: str | None  # For role hierarchy


@dataclass(frozen=True, slots=True)
class UserRole:
    """User role assignment."""

    user_id: str
    role_id: str
    tenant_id: str
    assigned_at: datetime
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class ResourcePermission:
    """Resource permission."""

    resource_type: str
    resource_id: str
    permission: Permission
    tenant_id: str


class RBACService:
    """
    RBAC service for access control.

    Features:
    - Role management
    - Permission checking
    - Role hierarchy
    - Resource-level permissions
    """

    def __init__(self) -> None:
        """Initialize RBAC service."""
        self._roles: dict[str, Role] = {}
        self._user_roles: dict[str, list[UserRole]] = {}  # user_id -> roles
        self._resource_permissions: dict[
            str, list[ResourcePermission]
        ] = {}  # user_id -> permissions

    def create_role(
        self,
        role_id: str,
        name: str,
        permissions: list[str],
        parent_role_id: str | None = None,
    ) -> Role:
        """
        Create a role.

        Args:
            role_id: Role identifier
            name: Role name
            permissions: List of permissions (resource:permission format)
            parent_role_id: Parent role for hierarchy

        Returns:
            Role
        """
        role = Role(
            role_id=role_id,
            name=name,
            permissions=permissions,
            parent_role_id=parent_role_id,
        )

        self._roles[role_id] = role

        logger.info(
            "role_created",
            role_id=role_id,
            name=name,
        )

        return role

    def assign_role_to_user(
        self,
        user_id: str,
        role_id: str,
        tenant_id: str,
        expires_at: datetime | None = None,
    ) -> UserRole:
        """
        Assign a role to a user.

        Args:
            user_id: User identifier
            role_id: Role identifier
            tenant_id: Tenant identifier
            expires_at: Optional expiration time

        Returns:
            User role assignment
        """
        if role_id not in self._roles:
            raise ValueError(f"Role not found: {role_id}")

        user_role = UserRole(
            user_id=user_id,
            role_id=role_id,
            tenant_id=tenant_id,
            assigned_at=datetime.now(UTC),
            expires_at=expires_at,
        )

        if user_id not in self._user_roles:
            self._user_roles[user_id] = []

        self._user_roles[user_id].append(user_role)

        logger.info(
            "role_assigned",
            user_id=user_id,
            role_id=role_id,
            tenant_id=tenant_id,
        )

        return user_role

    def revoke_role_from_user(
        self,
        user_id: str,
        role_id: str,
        tenant_id: str,
    ) -> bool:
        """
        Revoke a role from a user.

        Args:
            user_id: User identifier
            role_id: Role identifier
            tenant_id: Tenant identifier

        Returns:
            True if revoked
        """
        if user_id not in self._user_roles:
            return False

        initial_count = len(self._user_roles[user_id])
        self._user_roles[user_id] = [
            ur
            for ur in self._user_roles[user_id]
            if not (ur.role_id == role_id and ur.tenant_id == tenant_id)
        ]

        if len(self._user_roles[user_id]) < initial_count:
            logger.info(
                "role_revoked",
                user_id=user_id,
                role_id=role_id,
                tenant_id=tenant_id,
            )
            return True

        return False

    def grant_resource_permission(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        permission: Permission,
        tenant_id: str,
    ) -> ResourcePermission:
        """
        Grant a resource permission to a user.

        Args:
            user_id: User identifier
            resource_type: Resource type
            resource_id: Resource identifier
            permission: Permission
            tenant_id: Tenant identifier

        Returns:
            Resource permission
        """
        resource_permission = ResourcePermission(
            resource_type=resource_type,
            resource_id=resource_id,
            permission=permission,
            tenant_id=tenant_id,
        )

        if user_id not in self._resource_permissions:
            self._resource_permissions[user_id] = []

        self._resource_permissions[user_id].append(resource_permission)

        logger.info(
            "resource_permission_granted",
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            permission=permission,
        )

        return resource_permission

    async def check_permission(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        permission: Permission,
        tenant_id: str,
    ) -> bool:
        """
        Check if user has permission for a resource.

        Args:
            user_id: User identifier
            resource_type: Resource type
            resource_id: Resource identifier
            permission: Permission
            tenant_id: Tenant identifier

        Returns:
            True if permission granted
        """
        # Check direct resource permissions
        if user_id in self._resource_permissions:
            for rp in self._resource_permissions[user_id]:
                if (
                    rp.resource_type == resource_type
                    and rp.resource_id == resource_id
                    and rp.permission == permission
                    and rp.tenant_id == tenant_id
                ):
                    return True

        # Check role-based permissions
        if user_id in self._user_roles:
            for user_role in self._user_roles[user_id]:
                # Check if role is expired
                if user_role.expires_at and user_role.expires_at < datetime.now(UTC):
                    continue

                # Check if role belongs to tenant
                if user_role.tenant_id != tenant_id:
                    continue

                # Get role and check permissions
                role = self._roles.get(user_role.role_id)
                if role:
                    # Check direct permissions
                    permission_key = f"{resource_type}:{permission}"
                    if (
                        permission_key in role.permissions
                        or f"{resource_type}:*" in role.permissions
                        or "*:*" in role.permissions
                    ):
                        return True

                    # Check parent role permissions (hierarchy)
                    if role.parent_role_id:
                        if await self._check_parent_role_permission(
                            role.parent_role_id,
                            resource_type,
                            permission,
                        ):
                            return True

        return False

    async def _check_parent_role_permission(
        self,
        parent_role_id: str,
        resource_type: str,
        permission: Permission,
    ) -> bool:
        """
        Check parent role permission recursively.

        Args:
            parent_role_id: Parent role identifier
            resource_type: Resource type
            permission: Permission

        Returns:
            True if permission granted
        """
        role = self._roles.get(parent_role_id)
        if not role:
            return False

        permission_key = f"{resource_type}:{permission}"
        if (
            permission_key in role.permissions
            or f"{resource_type}:*" in role.permissions
            or "*:*" in role.permissions
        ):
            return True

        if role.parent_role_id:
            return await self._check_parent_role_permission(
                role.parent_role_id,
                resource_type,
                permission,
            )

        return False

    def get_user_roles(
        self,
        user_id: str,
        tenant_id: str | None = None,
    ) -> list[Role]:
        """
        Get user's roles.

        Args:
            user_id: User identifier
            tenant_id: Optional tenant filter

        Returns:
            List of roles
        """
        if user_id not in self._user_roles:
            return []

        roles = []
        now = datetime.now(UTC)

        for user_role in self._user_roles[user_id]:
            # Check if role is expired
            if user_role.expires_at and user_role.expires_at < now:
                continue

            # Check tenant filter
            if tenant_id and user_role.tenant_id != tenant_id:
                continue

            role = self._roles.get(user_role.role_id)
            if role:
                roles.append(role)

        return roles

    def get_role(self, role_id: str) -> Role | None:
        """
        Get a role by ID.

        Args:
            role_id: Role identifier

        Returns:
            Role or None
        """
        return self._roles.get(role_id)

    def delete_role(self, role_id: str) -> bool:
        """
        Delete a role.

        Args:
            role_id: Role identifier

        Returns:
            True if deleted
        """
        if role_id in self._roles:
            del self._roles[role_id]

            # Remove role from all users
            for user_id, user_roles in self._user_roles.items():
                self._user_roles[user_id] = [ur for ur in user_roles if ur.role_id != role_id]

            logger.info(
                "role_deleted",
                role_id=role_id,
            )

            return True
        return False

    def get_rbac_stats(self) -> dict[str, Any]:
        """
        Get RBAC statistics.

        Returns:
            RBAC statistics
        """
        total_roles = len(self._roles)
        total_user_roles = sum(len(roles) for roles in self._user_roles.values())
        total_resource_permissions = sum(
            len(perms) for perms in self._resource_permissions.values()
        )

        return {
            "total_roles": total_roles,
            "total_user_role_assignments": total_user_roles,
            "total_resource_permissions": total_resource_permissions,
            "users_with_roles": len(self._user_roles),
        }
