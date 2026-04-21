"""Anchored Summarizer Service — Context Compression (v3.1).

Implements the 'Anchored Iterative Summarization' pattern to maintain
a structured context anchor across long sessions. Structured summaries
prevent silent information drift (loss of file paths, decisions, etc).

Follows: docs/00-governance/context-compression.md (Workflow)
"""

from __future__ import annotations

import logging

from domain.ml.contracts import IReasoningRuntime

logger = logging.getLogger(__name__)

ANCHORED_SUMMARY_SCHEMA = """
## Session Intent
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
    """Butler's context compression anchor engine."""

    def __init__(self, ml_runtime: IReasoningRuntime):
        self._ml = ml_runtime

    async def generate_initial_summary(self, history: list[dict]) -> str:
        """Create the first anchored summary from a history chunk."""
        history_text = self._format_history(history)

        prompt = f"""
You are Butler's Context Engineering Engine. Summarize the following conversation history into an ANCHORED SUMMARY.
This summary will be used as the persistent memory for a long-running AI session.

CRITICAL RULES:
1. Use the EXACT Markdown structure provided below.
2. Be technically precise — preserve file paths, function names, and specific user intents.
3. If no decisions were made yet, return "No decisions made yet" in that section.
4. If no files were modified, return "No files modified yet".

CONVERSATION HISTORY:
{history_text}

OUTPUT STRUCTURE:
{ANCHORED_SUMMARY_SCHEMA}
"""
        return await self._run_summarization(prompt)

    async def merge_summary(self, existing_summary: str, new_history: list[dict]) -> str:
        """Merge new turns into an existing anchored summary."""
        history_text = self._format_history(new_history)

        prompt = f"""
You are Butler's Context Engineering Engine. Update the EXISTING ANCHORED SUMMARY with information from the NEW CONVERSATION TURNS.

CRITICAL RULES:
1. MAINTAIN the existing Markdown structure.
2. MERGE new information into the corresponding sections.
3. DO NOT LOSE previous file paths or critical technical decisions unless they were explicitly reversed.
4. Update 'Next Steps' and 'Current State' based on the latest turns.

EXISTING SUMMARY:
{existing_summary}

NEW CONVERSATION TURNS:
{history_text}

OUTPUT STRUCTURE:
{ANCHORED_SUMMARY_SCHEMA}
"""
        return await self._run_summarization(prompt)

    async def _run_summarization(self, prompt: str) -> str:
        from domain.ml.contracts import ReasoningRequest
        try:
            req = ReasoningRequest(
                system_prompt="You are Butler's Context Compression Engine. You specialize in technical summary maintenance.",
                prompt=prompt,
                temperature=0.1,
                max_tokens=1024,
                metadata={"purpose": "context_compression"}
            )
            res = await self._ml.generate(req, preferred_tier="T1")
            return res.content.strip()
        except Exception as e:
            logger.error(f"Anchored summarization failed: {e}")
            return ""

    def _format_history(self, history: list[dict]) -> str:
        lines = []
        for turn in history:
            role = turn.get("role", "unknown")
            content = turn.get("content", "")
            lines.append(f"[{role}]: {content}")
        return "\n".join(lines)
