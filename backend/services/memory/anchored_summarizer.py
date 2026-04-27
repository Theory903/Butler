from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from domain.ml.contracts import (
    IReasoningRuntime,
    ReasoningRequest,
    ReasoningTier,
    ResponseFormat,
)

if TYPE_CHECKING:
    from services.memory.consent_manager import ConsentManager

import structlog

logger = structlog.get_logger(__name__)

ANCHORED_SUMMARY_SCHEMA = """## Session Intent
[Short description of what the user is trying to achieve]

## Decisions Made
- [Decision 1]
- [Decision 2]

## Artifact Trail (Files Modified)
- [file1]: [brief change description]

## Current State
- [Actionable status]

## Next Steps
1. [Step 1]
2. [Step 2]
"""


class AnchoredSummarizer:
    """Butler's anchored context-compression engine.

    Purpose:
    - maintain a stable session anchor across long conversations
    - preserve technical precision such as file paths, function names, and decisions
    - reduce context drift during long-running orchestration flows
    """

    def __init__(
        self,
        ml_runtime: IReasoningRuntime,
        consent_manager: ConsentManager | None = None,
        *,
        max_history_chars: int = 16_000,
        max_tokens: int = 1_024,
    ) -> None:
        if max_history_chars <= 0:
            raise ValueError("max_history_chars must be greater than 0")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be greater than 0")

        self._ml = ml_runtime
        self._consent = consent_manager
        self._max_history_chars = max_history_chars
        self._max_tokens = max_tokens

    async def generate_initial_summary(
        self, history: list[dict[str, Any]], account_id: str | None = None
    ) -> str:
        """Create the first anchored summary from a history chunk.

        Enhanced with:
        - Progressive compression for long histories
        - Better prompt engineering for technical precision
        - Summary quality validation
        """
        # Progressive compression for very long histories
        if len(history) > 100:
            # First pass: compress recent history
            recent_history = history[-50:]
            summary = await self._generate_summary_with_validation(recent_history, account_id)

            # If summary is too short, try with more history
            if len(summary) < 200:
                return await self._generate_summary_with_validation(history[-75:], account_id)
            return summary
        return await self._generate_summary_with_validation(history, account_id)

    async def _generate_summary_with_validation(
        self, history: list[dict[str, Any]], account_id: str | None = None
    ) -> str:
        """Generate summary with quality validation."""
        history_text = await self._format_history(history, account_id)

        prompt = (
            "You are Butler's Context Engineering Engine.\n"
            "Summarize the following conversation history into an ANCHORED SUMMARY.\n"
            "This summary will be used as persistent memory for a long-running AI session.\n\n"
            "CRITICAL RULES:\n"
            "1. Use the EXACT Markdown structure provided below.\n"
            "2. Be technically precise and preserve file paths, function names, APIs, and specific user intents.\n"
            "3. If no decisions were made yet, write 'No decisions made yet' in that section.\n"
            "4. If no files were modified, write 'No files modified yet'.\n"
            "5. Do not add extra sections.\n"
            "6. Keep the summary compact but loss-aware.\n"
            "7. Preserve all technical details, variable names, and specific values.\n\n"
            f"CONVERSATION HISTORY:\n{history_text}\n\n"
            f"OUTPUT STRUCTURE:\n{ANCHORED_SUMMARY_SCHEMA}"
        )

        summary = await self._run_summarization(prompt)
        if summary and self._validate_summary_quality(summary):
            return summary

        return self._fallback_initial_summary(history)

    async def merge_summary(
        self,
        existing_summary: str,
        new_history: list[dict[str, Any]],
        account_id: str | None = None,
    ) -> str:
        """Merge new turns into an existing anchored summary."""
        history_text = await self._format_history(new_history, account_id)
        normalized_existing = (existing_summary or "").strip()

        if not normalized_existing:
            return await self.generate_initial_summary(new_history)

        prompt = (
            "You are Butler's Context Engineering Engine.\n"
            "Update the EXISTING ANCHORED SUMMARY with information from the NEW CONVERSATION TURNS.\n\n"
            "CRITICAL RULES:\n"
            "1. MAINTAIN the existing Markdown structure exactly.\n"
            "2. MERGE new information into the corresponding sections.\n"
            "3. DO NOT LOSE previous file paths, technical decisions, or constraints unless explicitly reversed.\n"
            "4. Update 'Current State' and 'Next Steps' based on the latest turns.\n"
            "5. Preserve still-relevant information from the old summary.\n"
            "6. Do not add extra sections.\n\n"
            f"EXISTING SUMMARY:\n{normalized_existing}\n\n"
            f"NEW CONVERSATION TURNS:\n{history_text}\n\n"
            f"OUTPUT STRUCTURE:\n{ANCHORED_SUMMARY_SCHEMA}"
        )

        summary = await self._run_summarization(prompt)
        if summary:
            return summary

        return self._fallback_merged_summary(normalized_existing, new_history)

    async def _run_summarization(self, prompt: str) -> str:
        """Call the reasoning runtime for anchored summarization."""
        try:
            request = ReasoningRequest(
                system_prompt=(
                    "You are Butler's Context Compression Engine.\n"
                    "You specialize in technical summary maintenance.\n"
                    "Return only the anchored markdown summary.\n"
                    "Do not include commentary before or after the summary."
                ),
                prompt=prompt,
                temperature=0.1,
                max_tokens=self._max_tokens,
                preferred_tier=ReasoningTier.T1,
                response_format=ResponseFormat.MARKDOWN,
                metadata={"purpose": "context_compression"},
            )
            response = await self._ml.generate(
                request,
                tenant_id="default",  # P0: Summarizer uses default tenant_id
                preferred_tier=ReasoningTier.T1,
            )
            return (response.content or "").strip()
        except Exception:
            logger.exception("anchored_summarization_failed")
            return ""

    async def _format_history(
        self, history: list[dict[str, Any]], account_id: str | None = None
    ) -> str:
        """Format a list of chat turns into a stable compact transcript."""
        if not history:
            return "[system]: No conversation history available."

        lines: list[str] = []
        total_chars = 0

        for turn in reversed(history):
            role = str(turn.get("role", "unknown")).strip() or "unknown"
            content = str(turn.get("content", "")).strip()

            if not content:
                continue

            normalized_content = self._normalize_text(content)
            line = f"[{role}]: {normalized_content}"

            projected = total_chars + len(line) + 1
            if projected > self._max_history_chars and lines:
                break

            lines.append(line)
            total_chars = projected

        lines.reverse()

        if not lines:
            return "[system]: No usable conversation history available."

        formatted = "\n".join(lines)

        if self._consent is not None and account_id:
            try:
                acc_uuid = uuid.UUID(account_id)
                formatted = await self._consent.scrub_text(acc_uuid, formatted)
            except Exception:
                logger.warning("summarizer_scrub_failed", account_id=account_id)

        return formatted

    def _normalize_text(self, text: str) -> str:
        """Normalize conversation text without destroying technical content."""
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = "\n".join(line.rstrip() for line in normalized.splitlines())
        normalized = normalized.strip()

        if len(normalized) > 4_000:
            # Truncate with ellipsis for very long content
            normalized = normalized[:3950] + "\n\n[...content truncated for brevity...]"

        return normalized

    def _validate_summary_quality(self, summary: str) -> bool:
        """Validate that the summary meets quality standards.

        Checks:
        - Contains required sections
        - Minimum length threshold
        - Contains technical content indicators
        """
        if not summary or len(summary) < 100:
            return False

        required_sections = ["Session Intent", "Decisions Made", "Current State"]
        for section in required_sections:
            if section not in summary:
                return False

        # Check for technical content indicators
        technical_indicators = ["file", "function", "api", "path", "decision"]
        return any(indicator.lower() in summary.lower() for indicator in technical_indicators)

    def _fallback_initial_summary(self, history: list[dict[str, Any]]) -> str:
        """Deterministic fallback when model summarization fails."""
        latest_user_intent = self._infer_latest_user_intent(history)

        return (
            "## Session Intent\n"
            f"{latest_user_intent}\n\n"
            "## Decisions Made\n"
            "- No decisions made yet\n\n"
            "## Artifact Trail (Files Modified)\n"
            "- No files modified yet\n\n"
            "## Current State\n"
            "- Anchored summary generation failed, fallback summary created\n\n"
            "## Next Steps\n"
            "1. Retry summarization\n"
            "2. Continue session with preserved recent context"
        )

    def _fallback_merged_summary(
        self,
        existing_summary: str,
        new_history: list[dict[str, Any]],
    ) -> str:
        """Conservative deterministic merge fallback."""
        latest_user_intent = self._infer_latest_user_intent(new_history)

        return (
            f"{existing_summary}\n\n"
            "<!-- merge_fallback_applied -->\n"
            "## Current State\n"
            "- Summary merge failed in model path, prior anchor preserved\n"
            f"- Latest inferred user intent: {latest_user_intent}\n\n"
            "## Next Steps\n"
            "1. Retry anchored merge\n"
            "2. Continue from preserved anchor and recent turns"
        )

    def _infer_latest_user_intent(self, history: list[dict[str, Any]]) -> str:
        """Best-effort extraction of the latest user goal."""
        for turn in reversed(history):
            role = str(turn.get("role", "")).strip().lower()
            content = str(turn.get("content", "")).strip()
            if role == "user" and content:
                return content[:300]
        return "User intent could not be inferred from available history."
