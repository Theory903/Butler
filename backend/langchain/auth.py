"""Butler Auth + Identity + Connections for LangChain.

Provides authentication, identity management, and connection handling.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ButlerIdentity:
    """Butler identity context."""

    account_id: str
    user_id: str | None = None
    tenant_id: str = ""
    roles: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ButlerConnection:
    """Butler connection to external services."""

    connection_id: str
    connection_type: str  # "api_key", "oauth", "service_account", etc.
    service_name: str
    config: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class ButlerAuthContext:
    """Authentication context for LangChain agents.

    This context:
    - Manages identity information
    - Validates permissions
    - Provides auth tokens
    - Handles session authentication
    """

    def __init__(self, identity: ButlerIdentity | None = None):
        """Initialize the auth context.

        Args:
            identity: Optional Butler identity
        """
        self._identity = identity
        self._auth_token: str | None = None
        self._session_data: dict[str, Any] = {}

    def set_identity(self, identity: ButlerIdentity) -> None:
        """Set the identity.

        Args:
            identity: Butler identity
        """
        self._identity = identity
        logger.info("auth_identity_set", account_id=identity.account_id)

    def get_identity(self) -> ButlerIdentity | None:
        """Get the current identity.

        Returns:
            Butler identity or None
        """
        return self._identity

    def set_auth_token(self, token: str) -> None:
        """Set the auth token.

        Args:
            token: Auth token
        """
        self._auth_token = token
        logger.info("auth_token_set")

    def get_auth_token(self) -> str | None:
        """Get the auth token.

        Returns:
            Auth token or None
        """
        return self._auth_token

    def has_permission(self, permission: str) -> bool:
        """Check if identity has a permission.

        Args:
            permission: Permission to check

        Returns:
            True if has permission
        """
        if not self._identity:
            return False
        return permission in self._identity.permissions

    def has_role(self, role: str) -> bool:
        """Check if identity has a role.

        Args:
            role: Role to check

        Returns:
            True if has role
        """
        if not self._identity:
            return False
        return role in self._identity.roles

    def is_authenticated(self) -> bool:
        """Check if authenticated.

        Returns:
            True if authenticated
        """
        return self._identity is not None and self._auth_token is not None

    def set_session_data(self, key: str, value: Any) -> None:
        """Set session data.

        Args:
            key: Data key
            value: Data value
        """
        self._session_data[key] = value

    def get_session_data(self, key: str) -> Any:
        """Get session data.

        Args:
            key: Data key

        Returns:
            Data value or None
        """
        return self._session_data.get(key)

    def clear_session(self) -> None:
        """Clear session data."""
        self._session_data.clear()
        logger.info("auth_session_cleared")


class ButlerConnectionManager:
    """Manager for external service connections.

    This manager:
    - Stores connection configurations
    - Manages connection lifecycle
    - Provides connection access
    - Handles connection rotation
    """

    def __init__(self):
        """Initialize the connection manager."""
        self._connections: dict[str, ButlerConnection] = {}
        self._active_connections: dict[str, Any] = {}

    def register_connection(self, connection: ButlerConnection) -> None:
        """Register a connection.

        Args:
            connection: Butler connection
        """
        self._connections[connection.connection_id] = connection
        logger.info(
            "connection_registered",
            connection_id=connection.connection_id,
            service=connection.service_name,
        )

    def unregister_connection(self, connection_id: str) -> None:
        """Unregister a connection.

        Args:
            connection_id: Connection ID
        """
        if connection_id in self._connections:
            del self._connections[connection_id]
            logger.info("connection_unregistered", connection_id=connection_id)

    def get_connection(self, connection_id: str) -> ButlerConnection | None:
        """Get a connection by ID.

        Args:
            connection_id: Connection ID

        Returns:
            Butler connection or None
        """
        return self._connections.get(connection_id)

    def get_connections_by_service(self, service_name: str) -> list[ButlerConnection]:
        """Get connections for a service.

        Args:
            service_name: Service name

        Returns:
            List of connections
        """
        return [conn for conn in self._connections.values() if conn.service_name == service_name]

    def get_active_connection(self, connection_id: str) -> Any | None:
        """Get an active connection instance.

        Args:
            connection_id: Connection ID

        Returns:
            Active connection or None
        """
        return self._active_connections.get(connection_id)

    async def activate_connection(self, connection_id: str) -> bool:
        """Activate a connection.

        Args:
            connection_id: Connection ID

        Returns:
            True if activated
        """
        connection = self._connections.get(connection_id)
        if not connection or not connection.is_active:
            return False

        # In production, this would create the actual connection
        self._active_connections[connection_id] = {"connection": connection, "status": "active"}
        logger.info("connection_activated", connection_id=connection_id)
        return True

    async def deactivate_connection(self, connection_id: str) -> bool:
        """Deactivate a connection.

        Args:
            connection_id: Connection ID

        Returns:
            True if deactivated
        """
        if connection_id in self._active_connections:
            del self._active_connections[connection_id]
            logger.info("connection_deactivated", connection_id=connection_id)
            return True

        return False

    def get_all_connections(self) -> dict[str, ButlerConnection]:
        """Get all connections.

        Returns:
            Dictionary of connections
        """
        return self._connections.copy()

    def get_connection_status(self, connection_id: str) -> str:
        """Get connection status.

        Args:
            connection_id: Connection ID

        Returns:
            Status string
        """
        if connection_id not in self._connections:
            return "not_found"

        connection = self._connections[connection_id]
        if not connection.is_active:
            return "inactive"

        if connection_id in self._active_connections:
            return "active"

        return "registered"


class ButlerAuthMiddleware:
    """Authentication middleware for LangChain agents.

    This middleware:
    - Validates JWT tokens before agent execution
    - Checks tenant/account access permissions
    - Injects user context into ButlerAgentState
    - Handles auth failures

    Production integration (Phase A.5):
    - Implements ButlerBaseMiddleware interface
    - Validates JWT tokens via Butler's auth service
    - Checks tenant/account access
    - Runs at PRE_MODEL hook
    """

    def __init__(self, auth_context: ButlerAuthContext, enabled: bool = True):
        """Initialize the auth middleware.

        Args:
            auth_context: Butler auth context
            enabled: Whether middleware is enabled
        """
        self._auth_context = auth_context
        self.enabled = enabled

    async def validate_jwt_token(self, token: str) -> bool:
        """Validate a JWT token.

        Args:
            token: JWT token string

        Returns:
            True if token is valid
        """
        # In production, this would validate against Butler's JWKS endpoint
        # For now, basic validation
        if not token or not token.startswith("Bearer "):
            return False

        # TODO: Integrate with domain/auth/contracts.py for real JWT validation
        # Use RS256/ES256 with JWKS as per Butler rules
        self._auth_context.set_auth_token(token)
        return True

    async def check_tenant_access(self, tenant_id: str, account_id: str) -> bool:
        """Check if account has access to tenant.

        Args:
            tenant_id: Tenant UUID
            account_id: Account UUID

        Returns:
            True if access granted
        """
        # In production, check tenant-account mapping in database
        # For now, basic check
        identity = self._auth_context.get_identity()
        if not identity:
            return False

        return identity.tenant_id == tenant_id and identity.account_id == account_id

    async def pre_model(self, context: Any) -> Any:
        """Pre-model hook for authentication.

        Args:
            context: ButlerMiddlewareContext

        Returns:
            MiddlewareResult
        """
        from langchain.middleware.base import MiddlewareResult

        if not self.enabled:
            return MiddlewareResult(success=True, should_continue=True)

        # Check authentication
        if not self._auth_context.is_authenticated():
            logger.warning("auth_failed_not_authenticated", session_id=context.session_id)
            return MiddlewareResult(
                success=False, should_continue=False, error="Authentication required"
            )

        # Check tenant/account access
        has_access = await self.check_tenant_access(context.tenant_id, context.account_id)
        if not has_access:
            logger.warning(
                "auth_failed_access_denied",
                tenant_id=context.tenant_id,
                account_id=context.account_id,
            )
            return MiddlewareResult(
                success=False, should_continue=False, error="Access denied: tenant/account mismatch"
            )

        # Inject identity into context
        identity = self._auth_context.get_identity()
        if identity:
            context.metadata.update(
                {
                    "account_id": identity.account_id,
                    "user_id": identity.user_id,
                    "tenant_id": identity.tenant_id,
                    "roles": identity.roles,
                    "permissions": identity.permissions,
                }
            )

        logger.info(
            "auth_success",
            tenant_id=context.tenant_id,
            account_id=context.account_id,
            user_id=context.user_id,
        )

        return MiddlewareResult(success=True, should_continue=True)

    async def process(self, context: Any, hook: Any) -> Any:
        """Process middleware for given hook.

        Args:
            context: ButlerMiddlewareContext
            hook: MiddlewareOrder

        Returns:
            MiddlewareResult
        """
        from langchain.middleware.base import MiddlewareOrder, MiddlewareResult

        if not self.enabled:
            return MiddlewareResult(success=True, should_continue=True)

        if hook == MiddlewareOrder.PRE_MODEL:
            return await self.pre_model(context)
        return MiddlewareResult(success=True, should_continue=True)

    # Legacy methods for backward compatibility
    def authenticate(self, token: str) -> bool:
        """Authenticate with a token (legacy sync method)."""
        # In production, this would validate the token
        self._auth_context.set_auth_token(token)
        return True

    def authorize(self, permission: str) -> bool:
        """Authorize a permission (legacy sync method)."""
        return self._auth_context.has_permission(permission)

    def require_auth(self) -> ButlerAuthContext:
        """Require authentication (legacy sync method)."""
        if not self._auth_context.is_authenticated():
            raise Exception("Authentication required")

        return self._auth_context

    def require_permission(self, permission: str) -> bool:
        """Require a permission (legacy sync method)."""
        if not self.authorize(permission):
            raise Exception(f"Permission required: {permission}")

        return True

    def inject_identity(self, context: dict[str, Any]) -> dict[str, Any]:
        """Inject identity into context (legacy sync method)."""
        identity = self._auth_context.get_identity()
        if identity:
            context["account_id"] = identity.account_id
            context["user_id"] = identity.user_id
            context["tenant_id"] = identity.tenant_id
            context["roles"] = identity.roles
            context["permissions"] = identity.permissions

        return context


class ButlerAgentAuth:
    """Combined auth system for LangChain agents.

    This system:
    - Combines auth context and connection management
    - Provides unified auth interface
    - Integrates with LangChain middleware
    """

    def __init__(self):
        """Initialize the agent auth system."""
        self._auth_context = ButlerAuthContext()
        self._connection_manager = ButlerConnectionManager()
        self._auth_middleware = ButlerAuthMiddleware(self._auth_context)

    @property
    def auth_context(self) -> ButlerAuthContext:
        """Get the auth context."""
        return self._auth_context

    @property
    def connection_manager(self) -> ButlerConnectionManager:
        """Get the connection manager."""
        return self._connection_manager

    @property
    def auth_middleware(self) -> ButlerAuthMiddleware:
        """Get the auth middleware."""
        return self._auth_middleware

    def setup_identity(
        self,
        account_id: str,
        user_id: str | None = None,
        tenant_id: str = "",
        roles: list[str] | None = None,
        permissions: list[str] | None = None,
    ) -> None:
        """Setup identity for the agent.

        Args:
            account_id: Account ID
            user_id: Optional user ID
            tenant_id: Tenant ID
            roles: Optional roles
            permissions: Optional permissions
        """
        identity = ButlerIdentity(
            account_id=account_id,
            user_id=user_id,
            tenant_id=tenant_id,
            roles=roles or [],
            permissions=permissions or [],
        )
        self._auth_context.set_identity(identity)
        logger.info("agent_identity_setup", account_id=account_id)

    def add_connection(
        self,
        connection_id: str,
        connection_type: str,
        service_name: str,
        config: dict[str, Any],
    ) -> None:
        """Add a connection.

        Args:
            connection_id: Connection ID
            connection_type: Connection type
            service_name: Service name
            config: Connection config
        """
        connection = ButlerConnection(
            connection_id=connection_id,
            connection_type=connection_type,
            service_name=service_name,
            config=config,
        )
        self._connection_manager.register_connection(connection)

    async def activate_all_connections(self) -> dict[str, bool]:
        """Activate all registered connections.

        Returns:
            Dictionary of connection ID to success status
        """
        results = {}
        for conn_id in self._connection_manager.get_all_connections():
            results[conn_id] = await self._connection_manager.activate_connection(conn_id)
        return results

    def get_auth_headers(self) -> dict[str, str]:
        """Get auth headers for requests.

        Returns:
            Dictionary of headers
        """
        headers = {}
        token = self._auth_context.get_auth_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        identity = self._auth_context.get_identity()
        if identity:
            headers["X-Account-ID"] = identity.account_id
            if identity.user_id:
                headers["X-User-ID"] = identity.user_id
            if identity.tenant_id:
                headers["X-Tenant-ID"] = identity.tenant_id

        return headers

    def clear_auth(self) -> None:
        """Clear authentication state."""
        self._auth_context.clear_session()
        self._auth_context._auth_token = None
        self._auth_context._identity = None
        logger.info("agent_auth_cleared")
