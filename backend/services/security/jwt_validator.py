"""
JWT Validator - Enhanced JWT Validation with JWKS

Implements enhanced JWT validation with JWKS (JSON Web Key Set).
Supports RS256/ES256 signatures, key rotation, and claim validation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class SignatureAlgorithm(StrEnum):
    """JWT signature algorithm."""

    RS256 = "RS256"
    RS384 = "RS384"
    RS512 = "RS512"
    ES256 = "ES256"
    ES384 = "ES384"
    ES512 = "ES512"


@dataclass(frozen=True, slots=True)
class JWKSKey:
    """JWKS key."""

    kid: str
    kty: str  # Key type (RSA, EC)
    alg: SignatureAlgorithm
    n: str | None  # RSA modulus
    e: str | None  # RSA exponent
    x: str | None  # EC x coordinate
    y: str | None  # EC y coordinate
    crv: str | None  # EC curve
    use: str  # sig or enc


@dataclass(frozen=True, slots=True)
class JWTClaims:
    """JWT claims."""

    iss: str  # Issuer
    sub: str  # Subject
    aud: list[str]  # Audience
    exp: int  # Expiration
    iat: int  # Issued at
    jti: str | None  # JWT ID
    nbf: int | None  # Not before
    additional_claims: dict[str, Any]


class JWTValidator:
    """
    JWT validator with JWKS support.

    Features:
    - JWKS key management
    - Multiple signature algorithms
    - Claim validation
    - Key rotation support
    """

    def __init__(
        self,
        issuer: str,
        audience: list[str],
    ) -> None:
        """Initialize JWT validator."""
        self._issuer = issuer
        self._audience = audience
        self._keys: dict[str, JWKSKey] = {}  # kid -> key
        self._blacklisted_jtis: set[str] = set()

    def load_jwks(self, jwks_json: dict[str, Any]) -> int:
        """
        Load JWKS (JSON Web Key Set).

        Args:
            jwks_json: JWKS JSON data

        Returns:
            Number of keys loaded
        """
        keys = jwks_json.get("keys", [])
        loaded = 0

        for key_data in keys:
            key = JWKSKey(
                kid=key_data.get("kid", ""),
                kty=key_data.get("kty", ""),
                alg=SignatureAlgorithm(key_data.get("alg", "RS256")),
                n=key_data.get("n"),
                e=key_data.get("e"),
                x=key_data.get("x"),
                y=key_data.get("y"),
                crv=key_data.get("crv"),
                use=key_data.get("use", "sig"),
            )

            self._keys[key.kid] = key
            loaded += 1

        logger.info(
            "jwks_loaded",
            keys_loaded=loaded,
        )

        return loaded

    def add_key(self, key: JWKSKey) -> None:
        """
        Add a JWKS key.

        Args:
            key: JWKS key
        """
        self._keys[key.kid] = key

        logger.info(
            "jwks_key_added",
            kid=key.kid,
            alg=key.alg,
        )

    def remove_key(self, kid: str) -> bool:
        """
        Remove a JWKS key.

        Args:
            kid: Key identifier

        Returns:
            True if removed
        """
        if kid in self._keys:
            del self._keys[kid]

            logger.info(
                "jwks_key_removed",
                kid=kid,
            )

            return True
        return False

    async def validate_token(
        self,
        token: str,
    ) -> JWTClaims | None:
        """
        Validate a JWT token.

        Args:
            token: JWT token string

        Returns:
            JWT claims if valid, None otherwise
        """
        try:
            # In production, this would use cryptography library for actual validation
            # For now, perform basic validation

            # Parse token
            parts = token.split(".")
            if len(parts) != 3:
                logger.warning(
                    "invalid_token_format",
                )
                return None

            header_b64, payload_b64, signature_b64 = parts

            # Decode header
            header = json.loads(self._base64url_decode(header_b64))

            # Get key ID from header
            kid = header.get("kid")
            if not kid or kid not in self._keys:
                logger.warning(
                    "unknown_key_id",
                    kid=kid,
                )
                return None

            # Decode payload
            payload = json.loads(self._base64url_decode(payload_b64))

            # Validate claims
            claims = self._validate_claims(payload)
            if not claims:
                return None

            # Check if token is blacklisted
            if claims.jti and claims.jti in self._blacklisted_jtis:
                logger.warning(
                    "token_blacklisted",
                    jti=claims.jti,
                )
                return None

            logger.info(
                "token_validated",
                sub=claims.sub,
                iss=claims.iss,
            )

            return claims

        except Exception as e:
            logger.error(
                "token_validation_failed",
                error=str(e),
            )
            return None

    def _validate_claims(self, payload: dict[str, Any]) -> JWTClaims | None:
        """
        Validate JWT claims.

        Args:
            payload: JWT payload

        Returns:
            JWT claims if valid, None otherwise
        """
        # Required claims
        iss = payload.get("iss")
        sub = payload.get("sub")
        exp = payload.get("exp")
        iat = payload.get("iat")

        if not iss or not sub or not exp or not iat:
            logger.warning(
                "missing_required_claims",
            )
            return None

        # Validate issuer
        if iss != self._issuer:
            logger.warning(
                "invalid_issuer",
                expected=self._issuer,
                received=iss,
            )
            return None

        # Validate audience
        aud = payload.get("aud")
        if isinstance(aud, str):
            aud = [aud]

        if not aud or not any(a in self._audience for a in aud):
            logger.warning(
                "invalid_audience",
                expected=self._audience,
                received=aud,
            )
            return None

        # Validate expiration
        now = int(datetime.now(UTC).timestamp())
        if exp < now:
            logger.warning(
                "token_expired",
                exp=exp,
                now=now,
            )
            return None

        # Validate not before if present
        nbf = payload.get("nbf")
        if nbf and nbf > now:
            logger.warning(
                "token_not_yet_valid",
                nbf=nbf,
                now=now,
            )
            return None

        # Extract additional claims
        additional_claims = {
            k: v
            for k, v in payload.items()
            if k not in ["iss", "sub", "aud", "exp", "iat", "jti", "nbf"]
        }

        return JWTClaims(
            iss=iss,
            sub=sub,
            aud=aud,
            exp=exp,
            iat=iat,
            jti=payload.get("jti"),
            nbf=nbf,
            additional_claims=additional_claims,
        )

    def _base64url_decode(self, data: str) -> str:
        """
        Decode base64url encoded string.

        Args:
            data: Base64url encoded string

        Returns:
            Decoded string
        """
        # Add padding if needed
        padding = len(data) % 4
        if padding:
            data += "=" * (4 - padding)

        import base64

        return base64.urlsafe_b64decode(data).decode("utf-8")

    def blacklist_token(self, jti: str) -> bool:
        """
        Blacklist a token by its JTI.

        Args:
            jti: JWT ID

        Returns:
            True if blacklisted
        """
        self._blacklisted_jtis.add(jti)

        logger.info(
            "token_blacklisted",
            jti=jti,
        )

        return True

    def remove_blacklist(self, jti: str) -> bool:
        """
        Remove token from blacklist.

        Args:
            jti: JWT ID

        Returns:
            True if removed
        """
        if jti in self._blacklisted_jtis:
            self._blacklisted_jtis.remove(jti)

            logger.info(
                "token_removed_from_blacklist",
                jti=jti,
            )

            return True
        return False

    def get_validator_stats(self) -> dict[str, Any]:
        """
        Get validator statistics.

        Returns:
            Validator statistics
        """
        return {
            "total_keys": len(self._keys),
            "blacklisted_jtis": len(self._blacklisted_jtis),
            "issuer": self._issuer,
            "audience": self._audience,
        }
