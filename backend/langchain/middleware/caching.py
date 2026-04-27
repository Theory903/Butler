"""Butler Caching Middleware.

Implements SWR (Stale-While-Revalidate) cache integration for model responses.
"""

import hashlib
import json
import logging
from typing import Any

from langchain.middleware.base import (
    ButlerBaseMiddleware,
    ButlerMiddlewareContext,
    MiddlewareResult,
)

import structlog

logger = structlog.get_logger(__name__)


class ButlerCachingMiddleware(ButlerBaseMiddleware):
    """Middleware for SWR caching of model responses.

    Runs on PRE_MODEL to check cache, and POST_MODEL to update cache.
    """

    def __init__(
        self,
        enabled: bool = True,
        cache_ttl_seconds: int = 300,
        cache_size: int = 1000,
    ):
        super().__init__(enabled=enabled)
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache_size = cache_size
        self._cache: dict[str, dict[str, Any]] = {}

    def _generate_cache_key(self, messages: list[dict[str, Any]], model: str | None) -> str:
        """Generate a cache key from messages and model."""
        cache_input = {
            "messages": messages,
            "model": model,
        }
        cache_str = json.dumps(cache_input, sort_keys=True)
        return hashlib.sha256(cache_str.encode()).hexdigest()

    def _evict_if_needed(self):
        """Evict oldest entries if cache is full."""
        if len(self._cache) > self._cache_size:
            # Simple FIFO eviction (could be improved with LRU)
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

    def _get_cached(self, cache_key: str) -> dict[str, Any] | None:
        """Get cached entry if valid."""
        entry = self._cache.get(cache_key)
        if not entry:
            return None

        import time

        if time.time() - entry.get("timestamp", 0) > self._cache_ttl_seconds:
            del self._cache[cache_key]
            return None

        return entry

    async def pre_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Check cache before model inference."""
        if not context.messages:
            return MiddlewareResult(success=True, should_continue=True)

        cache_key = self._generate_cache_key(context.messages, context.model)
        cached = self._get_cached(cache_key)

        if cached:
            logger.info(
                "cache_hit",
                cache_key=cache_key[:16],
                model=context.model,
                age_seconds=cached.get("age_seconds", 0),
            )

            # Return cached response
            return MiddlewareResult(
                success=True,
                should_continue=True,
                modified_input={"cached_response": cached["response"]},
                metadata={"cache_hit": True, "cache_key": cache_key},
            )

        logger.info("cache_miss", cache_key=cache_key[:16], model=context.model)

        # Store cache key for post_model
        context.metadata["_butler_cache_key"] = cache_key
        return MiddlewareResult(success=True, should_continue=True)

    async def post_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Update cache after model inference."""
        cache_key = context.metadata.get("_butler_cache_key")
        if not cache_key:
            return MiddlewareResult(success=True, should_continue=True)

        # Extract response from context
        response = context.metadata.get("response")
        if not response:
            return MiddlewareResult(success=True, should_continue=True)

        import time

        self._evict_if_needed()

        self._cache[cache_key] = {
            "response": response,
            "timestamp": time.time(),
            "messages": context.messages.copy(),
            "model": context.model,
        }

        logger.info("cache_updated", cache_key=cache_key[:16], model=context.model)

        return MiddlewareResult(success=True, should_continue=True)

    def clear_cache(self):
        """Clear the entire cache."""
        self._cache.clear()
        logger.info("cache_cleared")

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "size": len(self._cache),
            "max_size": self._cache_size,
            "ttl_seconds": self._cache_ttl_seconds,
        }
