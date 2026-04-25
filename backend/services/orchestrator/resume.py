"""
Approval Resume Handler - Resumes LangGraph after human approval decision.
Native interrupt() + Command(resume=) pattern.
"""

from datetime import UTC, datetime, timedelta

from langgraph.types import Command
from pydantic import BaseModel

APPROVAL_TIMEOUT_MINUTES = 30


class ApprovalDecision(BaseModel):
    approval_id: str
    session_id: str
    decision: str
    reason: str | None = None


def check_approval_expired(checkpoint_created_at: datetime) -> bool:
    """Check if approval has expired."""
    return datetime.now(UTC) - checkpoint_created_at > timedelta(minutes=APPROVAL_TIMEOUT_MINUTES)


async def resume_approval(
    session_id: str,
    tenant_id: str,
    approval_id: str,
    decision: dict,
) -> Command:
    """Resume graph with human approval decision."""
    return Command(
        resume={
            "approval_id": approval_id,
            "decision": decision.get("approved"),
            "reason": decision.get("reason"),
        }
    )


async def handle_approval_denied(
    session_id: str,
    approval_id: str,
    tool_name: str,
    reason: str | None = None,
) -> dict:
    """Handle case when approval is denied."""
    return {
        "status": "denied",
        "approval_id": approval_id,
        "tool_name": tool_name,
        "reason": reason or "User denied approval",
        "fallback_action": "return_error",
    }


def create_approval_url(approval_id: str, base_url: str = "http://localhost:3000") -> str:
    """Create approval URL for user."""
    return f"{base_url}/approve/{approval_id}"
