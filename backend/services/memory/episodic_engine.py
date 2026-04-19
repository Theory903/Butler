import logging
import json
from uuid import UUID
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from domain.memory.models import Episode
from domain.ml.contracts import IReasoningRuntime
from domain.memory.contracts import IMemoryRecorder

logger = logging.getLogger(__name__)

class EpisodicMemoryEngine:
    """Butler's Episodic Memory Engine — condenses sessions into goal-oriented summaries."""

    def __init__(
        self,
        db: AsyncSession,
        ml_runtime: IReasoningRuntime,
        memory_recorder: IMemoryRecorder,
    ):
        self._db = db
        self._ml_runtime = ml_runtime
        self._memory_service = memory_recorder   # narrow IMemoryRecorder slice

    async def capture_episode(self, account_id: str, session_id: str) -> Optional[Episode]:
        """Summarize a completed session into an interaction Episode."""
        acc_id = UUID(account_id)
        
        # 1. Fetch full session history
        history = await self._memory_service.get_session_history(account_id, session_id)
        if not history:
            logger.warning(f"No history found for session {session_id}, skipping episode capture.")
            return None

        # 2. Build summarization prompt
        history_text = "\n".join([f"{h.role}: {h.content}" for h in history])
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
                    "response_format": "json"
                }
            )
            
            summary_data = json.loads(inference_res.get("generated_text", "{}"))
            
            # 3. Store the Episode
            episode = Episode(
                account_id=acc_id,
                session_id=session_id,
                goal=summary_data.get("goal"),
                outcome=summary_data.get("outcome", "unknown"),
                events=summary_data.get("major_events", []),
                lessons=summary_data.get("lessons", []),
                created_at=datetime.utcnow()
            )
            
            self._db.add(episode)
            await self._db.commit()
            
            logger.info(f"Captured episode for session {session_id} (Outcome: {episode.outcome})")
            return episode
            
        except Exception as e:
            logger.error(f"Episodic summarization failed for session {session_id}: {e}")
            return None
