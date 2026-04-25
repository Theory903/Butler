"""
OAuth2/OIDC Provider Integration

Implements OAuth2 and OpenID Connect provider integration.
Supports authorization code flow, token validation, and user info retrieval.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class GrantType(StrEnum):
    """OAuth2 grant type."""

    AUTHORIZATION_CODE = "authorization_code"
    REFRESH_TOKEN = "refresh_token"
    CLIENT_CREDENTIALS = "client_credentials"


@dataclass(frozen=True, slots=True)
class OAuth2Client:
    """OAuth2 client configuration."""

    client_id: str
    client_secret_hash: str
    redirect_uris: list[str]
    scopes: list[str]
    grant_types: list[GrantType]


@dataclass(frozen=True, slots=True)
class AuthorizationCode:
    """Authorization code for OAuth2 flow."""

    code: str
    client_id: str
    user_id: str
    redirect_uri: str
    scopes: list[str]
    expires_at: datetime
    nonce: str | None


@dataclass(frozen=True, slots=True)
class AccessToken:
    """Access token."""

    token: str
    token_type: str
    expires_at: datetime
    scopes: list[str]
    user_id: str
    client_id: str


class OAuth2Provider:
    """
    OAuth2/OIDC provider for authentication.

    Features:
    - Authorization code flow
    - Token issuance
    - Token validation
    - User info retrieval
    """

    def __init__(self) -> None:
        """Initialize OAuth2 provider."""
        self._clients: dict[str, OAuth2Client] = {}
        self._authorization_codes: dict[str, AuthorizationCode] = {}
        self._access_tokens: dict[str, AccessToken] = {}
        self._refresh_tokens: dict[str, AccessToken] = {}

    def register_client(
        self,
        client_id: str,
        client_secret: str,
        redirect_uris: list[str],
        scopes: list[str],
        grant_types: list[GrantType],
    ) -> OAuth2Client:
        """
        Register an OAuth2 client.

        Args:
            client_id: Client identifier
            client_secret: Client secret
            redirect_uris: Allowed redirect URIs
            scopes: Allowed scopes
            grant_types: Allowed grant types

        Returns:
            OAuth2 client
        """
        client_secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()

        client = OAuth2Client(
            client_id=client_id,
            client_secret_hash=client_secret_hash,
            redirect_uris=redirect_uris,
            scopes=scopes,
            grant_types=grant_types,
        )

        self._clients[client_id] = client

        logger.info(
            "oauth2_client_registered",
            client_id=client_id,
        )

        return client

    async def create_authorization_code(
        self,
        client_id: str,
        user_id: str,
        redirect_uri: str,
        scopes: list[str],
        nonce: str | None = None,
        expires_in_seconds: int = 600,
    ) -> str:
        """
        Create an authorization code.

        Args:
            client_id: Client identifier
            user_id: User identifier
            redirect_uri: Redirect URI
            scopes: Requested scopes
            nonce: Optional nonce for OIDC
            expires_in_seconds: Code expiration time

        Returns:
            Authorization code
        """
        if client_id not in self._clients:
            raise ValueError(f"Client not registered: {client_id}")

        client = self._clients[client_id]

        if redirect_uri not in client.redirect_uris:
            raise ValueError(f"Invalid redirect URI: {redirect_uri}")

        code = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in_seconds)

        auth_code = AuthorizationCode(
            code=code,
            client_id=client_id,
            user_id=user_id,
            redirect_uri=redirect_uri,
            scopes=scopes,
            expires_at=expires_at,
            nonce=nonce,
        )

        self._authorization_codes[code] = auth_code

        logger.info(
            "authorization_code_created",
            client_id=client_id,
            user_id=user_id,
        )

        return code

    async def exchange_code_for_token(
        self,
        code: str,
        client_id: str,
        client_secret: str,
    ) -> AccessToken:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code
            client_id: Client identifier
            client_secret: Client secret

        Returns:
            Access token
        """
        auth_code = self._authorization_codes.get(code)

        if not auth_code:
            raise ValueError("Invalid authorization code")

        if auth_code.client_id != client_id:
            raise ValueError("Client ID mismatch")

        if auth_code.expires_at < datetime.now(UTC):
            raise ValueError("Authorization code expired")

        # Verify client secret
        client = self._clients.get(client_id)
        if not client:
            raise ValueError(f"Client not registered: {client_id}")

        client_secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()
        if client.client_secret_hash != client_secret_hash:
            raise ValueError("Invalid client secret")

        # Create access token
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        access_token = AccessToken(
            token=token,
            token_type="Bearer",
            expires_at=expires_at,
            scopes=auth_code.scopes,
            user_id=auth_code.user_id,
            client_id=client_id,
        )

        self._access_tokens[token] = access_token

        # Remove used authorization code
        del self._authorization_codes[code]

        logger.info(
            "access_token_issued",
            client_id=client_id,
            user_id=auth_code.user_id,
        )

        return access_token

    async def validate_token(
        self,
        token: str,
        required_scopes: list[str] | None = None,
    ) -> AccessToken | None:
        """
        Validate an access token.

        Args:
            token: Access token
            required_scopes: Required scopes

        Returns:
            Access token if valid, None otherwise
        """
        access_token = self._access_tokens.get(token)

        if not access_token:
            return None

        if access_token.expires_at < datetime.now(UTC):
            del self._access_tokens[token]
            return None

        if required_scopes:
            for scope in required_scopes:
                if scope not in access_token.scopes:
                    return None

        return access_token

    async def refresh_token(
        self,
        refresh_token: str,
        client_id: str,
        client_secret: str,
    ) -> AccessToken:
        """
        Refresh an access token.

        Args:
            refresh_token: Refresh token
            client_id: Client identifier
            client_secret: Client secret

        Returns:
            New access token
        """
        # In production, this would validate refresh token and issue new access token
        # For now, return the existing access token
        raise NotImplementedError("Token refresh not implemented")

    def get_user_info(
        self,
        user_id: str,
    ) -> dict[str, Any]:
        """
        Get user information.

        Args:
            user_id: User identifier

        Returns:
            User information
        """
        # In production, this would fetch from user database
        return {
            "sub": user_id,
            "name": f"User {user_id}",
            "email": f"{user_id}@example.com",
        }

    def revoke_token(self, token: str) -> bool:
        """
        Revoke an access token.

        Args:
            token: Access token

        Returns:
            True if revoked
        """
        if token in self._access_tokens:
            del self._access_tokens[token]

            logger.info(
                "access_token_revoked",
            )

            return True
        return False

    def get_provider_stats(self) -> dict[str, Any]:
        """
        Get provider statistics.

        Returns:
            Provider statistics
        """
        return {
            "total_clients": len(self._clients),
            "active_auth_codes": len(self._authorization_codes),
            "active_access_tokens": len(self._access_tokens),
            "active_refresh_tokens": len(self._refresh_tokens),
        }
