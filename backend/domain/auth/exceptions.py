"""Auth domain exceptions — RFC 9457 Problem Details.

All auth errors inherit from core.errors.Problem so the global
exception handler returns application/problem+json automatically.
"""

from __future__ import annotations

from core.errors import Problem


class AuthErrors:
    """Factory namespace for auth-related Problem instances."""

    INVALID_CREDENTIALS = Problem(
        type="invalid-credentials",
        title="Invalid Credentials",
        status=401,
        detail="The email or password provided is incorrect.",
    )

    EMAIL_ALREADY_REGISTERED = Problem(
        type="email-taken",
        title="Email Already Registered",
        status=409,
        detail="An account with this email address already exists.",
    )

    TOKEN_EXPIRED = Problem(
        type="token-expired",
        title="Token Expired",
        status=401,
        detail="The access token has expired. Use the refresh endpoint to obtain a new one.",
    )

    TOKEN_FAMILY_COMPROMISED = Problem(
        type="token-reuse-detected",
        title="Token Family Compromised",
        status=401,
        detail=(
            "Refresh token reuse detected. "
            "All sessions in this token family have been revoked for your security. "
            "Please log in again."
        ),
    )

    INVALID_TOKEN = Problem(
        type="invalid-token",
        title="Invalid Token",
        status=401,
        detail="The provided token is invalid or malformed.",
    )

    SESSION_REVOKED = Problem(
        type="session-revoked",
        title="Session Revoked",
        status=401,
        detail="This session has been revoked. Please log in again.",
    )

    SESSION_EXPIRED = Problem(
        type="session-expired",
        title="Session Expired",
        status=401,
        detail="This session has expired. Please log in again.",
    )

    ACCOUNT_SUSPENDED = Problem(
        type="account-suspended",
        title="Account Suspended",
        status=403,
        detail="Your account has been suspended. Contact support for assistance.",
    )

    ACCOUNT_DELETED = Problem(
        type="account-deleted",
        title="Account Not Found",
        status=401,
        detail="No active account found for the provided credentials.",
    )


class GatewayErrors:
    """Factory namespace for gateway-related Problem instances."""

    MISSING_AUTH = Problem(
        type="missing-authorization",
        title="Authorization Required",
        status=401,
        detail="A valid Bearer token is required in the Authorization header.",
    )

    TOKEN_EXPIRED = Problem(
        type="token-expired",
        title="Token Expired",
        status=401,
        detail="The access token has expired. Use the refresh endpoint.",
    )

    INVALID_TOKEN = Problem(
        type="invalid-token",
        title="Invalid Token",
        status=401,
        detail="The provided token is invalid or could not be verified.",
    )

    SESSION_REVOKED = Problem(
        type="session-revoked",
        title="Session Revoked",
        status=401,
        detail="The session associated with this token has been revoked.",
    )

    @staticmethod
    def rate_limited(retry_after: int, remaining: int = 0) -> Problem:
        return Problem(
            type="rate-limit-exceeded",
            title="Rate Limit Exceeded",
            status=429,
            detail=f"Too many requests. Please retry after {retry_after} seconds.",
            retry_after=retry_after,
            limit_remaining=remaining,
        )

    IDEMPOTENCY_CONFLICT = Problem(
        type="idempotency-conflict",
        title="Idempotent Request In Progress",
        status=409,
        detail="A request with this idempotency key is already being processed.",
    )

    INTERNAL_ERROR = Problem(
        type="internal-error",
        title="Internal Server Error",
        status=500,
        detail="An unexpected error prevented Butler from completing your request.",
    )

    STREAM_FAILED = Problem(
        type="stream-failed",
        title="Stream Setup Failed",
        status=502,
        detail="The response stream could not be established.",
    )

    MCP_SESSION_EXPIRED = Problem(
        type="mcp-session-expired",
        title="MCP Session Expired",
        status=404,
        detail="The MCP session has expired or does not exist. Send an initialize request to start a new session.",
    )

