"""
Tenant Resolver - Tenant Identity Resolution

Resolves tenant identity from JWT/session at gateway.
Creates immutable TenantContext. Never reconstructs downstream.
"""

from __future__ import annotations

import uuid

from .context import IsolationLevel, TenantContext


class TenantResolver:
    """
    Resolves tenant identity from validated JWT/session.

    Called at gateway/middleware layer only.
    Creates immutable TenantContext once per request.
    Never called inside downstream services.

    TODO: Integrate with JWT/JWKS validation from gateway.
    TODO: Query tenant registry for plan, region, isolation_level.
    TODO: Validate account_id, user_id against tenant membership.
    """

    async def resolve_from_jwt(
        self,
        jwt_payload: dict,
        request_id: str,
    ) -> TenantContext:
        """
        Resolve tenant context from validated JWT payload.

        JWT must be validated by gateway before this call.
        This method only extracts and normalizes tenant identity.

        Args:
            jwt_payload: Validated JWT payload with tenant claims
            request_id: Unique request identifier

        Returns:
            Immutable TenantContext

        Raises:
            ValueError: If required tenant claims missing or invalid
        """
        # Extract required fields from JWT
        tenant_id = jwt_payload.get("tenant_id")
        if not tenant_id:
            raise ValueError("JWT missing required tenant_id claim")

        account_id = jwt_payload.get("account_id")
        if not account_id:
            raise ValueError("JWT missing required account_id claim")

        user_id = jwt_payload.get("sub") or jwt_payload.get("user_id")
        if not user_id:
            raise ValueError("JWT missing required user_id claim")

        # Extract optional fields
        tenant_slug = jwt_payload.get("tenant_slug")
        org_id = jwt_payload.get("org_id")

        # Extract plan and region (TODO: query tenant registry)
        plan = jwt_payload.get("plan", "free")
        region = jwt_payload.get("region", "us-east-1")

        # Extract isolation level (TODO: query tenant registry)
        isolation_level_str = jwt_payload.get("isolation_level", "shared")
        try:
            isolation_level = IsolationLevel(isolation_level_str)
        except ValueError:
            isolation_level = IsolationLevel.SHARED

        # Extract session and actor info
        session_id = jwt_payload.get("session_id", str(uuid.uuid4()))
        actor_type = jwt_payload.get("actor_type", "user")
        scopes = frozenset(jwt_payload.get("scopes", []))

        # Extract metadata
        metadata = jwt_payload.get("metadata", {})

        return TenantContext(
            tenant_id=tenant_id,
            account_id=account_id,
            user_id=user_id,
            plan=plan,
            region=region,
            isolation_level=isolation_level,
            request_id=request_id,
            session_id=session_id,
            actor_type=actor_type,
            scopes=scopes,
            metadata=metadata,
            tenant_slug=tenant_slug,
            org_id=org_id,
        )

    async def resolve_from_session(
        self,
        session_data: dict,
        request_id: str,
    ) -> TenantContext:
        """
        Resolve tenant context from validated session data.

        Used for API key auth or session cookie auth.

        Args:
            session_data: Validated session data with tenant info
            request_id: Unique request identifier

        Returns:
            Immutable TenantContext

        Raises:
            ValueError: If required session fields missing or invalid
        """
        # Similar to JWT resolution but from session store
        # TODO: Implement session-based resolution
        raise NotImplementedError("Session-based resolution not yet implemented")
