"""Content guard middleware for LangChain agents.

Integrates with Butler's ContentGuard service for safety checks.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.middleware.base import (
    ButlerBaseMiddleware,
    ButlerMiddlewareContext,
    MiddlewareOrder,
    MiddlewareResult,
)

logger = logging.getLogger(__name__)


class ContentGuardMiddleware(ButlerBaseMiddleware):
    """Middleware for content safety checks.

    This middleware:
    - Checks input content for PII, harmful content, policy violations
    - Checks output content for safety violations
    - Blocks or redacts unsafe content
    - Runs at PRE_MODEL and POST_MODEL hooks

    Production integration (Phase B.2):
    - Integrates with Butler's ContentGuard service
    - Multi-layer safety checks (PII, harmful content, policy)
    - Configurable blocking/redaction policies
    """

    def __init__(
        self,
        enabled: bool = True,
        block_pii: bool = True,
        block_harmful: bool = True,
        block_policy_violations: bool = True,
        redact_pii: bool = False,
    ):
        """Initialize content guard middleware.

        Args:
            enabled: Whether middleware is enabled
            block_pii: Whether to block PII in input/output
            block_harmful: Whether to block harmful content
            block_policy_violations: Whether to block policy violations
            redact_pii: Whether to redact PII instead of blocking
        """
        super().__init__(enabled=enabled)
        self._block_pii = block_pii
        self._block_harmful = block_harmful
        self._block_policy_violations = block_policy_violations
        self._redact_pii = redact_pii

        # Lazy load ContentGuard service
        self._content_guard = None

    def _get_content_guard(self) -> Any:
        """Get Butler's ContentGuard service (lazy load)."""
        if self._content_guard is None:
            try:
                from services.security.safety import ContentGuard

                self._content_guard = ContentGuard()
            except ImportError:
                logger.warning("content_guard_unavailable")
                return None
        return self._content_guard

    async def pre_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Check input content before model inference.

        Args:
            context: ButlerMiddlewareContext with input messages

        Returns:
            MiddlewareResult with potential blocking
        """
        if not self.enabled:
            return MiddlewareResult(success=True, should_continue=True)

        content_guard = self._get_content_guard()
        if not content_guard:
            return MiddlewareResult(success=True, should_continue=True)

        # Check input messages for safety violations
        messages = context.messages
        violations = []

        for msg in messages:
            content = msg.get("content", "")
            if not content:
                continue

            # Check for PII
            if self._block_pii:
                pii_check = await self._check_pii(content)
                if pii_check:
                    violations.append(("pii", pii_check))

            # Check for harmful content
            if self._block_harmful:
                harmful_check = await self._check_harmful(content)
                if harmful_check:
                    violations.append(("harmful", harmful_check))

            # Check for policy violations
            if self._block_policy_violations:
                policy_check = await self._check_policy(content)
                if policy_check:
                    violations.append(("policy", policy_check))

        if violations:
            logger.warning(
                "content_guard_pre_model_violations",
                violations=[v[0] for v in violations],
            )
            return MiddlewareResult(
                success=False,
                should_continue=False,
                error=f"Content blocked: {', '.join(v[0] for v in violations)}",
            )

        return MiddlewareResult(success=True, should_continue=True)

    async def post_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Check output content after model inference.

        Args:
            context: ButlerMiddlewareContext with output messages

        Returns:
            MiddlewareResult with potential redaction/blocking
        """
        if not self.enabled:
            return MiddlewareResult(success=True, should_continue=True)

        content_guard = self._get_content_guard()
        if not content_guard:
            return MiddlewareResult(success=True, should_continue=True)

        # Check output messages for safety violations
        messages = context.messages
        modified_messages = None

        for msg in messages:
            content = msg.get("content", "")
            if not content:
                continue

            original_content = content

            # Redact PII if configured
            if self._redact_pii:
                content = await self._redact_pii_content(content)

            # Check for harmful content
            if self._block_harmful:
                harmful_check = await self._check_harmful(content)
                if harmful_check:
                    logger.warning(
                        "content_guard_post_model_harmful",
                        violation=harmful_check,
                    )
                    return MiddlewareResult(
                        success=False,
                        should_continue=False,
                        error=f"Harmful content detected: {harmful_check}",
                    )

            # Update message if content was modified
            if content != original_content:
                if modified_messages is None:
                    modified_messages = messages.copy()
                msg["content"] = content

        if modified_messages:
            return MiddlewareResult(
                success=True,
                should_continue=True,
                modified_input={"messages": modified_messages},
            )

        return MiddlewareResult(success=True, should_continue=True)

    async def _check_pii(self, content: str) -> str | None:
        """Check content for PII.

        Args:
            content: Content to check

        Returns:
            PII type if found, None otherwise
        """
        content_guard = self._get_content_guard()
        if content_guard and hasattr(content_guard, "detect_pii"):
            result = await content_guard.detect_pii(content)
            if result:
                return "pii_detected"
        return None

    async def _check_harmful(self, content: str) -> str | None:
        """Check content for harmful content.

        Args:
            content: Content to check

        Returns:
            Harmful category if found, None otherwise
        """
        content_guard = self._get_content_guard()
        if content_guard and hasattr(content_guard, "check_harmful"):
            result = await content_guard.check_harmful(content)
            if result:
                return result
        return None

    async def _check_policy(self, content: str) -> str | None:
        """Check content for policy violations.

        Args:
            content: Content to check

        Returns:
            Policy violation if found, None otherwise
        """
        content_guard = self._get_content_guard()
        if content_guard and hasattr(content_guard, "check_policy"):
            result = await content_guard.check_policy(content)
            if result:
                return result
        return None

    async def _redact_pii_content(self, content: str) -> str:
        """Redact PII from content.

        Args:
            content: Content to redact

        Returns:
            Redacted content
        """
        content_guard = self._get_content_guard()
        if content_guard and hasattr(content_guard, "redact_pii"):
            return await content_guard.redact_pii(content)
        return content
