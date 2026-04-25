import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.meetings.models import Meeting, MeetingSummary, Transcription

logger = structlog.get_logger(__name__)


class MeetingService:
    """Manages meeting lifecycle, transcriptions, and summaries."""

    def __init__(self, db: AsyncSession, llm_runtime: Any):
        self._db = db
        self._llm = llm_runtime

    async def create_meeting(
        self, account_id: str, title: str, participants: list[str] = None
    ) -> Meeting:
        if participants is None:
            participants = []
        meeting = Meeting(
            account_id=uuid.UUID(account_id),
            title=title,
            participants=participants,
            start_time=datetime.now(UTC),
        )
        self._db.add(meeting)
        await self._db.flush()
        return meeting

    async def add_transcription_segment(
        self, meeting_id: str, speaker: str, text: str, timestamp: float
    ) -> None:
        """Append a transcription segment to the existing transcript."""
        # Note: In a real production system, we might buffer segments in Redis
        # for real-time UI before flushing to Postgres on meeting end.
        meeting_uuid = uuid.UUID(meeting_id)

        stmt = select(Transcription).where(Transcription.meeting_id == meeting_uuid)
        result = await self._db.execute(stmt)
        transcription = result.scalar_one_or_none()

        if not transcription:
            transcription = Transcription(meeting_id=meeting_uuid, content="", segments=[])
            self._db.add(transcription)

        segment = {"speaker": speaker, "text": text, "ts": timestamp}
        transcription.segments.append(segment)
        transcription.content += f"\n[{speaker}] {text}"

        await self._db.flush()

    async def finish_meeting(self, meeting_id: str) -> MeetingSummary:
        """Close the meeting and generate an AI summary."""
        meeting = await self._db.get(Meeting, uuid.UUID(meeting_id))
        if not meeting:
            raise ValueError(f"Meeting {meeting_id} not found")

        meeting.end_time = datetime.now(UTC)

        # 1. Fetch transcript
        stmt = select(Transcription).where(Transcription.meeting_id == meeting.id)
        result = await self._db.execute(stmt)
        transcription = result.scalar_one_or_none()

        if not transcription or not transcription.content:
            summary = MeetingSummary(
                meeting_id=meeting.id,
                summary_text="No audio data was recorded for this meeting.",
                action_items=[],
                key_decisions=[],
            )
            self._db.add(summary)
            await self._db.flush()
            return summary

        # 2. Invoke AI to generate summary
        # Simplified: In reality, we'd use self._llm.execute_inference()
        summary_text = await self._generate_ai_summary(transcription.content)

        summary = MeetingSummary(
            meeting_id=meeting.id,
            summary_text=summary_text,
            action_items=["Action item extracted from transcript..."],
            key_decisions=["Decision extracted from transcript..."],
        )
        self._db.add(summary)
        await self._db.flush()
        await self._db.commit()

        return summary

    async def _generate_ai_summary(self, transcript: str) -> str:
        """Internal helper to call LLM for summarization."""
        # Simulated LLM summary
        return f"Summary of the meeting based on transcript: {transcript[:100]}..."

    async def get_meeting_history(self, account_id: str) -> list[Meeting]:
        stmt = (
            select(Meeting)
            .where(Meeting.account_id == uuid.UUID(account_id))
            .order_by(Meeting.created_at.desc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
