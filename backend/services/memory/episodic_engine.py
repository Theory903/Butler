import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.memory.contracts import IMemoryRecorder
from domain.memory.models import Episode
from domain.ml.contracts import IReasoningRuntime

if TYPE_CHECKING:
    from services.memory.consent_manager import ConsentManager

import structlog

logger = structlog.get_logger(__name__)


class EpisodicMemoryEngine:
    """Butler's Episodic Memory Engine — condenses sessions into goal-oriented summaries."""

    def __init__(
        self,
        db: AsyncSession,
        ml_runtime: IReasoningRuntime,
        memory_recorder: IMemoryRecorder,
        consent_manager: "ConsentManager | None" = None,
    ):
        self._db = db
        self._ml_runtime = ml_runtime
        self._memory_service = memory_recorder  # narrow IMemoryRecorder slice
        self._consent = consent_manager

    async def capture_episode(
        self, account_id: str, session_id: str, tenant_id: str | None = None
    ) -> Episode | None:
        """Summarize a completed session into an interaction Episode.

        Args:
            account_id: Account ID
            session_id: Session ID
            tenant_id: Tenant ID for multi-tenant isolation (Phase 3)
        """
        acc_id = UUID(account_id)
        tenant_uuid = UUID(tenant_id or account_id)

        # 1. Fetch full session history
        history = await self._memory_service.get_session_history(account_id, session_id)
        if not history:
            logger.warning(f"No history found for session {session_id}, skipping episode capture.")
            return None

        # 2. Build summarization prompt (apply PII scrubbing if consent manager present)
        history_text = "\n".join([f"{h.role}: {h.content}" for h in history])

        if self._consent is not None:
            try:
                history_text = await self._consent.scrub_text(acc_id, history_text)
            except Exception:
                logger.warning(
                    "episodic_scrub_failed",
                    extra={"account_id": account_id, "session_id": session_id},
                )
        prompt = f"""
Summarize the following conversation session into a goal-oriented Episode.

CONVERSATION:
{history_text}

Response format (JSON):
{{
  "goal": "What was the user trying to achieve?",
  "outcome": "completed | failed | abandoned",
  "major_events": ["list", "of", "key", "actions/turns"],
  "lessons": ["What did we learn about the user or their environment?"]
}}
"""

        try:
            inference_res = await self._ml_runtime.execute_inference(
                profile_name="cloud_fast_general",
                payload={
                    "system": "You are Butler's Episodic Memory Engine. Summarize interaction history.",
                    "prompt": prompt,
                    "response_format": "json",
                },
            )

            summary_data = json.loads(inference_res.get("generated_text", "{}"))

            # 3. Store the Episode
            episode = Episode(
                tenant_id=tenant_uuid,
                account_id=acc_id,
                session_id=session_id,
                goal=summary_data.get("goal"),
                outcome=summary_data.get("outcome", "unknown"),
                events=summary_data.get("major_events", []),
                lessons=summary_data.get("lessons", []),
                created_at=datetime.utcnow(),
            )

            self._db.add(episode)
            await self._db.commit()

            logger.info(f"Captured episode for session {session_id} (Outcome: {episode.outcome})")
            return episode

        except Exception as e:
            logger.error(f"Episodic summarization failed for session {session_id}: {e}")
            return None
