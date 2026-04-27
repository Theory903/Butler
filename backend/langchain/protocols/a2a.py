"""Butler A2A (Agent-to-Agent) Protocol.

Phase C.2: Wrapper around services/orchestrator/subagent_runtime.py and blender.py.
Exposes inter-agent messaging via Butler's subagent runtime.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

import structlog

logger = structlog.get_logger(__name__)


class MessageType(str, Enum):
    """Types of agent messages."""

    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


class Priority(str, Enum):
    """Message priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AgentMessage:
    """A message between agents."""

    message_id: str = field(default_factory=lambda: str(uuid4()))
    sender_id: str = ""
    recipient_id: str = ""
    message_type: MessageType = MessageType.REQUEST
    priority: Priority = Priority.NORMAL
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: 0)
    reply_to: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentCapability:
    """An agent capability description."""

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class ButlerA2AClient:
    """Butler's A2A client wrapping subagent_runtime.

    This client:
    - Wraps services/orchestrator/subagent_runtime.py for subagent execution
    - Wraps services/orchestrator/blender.py for federated intelligence
    - Exposes LangChain-compatible agent communication
    """

    def __init__(
        self,
        agent_id: str,
        subagent_runtime: Any | None = None,
        blender: Any | None = None,
    ):
        """Initialize the A2A client.

        Args:
            agent_id: This agent's ID
            subagent_runtime: Butler's SubagentRuntime service
            blender: Butler's Blender service
        """
        self._agent_id = agent_id
        self._subagent_runtime = subagent_runtime
        self._blender = blender

    async def send_request(
        self,
        recipient_id: str,
        payload: dict[str, Any],
        priority: Priority = Priority.NORMAL,
        timeout: float = 30.0,
    ) -> Any:
        """Send a request to another agent via subagent runtime.

        Args:
            recipient_id: The recipient agent ID
            payload: Request payload
            priority: Message priority
            timeout: Timeout in seconds

        Returns:
            Response payload
        """
        if not self._subagent_runtime:
            raise RuntimeError("Subagent runtime not configured")

        # Map A2A priority to subagent trust level
        from domain.policy.capability_flags import TrustLevel

        trust_map = {
            Priority.LOW: TrustLevel.UNTRUSTED,
            Priority.NORMAL: TrustLevel.VERIFIED_USER,
            Priority.HIGH: TrustLevel.PEER_AGENT,
            Priority.CRITICAL: TrustLevel.INTERNAL,
        }
        trust_level = trust_map.get(priority, TrustLevel.VERIFIED_USER)

        # Create subagent profile
        from services.orchestrator.subagent_runtime import RuntimeClass, SubAgentProfile

        profile = SubAgentProfile(
            agent_id=f"sub:{recipient_id}",
            parent_agent_id=self._agent_id,
            session_id=payload.get("session_id", "default"),
            runtime_class=RuntimeClass.IN_PROCESS,
            trust_level=trust_level,
            memory_scope=payload.get("memory_scope", "session"),
        )

        # Execute via subagent runtime
        try:
            result = await self._subagent_runtime.execute(
                profile=profile,
                task=payload.get("task", ""),
                context=payload.get("context", {}),
            )
            return {"success": True, "result": result}
        except Exception as e:
            logger.exception("a2a_subagent_execution_failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def blend_intelligence(
        self,
        query: str,
        user_id: str,
        session_id: str,
        context: dict[str, Any] | None = None,
    ) -> Any:
        """Blend intelligence from multiple sources via ButlerBlender.

        Args:
            query: Query to process
            user_id: User ID
            session_id: Session ID
            context: Additional context

        Returns:
            Blended intelligence result
        """
        if not self._blender:
            raise RuntimeError("Blender not configured")

        from services.orchestrator.blender import BlenderSignal

        signal = BlenderSignal(
            user_id=user_id,
            session_id=session_id,
            query=query,
            context=context or {},
        )

        try:
            result = await self._blender.blend(signal)
            return {"success": True, "result": result}
        except Exception as e:
            logger.exception("a2a_blender_failed", error=str(e))
            return {"success": False, "error": str(e)}


class ButlerA2AServer:
    """Butler's A2A server wrapping subagent runtime registry.

    This server:
    - Manages subagent profiles via SubagentRuntime
    - Routes messages between agents
    - Handles capability discovery via Blender
    """

    def __init__(self, subagent_runtime: Any | None = None):
        """Initialize the A2A server.

        Args:
            subagent_runtime: Butler's SubagentRuntime service
        """
        self._subagent_runtime = subagent_runtime
        self._agents: dict[str, dict[str, Any]] = {}

    def register_agent(self, agent_id: str, agent_info: dict[str, Any]) -> None:
        """Register an agent.

        Args:
            agent_id: Agent ID
            agent_info: Agent information
        """
        self._agents[agent_id] = agent_info
        logger.info("a2a_agent_registered", agent_id=agent_id)

    def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent.

        Args:
            agent_id: Agent ID
        """
        if agent_id in self._agents:
            del self._agents[agent_id]
        logger.info("a2a_agent_unregistered", agent_id=agent_id)

    def discover_agents(self) -> list[str]:
        """Discover all registered agents.

        Returns:
            List of agent IDs
        """
        return list(self._agents.keys())

    async def route_message(self, message: AgentMessage) -> bool:
        """Route a message to its recipient.

        Args:
            message: The message to route

        Returns:
            True if routing succeeded
        """
        if message.recipient_id not in self._agents:
            logger.warning("a2a_recipient_not_found", recipient_id=message.recipient_id)
            return False

        # In production, this would deliver via subagent runtime
        logger.info(
            "a2a_message_routed", recipient_id=message.recipient_id, message_id=message.message_id
        )
        return True
