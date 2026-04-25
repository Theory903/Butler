import json
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class RealtimeEvent(BaseModel):
    """Typed event for real-time delivery."""

    event_type: str  # workflow.update, approval.request, response.chunk, presence.change
    payload: dict
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    durable: bool = True  # If true, persisted in Redis Streams for replay

    def to_dict(self):
        return {
            "type": self.event_type,
            "payload": json.dumps(self.payload),
            "timestamp": self.timestamp.isoformat(),
            "event_id": self.event_id,
        }


# Event factory helpers
class Events:
    @staticmethod
    def workflow_update(workflow_id: str, status: str, detail: str = None) -> RealtimeEvent:
        return RealtimeEvent(
            event_type="workflow.update",
            payload={"workflow_id": workflow_id, "status": status, "detail": detail},
        )

    @staticmethod
    def approval_request(approval_id: str, description: str) -> RealtimeEvent:
        return RealtimeEvent(
            event_type="approval.request",
            payload={"approval_id": approval_id, "description": description},
        )

    @staticmethod
    def response_chunk(content: str, final: bool = False) -> RealtimeEvent:
        return RealtimeEvent(
            event_type="response.chunk",
            payload={"content": content, "final": final},
            durable=False,  # Ephemeral — no replay needed
        )

    @staticmethod
    def presence_change(account_id: str, status: str) -> RealtimeEvent:
        return RealtimeEvent(
            event_type="presence.change",
            payload={"account_id": account_id, "status": status},
            durable=False,
        )
