"""RS256 JWT manager with full RFC 7517 JWKS document.

Key rules (from docs/rules/SYSTEM_RULES.md):
  - Algorithm: RS256 ONLY. HS256 is NEVER used.
  - Claims: iss, aud, iat, exp, jti, sub, sid, aal
  - Issuer + audience validated on every verify
  - JWKS document exposes full RSA public key material (n, e)

In development, a 2048-bit RSA key pair is generated in memory.
In production, load from PEM files via JWT_PRIVATE_KEY_PATH setting.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

import jwt


def _b64url(data: bytes) -> str:
    """Base64url-encode without padding (per RFC 7517)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _int_to_bytes(n: int) -> bytes:
    length = (n.bit_length() + 7) // 8
    return n.to_bytes(length, "big")


class JWK:
    """Represents a single RSA key in the JWKS lifecycle."""

    def __init__(self, private_key: RSAPrivateKey, key_id: str, state: str = "active_signing"):
        self.private_key = private_key
        self.public_key: RSAPublicKey = private_key.public_key()  # type: ignore
        self.key_id = key_id
        self.state = state  # active_signing | active_verify_only | retired | revoked

        # Pre-compute key material
        pub_numbers = self.public_key.public_numbers()
        self.n = _b64url(_int_to_bytes(pub_numbers.n))
        self.e = _b64url(_int_to_bytes(pub_numbers.e))

        # PEMs for signing/verification
        self.private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self.public_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )


class JWKSManager:
    """Production JWKS manager with key rotation states."""

    def __init__(self, issuer: str, audience: str):
        self._issuer = issuer
        self._audience = audience
        self._keys: dict[str, JWK] = {}
        self._active_signing_kid: str | None = None

    def add_key(self, key: JWK):
        self._keys[key.key_id] = key
        if key.state == "active_signing":
            self._active_signing_kid = key.key_id

    # ── Token signing ──────────────────────────────────────────────────────────

    def sign_access_token(self, claims: dict, ttl: timedelta) -> str:
        if not self._active_signing_kid:
            raise RuntimeError("No active signing key configured")

        signing_key = self._keys[self._active_signing_kid]
        now = datetime.now(UTC)

        payload = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": str(claims["sub"]),  # Principal ID
            "sid": str(claims["sid"]),  # Session ID
            "aid": str(claims["aid"]),  # Active Account ID (Context)
            "amr": claims.get("amr", ["pwd"]),  # Auth Methods Reference
            "acr": claims.get("acr", "aal1"),  # Assurance Level
            "device_id": claims.get("device_id"),
            "scope": claims.get("scope", "butler:all"),
            "iat": now,
            "exp": now + ttl,
            "jti": str(uuid4()),
        }

        return jwt.encode(
            payload,
            signing_key.private_pem,
            algorithm="RS256",
            headers={"kid": signing_key.key_id, "typ": "at+jwt"},
        )

    def sign_refresh_token(
        self,
        claims: dict,
        family_id: str,
        ttl: timedelta,
    ) -> str:
        if not self._active_signing_kid:
            raise RuntimeError("No active signing key configured")

        signing_key = self._keys[self._active_signing_kid]
        now = datetime.now(UTC)

        payload = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": str(claims["sub"]),
            "sid": str(claims["sid"]),
            "fid": family_id,
            "typ": "refresh",
            "device_id": claims.get("device_id"),
            "iat": now,
            "exp": now + ttl,
            "jti": str(uuid4()),
        }

        return jwt.encode(
            payload,
            signing_key.private_pem,
            algorithm="RS256",
            headers={"kid": signing_key.key_id},
        )

    # ── Token verification ─────────────────────────────────────────────────────

    def verify_token(
        self,
        token: str,
        audience: str | None = None,
        issuer: str | None = None,
        leeway: int = 0,
    ) -> dict:
        """Verify JWT signature by looking up kid in JWKS pool."""
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid or kid not in self._keys:
            raise jwt.exceptions.InvalidKeyError(f"Missing or invalid kid: {kid}")

        key = self._keys[kid]
        if key.state == "revoked":
            raise jwt.exceptions.InvalidKeyError("Key revoked")

        return jwt.decode(
            token,
            key.public_pem,
            algorithms=["RS256"],
            issuer=issuer or self._issuer,
            audience=audience or self._audience,
            leeway=leeway,
            options={"require": ["exp", "iat", "sub", "jti", "iss", "aud"]},
        )

    # ── JWKS document ──────────────────────────────────────────────────────────

    def get_jwks_document(self) -> dict:
        keys = []
        for key in self._keys.values():
            if key.state == "revoked":
                continue
            keys.append(
                {
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                    "kid": key.key_id,
                    "n": key.n,
                    "e": key.e,
                }
            )
        return {"keys": keys}


# ---------------------------------------------------------------------------
# Singleton Factory
# ---------------------------------------------------------------------------

_jwks_manager: JWKSManager | None = None


def get_jwks_manager() -> JWKSManager:
    global _jwks_manager
    if _jwks_manager is None:
        from infrastructure.config import settings

        mgr = JWKSManager(issuer=settings.JWT_ISSUER, audience=settings.JWT_AUDIENCE)

        # Load primary key
        if settings.JWT_PRIVATE_KEY_PATH:
            with open(settings.JWT_PRIVATE_KEY_PATH, "rb") as f:
                pkey = serialization.load_pem_private_key(f.read(), password=None)
        else:
            # Dev mode fallback
            pkey = rsa.generate_private_key(65537, 2048)

        mgr.add_key(JWK(pkey, key_id=settings.JWKS_KEY_ID, state="active_signing"))

        _jwks_manager = mgr

    return _jwks_manager
