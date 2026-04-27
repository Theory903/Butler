"""Butler Summarization Middleware.

Wraps AnchoredSummarizer to compress long conversation history
before model inference.
"""

import logging

from langchain.middleware.base import (
    ButlerBaseMiddleware,
    ButlerMiddlewareContext,
    MiddlewareResult,
)
from services.memory.anchored_summarizer import AnchoredSummarizer

import structlog

logger = structlog.get_logger(__name__)


class ButlerSummarizationMiddleware(ButlerBaseMiddleware):
    """Middleware for context compression using anchored summarization.

    Runs on PRE_MODEL hook to compress long conversation history.
    """

    def __init__(
        self,
        summarizer: AnchoredSummarizer | None = None,
        enabled: bool = True,
        max_history_chars: int = 16_000,
    ):
        super().__init__(enabled=enabled)
        self._summarizer = summarizer
        self._max_history_chars = max_history_chars

    async def pre_model(self, context: ButlerMiddlewareContext) -> MiddlewareResult:
        """Compress conversation history if it exceeds threshold."""
        if not context.messages:
            return MiddlewareResult(success=True, should_continue=True)

        # Calculate total chars in messages
        total_chars = sum(len(str(msg.get("content", ""))) for msg in context.messages)

        if total_chars <= self._max_history_chars:
            return MiddlewareResult(success=True, should_continue=True)

        if not self._summarizer:
            logger.warning("summarizer_not_configured")
            return MiddlewareResult(success=True, should_continue=True)

        try:
            # Generate anchored summary
            summary = await self._summarizer.generate_initial_summary(
                history=context.messages,
                account_id=context.account_id,
            )

            if summary:
                # Replace history with summary
                summary_msg = {"role": "system", "content": summary}
                # Keep last few messages for context
                recent_messages = context.messages[-5:] if len(context.messages) > 5 else []
                compressed_messages = [summary_msg] + recent_messages

                logger.info(
                    "history_compressed",
                    original_count=len(context.messages),
                    compressed_count=len(compressed_messages),
                    original_chars=total_chars,
                    compressed_chars=len(summary),
                )

                return MiddlewareResult(
                    success=True,
                    should_continue=True,
                    modified_input={"messages": compressed_messages},
                    metadata={
                        "summary": summary,
                        "original_message_count": len(context.messages),
                    },
                )
        except Exception as exc:
            logger.warning("summarization_failed", error=str(exc))

        return MiddlewareResult(success=True, should_continue=True)
