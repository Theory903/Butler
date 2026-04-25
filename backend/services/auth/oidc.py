from __future__ import annotations

import uuid
from datetime import UTC, datetime

from authlib.oauth2.rfc6749 import AuthorizationServer as _AuthorizationServer
from authlib.oauth2.rfc6749 import grants
from authlib.oauth2.rfc7636 import CodeChallenge
from authlib.oidc.core import IdToken, UserInfo
from authlib.oidc.core.grants import (
    OpenIDCode as _OpenIDCode,
)
from authlib.oidc.core.grants import (
    OpenIDToken as _OpenIDToken,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.auth.models import OAuthClient, OAuthCode, Principal
from infrastructure.config import settings
from services.auth.jwt import JWKSManager


class AsyncAuthorizationServer(_AuthorizationServer):
    """Custom Authlib AuthorizationServer adapted for Async SQLAlchemy."""

    def __init__(self, db: AsyncSession, jwks: JWKSManager, issuer: str):
        super().__init__()
        self.db = db
        self.jwks = jwks
        self.issuer = issuer

    async def query_client(self, client_id: str):
        return await self.db.scalar(select(OAuthClient).where(OAuthClient.client_id == client_id))

    async def save_token(self, token, request):
        # We handle token issuance via our own Butler Session logic
        # but Authlib wants to store its own DTOs if requested.
        pass


class AuthorizationCodeGrant(grants.AuthorizationCodeGrant):
    """Authorization Code Grant with mandatory PKCE support."""

    TOKEN_ENDPOINT_AUTH_METHODS = ["client_secret_basic", "client_secret_post", "none"]

    def generate_authorization_code(self):
        return str(uuid.uuid4())

    async def save_authorization_code(self, code, request):
        request.data.get("nonce")
        expires_at = datetime.now(UTC) + self.AUTHORIZATION_CODE_EXPIRES_IN

        auth_code = OAuthCode(
            code=code,
            client_id=request.client.client_id,
            redirect_uri=request.redirect_uri,
            scope=request.scope,
            principal_id=uuid.UUID(request.user.id),
            code_challenge=request.data.get("code_challenge"),
            code_challenge_method=request.data.get("code_challenge_method"),
            expires_at=expires_at,
        )
        self.server.db.add(auth_code)
        await self.server.db.flush()
        return auth_code

    async def query_authorization_code(self, code, client):
        item = await self.server.db.scalar(
            select(OAuthCode).where(OAuthCode.code == code, OAuthCode.client_id == client.client_id)
        )
        if item and not item.is_expired():
            return item
        return None

    async def delete_authorization_code(self, authorization_code):
        await self.server.db.delete(authorization_code)
        await self.server.db.flush()

    async def authenticate_user(self, authorization_code):
        return await self.server.db.get(Principal, authorization_code.principal_id)


class OpenIDCode(_OpenIDCode):
    def exists_nonce(self, nonce, request):
        # Redis check for nonce replay protection could go here
        return False

    def get_jwt_config(self, grant):
        return {
            "key": self.server.jwks.get_active_private_key(),
            "alg": "RS256",
            "iss": self.server.issuer,
            "exp": 3600,
        }

    def generate_user_info(self, user, scope):
        return UserInfo(sub=str(user.id), email=user.email)


class OpenIDToken(_OpenIDToken):
    def get_jwt_config(self, grant):
        return {
            "key": self.server.jwks.get_active_private_key(),
            "alg": "RS256",
            "iss": self.server.issuer,
            "exp": 3600,
        }

    def generate_id_token(self, token, user, auth_time, scope):
        return IdToken(
            iss=self.server.issuer,
            sub=str(user.id),
            aud=token["client_id"],
            iat=int(datetime.now(UTC).timestamp()),
            exp=int(datetime.now(UTC).timestamp()) + 3600,
            auth_time=auth_time,
        )


def get_oidc_discovery(issuer: str) -> dict:
    """Return OIDC discovery document (RFC 8414 / OIDC Discovery)."""
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/api/v1/auth/authorize",
        "token_endpoint": f"{issuer}/api/v1/auth/token",
        "userinfo_endpoint": f"{issuer}/api/v1/auth/userinfo",
        "jwks_uri": f"{issuer}/.well-known/jwks.json",
        "scopes_supported": ["openid", "profile", "email", "offline_access"],
        "response_types_supported": ["code", "id_token", "token id_token"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
        "claims_supported": ["sub", "iss", "email", "name"],
        "code_challenge_methods_supported": ["S256"],
    }


def create_oidc_server(db: AsyncSession, jwks: JWKSManager) -> AsyncAuthorizationServer:
    """Initialize and configure the OIDC Authorization Server."""
    server = AsyncAuthorizationServer(db, jwks, settings.JWT_ISSUER)

    # Register grants
    server.register_grant(
        AuthorizationCodeGrant,
        [
            OpenIDCode(jwks),
            OpenIDToken(jwks),
            CodeChallenge(required=True),
        ],
    )

    return server
