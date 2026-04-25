"""Butler LangGraph state definition.

Defines the state object that flows through the Butler agent graph.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ButlerGraphState:
    """State for Butler LangGraph workflow.

    This state flows through the graph nodes:
    intake → safety → context → plan → unified_agent_loop → tool_execute → approval_if_needed → memory_writeback → render
    """

    # Input
    account_id: str
    session_id: str
    user_message: str
    model: str

    # Context
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    memory_context: str | None = None
    system_message: str | None = None

    # Governance
    account_tier: str = "free"
    channel: str = "api"
    assurance_level: str = "AAL1"
    product_tier: str | None = None
    industry_profile: str | None = None

    # Agent loop state
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)

    # Execution metadata
    iterations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    duration_ms: int = 0

    # Output
    final_response: str | None = None
    stopped_reason: str = "completed"

    # Error state
    error: str | None = None

    # Memory writeback
    memories_to_store: list[dict[str, Any]] = field(default_factory=list)

    # Approval state
    pending_approval: dict[str, Any] | None = None
    approval_granted: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary."""
        return {
            "account_id": self.account_id,
            "session_id": self.session_id,
            "user_message": self.user_message,
            "model": self.model,
            "conversation_history": self.conversation_history,
            "memory_context": self.memory_context,
            "system_message": self.system_message,
            "account_tier": self.account_tier,
            "channel": self.channel,
            "assurance_level": self.assurance_level,
            "iterations": self.iterations,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
            "duration_ms": self.duration_ms,
            "final_response": self.final_response,
            "stopped_reason": self.stopped_reason,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ButlerGraphState":
        """Create state from dictionary."""
        return cls(
            account_id=data["account_id"],
            session_id=data["session_id"],
            user_message=data["user_message"],
            model=data["model"],
            conversation_history=data.get("conversation_history", []),
            memory_context=data.get("memory_context"),
            system_message=data.get("system_message"),
            account_tier=data.get("account_tier", "free"),
            channel=data.get("channel", "api"),
            assurance_level=data.get("assurance_level", "AAL1"),
            product_tier=data.get("product_tier"),
            industry_profile=data.get("industry_profile"),
        )
