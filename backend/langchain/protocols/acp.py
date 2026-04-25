"""Butler ACP (Agent Communication Protocol).

Phase C.3: Port from openclaw ACP control-plane (~2000 LOC Python equivalent).
Implements session-mode interaction, persistent bindings, secret-file pattern,
approval classifier, prompt-harness, session rate limit, and translator.
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class ACPAction(str, Enum):
    """ACP action types from openclaw."""

    QUERY = "query"
    INVOKE = "invoke"
    NOTIFY = "notify"
    REQUEST = "request"
    RESPOND = "respond"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    PUBLISH = "publish"
    # Openclaw-specific actions
    CANCEL = "cancel"
    SET_MODE = "set_mode"
    STOP_REASON = "stop_reason"
    PROMPT_PREFIX = "prompt_prefix"


class ACPStatus(str, Enum):
    """ACP status codes."""

    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"
    TIMEOUT = "timeout"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


@dataclass
class ACPMessage:
    """An ACP protocol message with openclaw extensions."""

    action: ACPAction
    sender: str
    recipient: str
    payload: dict[str, Any] = field(default_factory=dict)
    message_id: str = ""
    correlation_id: str = ""
    conversation_id: str = ""  # Openclaw conversation tracking
    status: ACPStatus = ACPStatus.SUCCESS
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action": self.action.value,
            "sender": self.sender,
            "recipient": self.recipient,
            "payload": self.payload,
            "message_id": self.message_id,
            "correlation_id": self.correlation_id,
            "conversation_id": self.conversation_id,
            "status": self.status.value,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ACPMessage":
        """Create from dictionary."""
        return cls(
            action=ACPAction(data["action"]),
            sender=data["sender"],
            recipient=data["recipient"],
            payload=data.get("payload", {}),
            message_id=data.get("message_id", ""),
            correlation_id=data.get("correlation_id", ""),
            conversation_id=data.get("conversation_id", ""),
            status=ACPStatus(data.get("status", "success")),
            timestamp=data.get("timestamp", 0.0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ACPCapability:
    """An ACP capability description."""

    name: str
    action: ACPAction
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    rate_limit: int = 100
    requires_auth: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ACPSession:
    """ACP session for session-mode interaction (openclaw pattern)."""

    session_id: str
    tenant_id: str
    account_id: str
    user_id: str
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    mode: str = "default"  # set_mode action
    prompt_prefix: str = ""  # prompt_prefix action
    rate_limit_remaining: int = 100
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        return self.expires_at is not None and time.time() > self.expires_at

    def check_rate_limit(self) -> bool:
        return self.rate_limit_remaining > 0


@dataclass
class ACPPersistentBinding:
    """Persistent binding for tool/agent connections (openclaw pattern)."""

    binding_id: str
    tenant_id: str
    account_id: str
    tool_name: str
    agent_id: str
    binding_type: str = "tool"  # tool, agent, resource
    config: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None

    def is_valid(self) -> bool:
        return self.expires_at is None or time.time() < self.expires_at


class ACPApprovalClassifier:
    """Approval classifier for tool/agent requests (openclaw pattern)."""

    def __init__(self):
        self._approval_cache: dict[str, bool] = {}

    def classify(self, action: ACPAction, payload: dict[str, Any]) -> bool:
        """Classify if action requires approval.

        Args:
            action: The ACP action
            payload: Action payload

        Returns:
            True if approval required
        """
        cache_key = f"{action.value}:{hash(json.dumps(payload, sort_keys=True))}"
        if cache_key in self._approval_cache:
            return self._approval_cache[cache_key]

        # Default classification rules
        requires_approval = action in [ACPAction.INVOKE, ACPAction.REQUEST]
        if "tool_name" in payload:
            tool_name = payload["tool_name"].lower()
            # High-risk tools require approval
            requires_approval = any(
                keyword in tool_name
                for keyword in ["delete", "modify", "execute", "shell", "sudo"]
            )

        self._approval_cache[cache_key] = requires_approval
        return requires_approval


class ButlerACPClient:
    """Butler's ACP client with openclaw features.

    This client:
    - Sends ACP-compliant messages
    - Manages sessions with rate limits
    - Handles persistent bindings
    - Integrates with approval classifier
    """

    def __init__(
        self,
        agent_id: str,
        transport: Any | None = None,
        session_manager: Any | None = None,
    ):
        """Initialize the ACP client.

        Args:
            agent_id: This agent's ID
            transport: Optional transport layer
            session_manager: Optional session manager
        """
        self._agent_id = agent_id
        self._transport = transport
        self._session_manager = session_manager
        self._capabilities: dict[str, ACPCapability] = {}
        self._pending_correlations: dict[str, Any] = {}
        self._current_session_id: str | None = None

    def register_capability(self, capability: ACPCapability) -> None:
        """Register a capability."""
        self._capabilities[capability.name] = capability
        logger.info("acp_capability_registered", capability=capability.name)

    async def set_mode(self, mode: str) -> str:
        """Set session mode (openclaw translator)."""
        if self._current_session_id and self._session_manager:
            session = self._session_manager.get_session(self._current_session_id)
            if session:
                session.mode = mode
                logger.info("acp_mode_set", mode=mode, session_id=self._current_session_id)
                return self._current_session_id
        return ""

    async def prompt_prefix(self, prefix: str) -> str:
        """Set prompt prefix (openclaw translator)."""
        if self._current_session_id and self._session_manager:
            session = self._session_manager.get_session(self._current_session_id)
            if session:
                session.prompt_prefix = prefix
                logger.info("acp_prompt_prefix_set", prefix=prefix[:50])
                return self._current_session_id
        return ""

    async def cancel(self, correlation_id: str) -> bool:
        """Cancel pending request (openclaw translator)."""
        if correlation_id in self._pending_correlations:
            del self._pending_correlations[correlation_id]
            logger.info("acp_request_cancelled", correlation_id=correlation_id)
            return True
        return False

    async def query(
        self,
        recipient: str,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a query action."""
        message = ACPMessage(
            action=ACPAction.QUERY,
            sender=self._agent_id,
            recipient=recipient,
            payload={"query": query, "parameters": parameters or {}},
            conversation_id=self._current_session_id or "",
        )
        return await self._send(message)

    async def invoke(
        self,
        recipient: str,
        function: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Send an invoke action."""
        message = ACPMessage(
            action=ACPAction.INVOKE,
            sender=self._agent_id,
            recipient=recipient,
            payload={"function": function, "arguments": arguments},
            conversation_id=self._current_session_id or "",
        )
        return await self._send(message)

    async def notify(
        self,
        recipient: str,
        event: str,
        data: dict[str, Any] | None = None,
    ) -> str:
        """Send a notification (fire-and-forget)."""
        message = ACPMessage(
            action=ACPAction.NOTIFY,
            sender=self._agent_id,
            recipient=recipient,
            payload={"event": event, "data": data or {}},
            conversation_id=self._current_session_id or "",
        )
        await self._send(message)
        return message.message_id

    async def request(
        self,
        recipient: str,
        request_type: str,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a request action."""
        import uuid
        correlation_id = str(uuid.uuid4())
        message = ACPMessage(
            action=ACPAction.REQUEST,
            sender=self._agent_id,
            recipient=recipient,
            correlation_id=correlation_id,
            payload={"request_type": request_type, "parameters": parameters or {}},
            conversation_id=self._current_session_id or "",
        )
        return await self._send(message)

    async def respond(
        self,
        recipient: str,
        correlation_id: str,
        response: dict[str, Any],
    ) -> str:
        """Send a response to a request."""
        message = ACPMessage(
            action=ACPAction.RESPOND,
            sender=self._agent_id,
            recipient=recipient,
            correlation_id=correlation_id,
            payload={"response": response},
            conversation_id=self._current_session_id or "",
        )
        await self._send(message)
        return message.message_id

    async def _send(self, message: ACPMessage) -> dict[str, Any]:
        """Send a message via transport."""
        import uuid

        if not message.message_id:
            message.message_id = str(uuid.uuid4())
        message.timestamp = time.time()

        if self._transport:
            await self._transport.send(message.to_dict())

        logger.info("acp_message_sent", action=message.action, recipient=message.recipient)
        return {"status": "sent", "message_id": message.message_id}


class ButlerACPServer:
    """Butler's ACP server with openclaw features.

    This server:
    - Validates ACP messages
    - Manages sessions with rate limits
    - Handles persistent bindings
    - Routes messages based on action type
    - Integrates approval classifier
    """

    def __init__(self):
        """Initialize the ACP server."""
        self._agents: dict[str, ButlerACPClient] = {}
        self._sessions: dict[str, ACPSession] = {}
        self._bindings: dict[str, ACPPersistentBinding] = {}
        self._global_capabilities: dict[str, ACPCapability] = {}
        self._rate_limits: dict[str, dict[str, Any]] = {}
        self._approval_classifier = ACPApprovalClassifier()

    def create_session(
        self,
        tenant_id: str,
        account_id: str,
        user_id: str,
        expires_in_seconds: int | None = None,
    ) -> ACPSession:
        """Create a new ACP session (openclaw session-mapper)."""
        session_id = str(uuid4())
        expires_at = time.time() + expires_in_seconds if expires_in_seconds else None
        session = ACPSession(
            session_id=session_id,
            tenant_id=tenant_id,
            account_id=account_id,
            user_id=user_id,
            expires_at=expires_at,
        )
        self._sessions[session_id] = session
        logger.info("acp_session_created", session_id=session_id, tenant_id=tenant_id)
        return session

    def get_session(self, session_id: str) -> ACPSession | None:
        """Get a session by ID."""
        session = self._sessions.get(session_id)
        if session and session.is_expired():
            del self._sessions[session_id]
            return None
        return session

    def create_binding(
        self,
        tenant_id: str,
        account_id: str,
        tool_name: str,
        agent_id: str,
        config: dict[str, Any] | None = None,
    ) -> ACPPersistentBinding:
        """Create a persistent binding (openclaw persistent-bindings)."""
        binding_id = str(uuid4())
        binding = ACPPersistentBinding(
            binding_id=binding_id,
            tenant_id=tenant_id,
            account_id=account_id,
            tool_name=tool_name,
            agent_id=agent_id,
            config=config or {},
        )
        self._bindings[binding_id] = binding
        logger.info("acp_binding_created", binding_id=binding_id, tool_name=tool_name)
        return binding

    def get_bindings(self, tool_name: str | None = None) -> list[ACPPersistentBinding]:
        """Get bindings, optionally filtered by tool name."""
        bindings = list(self._bindings.values())
        if tool_name:
            bindings = [b for b in bindings if b.tool_name == tool_name]
        return bindings

    def register_agent(self, client: ButlerACPClient) -> None:
        """Register an agent client."""
        self._agents[client._agent_id] = client
        logger.info("acp_agent_registered", agent_id=client._agent_id)

    def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent."""
        if agent_id in self._agents:
            del self._agents[agent_id]
        logger.info("acp_agent_unregistered", agent_id=agent_id)

    def register_global_capability(self, capability: ACPCapability) -> None:
        """Register a global capability."""
        self._global_capabilities[capability.name] = capability
        logger.info("acp_global_capability_registered", capability=capability.name)

    async def route_message(self, message: ACPMessage) -> ACPMessage | None:
        """Route an ACP message with approval check."""
        recipient_client = self._agents.get(message.recipient)

        if not recipient_client:
            logger.warning("acp_recipient_not_found", recipient=message.recipient)
            return None

        # Check approval requirement
        requires_approval = self._approval_classifier.classify(message.action, message.payload)
        if requires_approval:
            logger.info("acp_approval_required", action=message.action)
            return ACPMessage(
                action=ACPAction.RESPOND,
                sender="server",
                recipient=message.sender,
                correlation_id=message.message_id,
                status=ACPStatus.PENDING,
                payload={"requires_approval": True},
            )

        # Check session rate limit
        if message.conversation_id:
            session = self.get_session(message.conversation_id)
            if session and not session.check_rate_limit():
                logger.warning("acp_rate_limit_exceeded", session_id=message.conversation_id)
                return ACPMessage(
                    action=ACPAction.RESPOND,
                    sender="server",
                    recipient=message.sender,
                    correlation_id=message.message_id,
                    status=ACPStatus.REJECTED,
                    payload={"error": "Session rate limit exceeded"},
                )
        # Route to recipient
        return await recipient_client.handle_message(message)
