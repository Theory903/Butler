import logging
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class MeetingTelemetryStore:
    def __init__(self):
        self.active_sessions: dict[str, dict[str, Any]] = {}

    def start_session(self, session_id: str):
        self.active_sessions[session_id] = {
            "id": session_id,
            "transcripts": [],
            "start_time": "now",  # In a real impl, datetime.utcnow().isoformat()
        }
        logger.info(f"[MeetingTelemetry] Tracking started for session {session_id}")

    def append_transcript(self, session_id: str, text: str, role: str = "user"):
        if session_id in self.active_sessions:
            self.active_sessions[session_id]["transcripts"].append({"role": role, "text": text})

    async def end_session(self, session_id: str, orchestrator_svc: Any):
        if session_id not in self.active_sessions:
            return

        data = self.active_sessions[session_id]
        transcripts = data["transcripts"]

        if not transcripts:
            logger.info(f"[MeetingTelemetry] Session {session_id} ended with no telemetry.")
            del self.active_sessions[session_id]
            return

        logger.info(
            f"[MeetingTelemetry] Session {session_id} ended. Constructing summary for {len(transcripts)} turns."
        )

        # Compile a synthetic format
        raw_text = "\n".join([f"{t['role'].capitalize()}: {t['text']}" for t in transcripts])

        # We would invoke the LLM or Hermes agent synchronously here logic
        # For Native Jarvis compatibility, generate legacySummary + detailedSummary
        try:
            summary_prompt = (
                "You are an AI meeting assistant. Summarize the following meeting transcript. "
                "Provide an Overview, Key points, and Action Items. Format as JSON mapping these keys.\n\n"
                f"Transcript:\n{raw_text}"
            )

            # Using OrchestratorService.intake directly
            from api.schemas.gateway import ChatRequest

            req = ChatRequest(message=summary_prompt, session_id=session_id + "_summary")

            summary_res = await orchestrator_svc.intake(req, account_id="jarvis_system")
            summary_text = summary_res.content

            logger.info(f"[MeetingTelemetry] Summary Generated:\n{summary_text[:150]}...")

            # Post this into Butler Memory Store
            # In a real prod environment we store it in Postgres.

        except Exception as e:
            logger.error(f"[MeetingTelemetry] Failed to summarize session {session_id}: {e}")

        del self.active_sessions[session_id]


# Singleton
meeting_telemetry = MeetingTelemetryStore()
