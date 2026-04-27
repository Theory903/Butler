"""Butler Agent Server endpoints and runtime infrastructure.

Provides FastAPI endpoints for agent execution and management.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import structlog

logger = structlog.get_logger(__name__)


def _tool_call_get(tc: Any, key: str, default: Any = None) -> Any:
    """Safely extract a value from a tool call, supporting both dict-style and object-style.

    Args:
        tc: Tool call (dict with keys like "name", "args", "id" or object with attributes)
        key: Key to extract (e.g., "name", "args", "id")
        default: Default value if key not found

    Returns:
        The extracted value or default
    """
    if isinstance(tc, dict):
        return tc.get(key, default)
    return getattr(tc, key, default)


# Request/Response Schemas


class AgentCreateRequest(BaseModel):
    """Request to create an agent."""

    tenant_id: str
    account_id: str
    session_id: str
    user_id: str | None = None
    preferred_model: str | None = None
    system_prompt: str | None = None
    enable_checkpointing: bool = False


class AgentExecuteRequest(BaseModel):
    """Request to execute an agent."""

    message: str
    session_id: str
    trace_id: str
    user_id: str | None = None


class AgentResponse(BaseModel):
    """Agent execution response."""

    response: str
    tool_calls: list[dict[str, Any]] = []
    trace_id: str
    session_id: str
    metadata: dict[str, Any] = {}


class AgentStatusResponse(BaseModel):
    """Agent status response."""

    session_id: str
    status: str
    message_count: int
    last_activity: str | None = None


class ButlerAgentServer:
    """Butler Agent Server for runtime infrastructure.

    This server:
    - Provides HTTP endpoints for agent execution
    - Manages agent lifecycle
    - Handles session management
    - Integrates with Butler's services
    """

    def __init__(
        self,
        runtime_manager: Any,
        tool_executor: Any | None = None,
        memory_service: Any | None = None,
        middleware_registry: Any | None = None,
    ):
        """Initialize the agent server.

        Args:
            runtime_manager: Butler's MLRuntimeManager
            tool_executor: Butler's ToolExecutor
            memory_service: Butler's MemoryService
            middleware_registry: Butler's MiddlewareRegistry
        """
        self._runtime_manager = runtime_manager
        self._tool_executor = tool_executor
        self._memory_service = memory_service
        self._middleware_registry = middleware_registry
        self._active_sessions: dict[str, Any] = {}

    def create_router(self) -> APIRouter:
        """Create the FastAPI router for agent endpoints.

        Returns:
            FastAPI router
        """
        router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

        @router.post("/create", response_model=dict[str, str])
        async def create_agent(request: AgentCreateRequest) -> dict[str, str]:
            """Create a new agent session."""
            try:
                from domain.tools.hermes_compiler import ButlerToolSpec
                from langchain.agent import create_agent

                # Get tool specs (mock for now)
                tool_specs: list[ButlerToolSpec] = []

                # Create the agent
                agent = create_agent(
                    runtime_manager=self._runtime_manager,
                    tool_specs=tool_specs,
                    tenant_id=request.tenant_id,
                    account_id=request.account_id,
                    session_id=request.session_id,
                    trace_id="",  # Will be set on execution
                    tool_executor=self._tool_executor,
                    user_id=request.user_id,
                    preferred_model=request.preferred_model,
                    system_prompt=request.system_prompt,
                    checkpoint_config={"connection_string": ""}
                    if request.enable_checkpointing
                    else None,
                    middleware_registry=self._middleware_registry,
                    memory_service=self._memory_service,
                )

                self._active_sessions[request.session_id] = {
                    "agent": agent,
                    "account_id": request.account_id,
                    "tenant_id": request.tenant_id,
                    "created_at": None,
                }

                logger.info("agent_session_created", session_id=request.session_id)
                return {"session_id": request.session_id, "status": "created"}

            except Exception as exc:
                logger.exception("agent_creation_failed")
                raise HTTPException(status_code=500, detail=str(exc))

        @router.post("/execute", response_model=AgentResponse)
        async def execute_agent(request: AgentExecuteRequest) -> AgentResponse:
            """Execute an agent with a message."""
            try:
                session = self._active_sessions.get(request.session_id)
                if not session:
                    raise HTTPException(status_code=404, detail="Session not found")

                agent = session["agent"]

                # Execute the agent
                from langchain_core.messages import HumanMessage

                messages = [HumanMessage(content=request.message)]
                state = {"messages": messages}

                result = await agent.ainvoke(state)

                # Extract response
                response_text = ""
                tool_calls = []

                if result.get("messages"):
                    last_message = result["messages"][-1]
                    response_text = getattr(last_message, "content", str(last_message))

                    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                        tool_calls = [
                            {"name": _tool_call_get(tc, "name"), "args": _tool_call_get(tc, "args")}
                            for tc in last_message.tool_calls
                        ]

                return AgentResponse(
                    response=response_text,
                    tool_calls=tool_calls,
                    trace_id=request.trace_id,
                    session_id=request.session_id,
                )

            except HTTPException:
                raise
            except Exception as exc:
                logger.exception("agent_execution_failed")
                raise HTTPException(status_code=500, detail=str(exc))

        @router.get("/status/{session_id}", response_model=AgentStatusResponse)
        async def get_agent_status(session_id: str) -> AgentStatusResponse:
            """Get agent session status."""
            session = self._active_sessions.get(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            return AgentStatusResponse(
                session_id=session_id,
                status="active",
                message_count=0,
            )

        @router.delete("/{session_id}")
        async def delete_agent(session_id: str) -> dict[str, str]:
            """Delete an agent session."""
            if session_id in self._active_sessions:
                del self._active_sessions[session_id]
                logger.info("agent_session_deleted", session_id=session_id)
                return {"session_id": session_id, "status": "deleted"}

            raise HTTPException(status_code=404, detail="Session not found")

        @router.get("/sessions")
        async def list_sessions() -> dict[str, list[str]]:
            """List all active sessions."""
            return {"sessions": list(self._active_sessions.keys())}

        return router

    async def execute_agent_background(
        self,
        session_id: str,
        message: str,
        trace_id: str,
    ) -> dict[str, Any]:
        """Execute an agent in the background.

        Args:
            session_id: Session ID
            message: User message
            trace_id: Trace ID

        Returns:
            Execution result
        """
        session = self._active_sessions.get(session_id)
        if not session:
            raise ValueError("Session not found")

        agent = session["agent"]

        from langchain_core.messages import HumanMessage

        messages = [HumanMessage(content=message)]
        state = {"messages": messages}

        result = await agent.ainvoke(state)

        return {
            "session_id": session_id,
            "trace_id": trace_id,
            "result": result,
        }

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get a session by ID.

        Args:
            session_id: Session ID

        Returns:
            Session data or None
        """
        return self._active_sessions.get(session_id)

    def get_all_sessions(self) -> dict[str, dict[str, Any]]:
        """Get all sessions.

        Returns:
            Dictionary of session data
        """
        return self._active_sessions.copy()


class ButlerAgentRuntime:
    """Runtime infrastructure for agent execution.

    This runtime:
    - Manages agent lifecycle
    - Provides execution context
    - Handles resource allocation
    - Supports scaling and load balancing
    """

    def __init__(self, server: ButlerAgentServer):
        """Initialize the runtime.

        Args:
            server: The agent server
        """
        self._server = server
        self._running_agents: dict[str, Any] = {}
        self._resource_pool: dict[str, Any] = {}

    async def start_agent(
        self,
        session_id: str,
        config: dict[str, Any],
    ) -> str:
        """Start an agent.

        Args:
            session_id: Session ID
            config: Agent configuration

        Returns:
            Agent ID
        """
        import uuid

        agent_id = str(uuid.uuid4())

        self._running_agents[agent_id] = {
            "session_id": session_id,
            "config": config,
            "status": "running",
            "started_at": None,
        }

        logger.info("runtime_agent_started", agent_id=agent_id, session_id=session_id)
        return agent_id

    async def stop_agent(self, agent_id: str) -> bool:
        """Stop an agent.

        Args:
            agent_id: Agent ID

        Returns:
            True if stopped
        """
        if agent_id in self._running_agents:
            self._running_agents[agent_id]["status"] = "stopped"
            logger.info("runtime_agent_stopped", agent_id=agent_id)
            return True

        return False

    def get_agent_status(self, agent_id: str) -> dict[str, Any] | None:
        """Get agent status.

        Args:
            agent_id: Agent ID

        Returns:
            Agent status or None
        """
        return self._running_agents.get(agent_id)

    def get_all_agents(self) -> dict[str, dict[str, Any]]:
        """Get all running agents.

        Returns:
            Dictionary of agent data
        """
        return self._running_agents.copy()

    async def allocate_resources(self, agent_id: str, requirements: dict[str, Any]) -> bool:
        """Allocate resources for an agent.

        Args:
            agent_id: Agent ID
            requirements: Resource requirements

        Returns:
            True if allocated
        """
        self._resource_pool[agent_id] = requirements
        logger.info("runtime_resources_allocated", agent_id=agent_id)
        return True

    async def release_resources(self, agent_id: str) -> bool:
        """Release resources for an agent.

        Args:
            agent_id: Agent ID

        Returns:
            True if released
        """
        if agent_id in self._resource_pool:
            del self._resource_pool[agent_id]
            logger.info("runtime_resources_released", agent_id=agent_id)
            return True

        return False

    def get_resource_usage(self) -> dict[str, Any]:
        """Get resource usage statistics.

        Returns:
            Resource usage data
        """
        return {
            "active_agents": len(self._running_agents),
            "resource_pool_size": len(self._resource_pool),
            "total_resources_allocated": sum(
                r.get("memory_mb", 0) for r in self._resource_pool.values()
            ),
        }
