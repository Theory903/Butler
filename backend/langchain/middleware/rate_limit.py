"""Butler Rate Limit Middleware.

Wraps RateLimiter to enforce per-tenant rate limits on agent execution.
"""

import logging

from langchain.middleware.base import (
    ButlerBaseMiddleware,
    ButlerMiddlewareContext,
    MiddlewareResult,
)
from services.gateway.rate_limiter import RateLimiter

import structlog

logger = structlog.get_logger(__name__)


class ButlerRateLimitMiddleware(ButlerBaseMiddleware):
    """Middleware for per-tenant rate limiting.

    Runs on PRE_MODEL hook to check rate limit before inference.
    """

    def __init__(
        self,
        rate_limiter: RateLimiter | None = None,
        enabled: bool = True,
        cost_per_request: int = 1,
    ):
        super().__init__(enabled=enabled)
        self._rate_limiter = rate_limiter
        self._cost_per_request = cost_per_request

    async def pre_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Check rate limit before model inference."""
        if not self._rate_limiter:
            return MiddlewareResult(success=True, should_continue=True)

        try:
            result = await self._rate_limiter.check(
                account_id=context.account_id,
                cost=self._cost_per_request,
            )

            if not result.allowed:
                logger.warning(
                    "rate_limit_exceeded",
                    account_id=context.account_id,
                    remaining=result.remaining,
                    limit=result.limit,
                )
                return MiddlewareResult(
                    success=False,
                    should_continue=False,
                    error=f"Rate limit exceeded. Remaining: {result.remaining}/{result.limit}",
                    metadata={
                        "remaining": result.remaining,
                        "limit": result.limit,
                        "reset": result.reset,
                    },
                )

            logger.info(
                "rate_limit_check_passed",
                account_id=context.account_id,
                remaining=result.remaining,
                limit=result.limit,
            )

            return MiddlewareResult(
                success=True,
                should_continue=True,
                metadata={
                    "rate_limit_remaining": result.remaining,
                    "rate_limit_limit": result.limit,
                },
            )
        except Exception as exc:
            logger.warning("rate_limit_check_failed", error=str(exc))
            # Fail open: allow request if rate limiter fails
            return MiddlewareResult(success=True, should_continue=True)
