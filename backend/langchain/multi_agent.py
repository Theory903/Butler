"""Butler Multi-Agent and Deep Agents.

Phase D: Wrapper around services/orchestrator/subagent_runtime.py, blender.py.
Integrates with Butler's real multi-agent infrastructure for hierarchical reasoning.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from langchain.protocols.a2a import ButlerA2AClient, ButlerA2AServer, AgentMessage, MessageType, Priority
from langchain.protocols.acp import ButlerACPClient, ButlerACPServer, ACPMessage, ACPAction, ACPStatus

logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    """Agent roles in multi-agent systems."""

    ORCHESTRATOR = "orchestrator"
    SPECIALIST = "specialist"
    SUPERVISOR = "supervisor"
    WORKER = "worker"
    OBSERVER = "observer"


@dataclass
class AgentConfig:
    """Configuration for an agent."""

    agent_id: str
    role: AgentRole
    capabilities: list[str] = field(default_factory=list)
    parent_id: str | None = None
    children_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ButlerMultiAgentOrchestrator:
    """Orchestrates multiple agents using Butler's subagent_runtime and blender.

    This orchestrator:
    - Wraps services/orchestrator/subagent_runtime.py for subagent execution
    - Wraps services/orchestrator/blender.py for federated intelligence
    - Manages agent lifecycle via A2A protocol
    - Coordinates agent communication
    - Handles agent hierarchies
    """

    def __init__(
        self,
        a2a_server: ButlerA2AServer | None = None,
        subagent_runtime: Any | None = None,
        blender: Any | None = None,
    ):
        """Initialize the multi-agent orchestrator.

        Args:
            a2a_server: Optional A2A server for agent communication
            subagent_runtime: Butler's SubagentRuntime service
            blender: Butler's Blender service
        """
        self._a2a_server = a2a_server or ButlerA2AServer(subagent_runtime)
        self._subagent_runtime = subagent_runtime
        self._blender = blender
        self._agents: dict[str, AgentConfig] = {}
        self._task_queue: list[dict[str, Any]] = []
        self._active_tasks: dict[str, Any] = {}

    def register_agent(self, config: AgentConfig) -> None:
        """Register an agent with the orchestrator."""
        self._agents[config.agent_id] = config
        self._a2a_server.register_agent(config.agent_id, {"role": config.role.value})
        logger.info("multi_agent_registered", agent_id=config.agent_id, role=config.role)

    def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent."""
        if agent_id in self._agents:
            config = self._agents[agent_id]
            if config.parent_id and config.parent_id in self._agents:
                parent_config = self._agents[config.parent_id]
                parent_config.children_ids = [
                    cid for cid in parent_config.children_ids if cid != agent_id
                ]
            del self._agents[agent_id]
            self._a2a_server.unregister_agent(agent_id)
            logger.info("multi_agent_unregistered", agent_id=agent_id)

    def get_agent(self, agent_id: str) -> AgentConfig | None:
        """Get agent configuration."""
        return self._agents.get(agent_id)

    async def dispatch_task(
        self,
        task: dict[str, Any],
        target_agent_id: str | None = None,
        target_role: AgentRole | None = None,
    ) -> str:
        """Dispatch a task via subagent runtime."""
        import uuid
        task_id = str(uuid.uuid4())

        if self._subagent_runtime:
            # Use real subagent runtime for execution
            from services.orchestrator.subagent_runtime import SubAgentProfile, RuntimeClass
            from domain.policy.capability_flags import TrustLevel

            profile = SubAgentProfile(
                agent_id=f"sub:{target_agent_id or 'orchestrator'}",
                parent_agent_id="orchestrator",
                session_id=task.get("session_id", "default"),
                runtime_class=RuntimeClass.IN_PROCESS,
                trust_level=TrustLevel.VERIFIED_USER,
                memory_scope=task.get("memory_scope", "session"),
            )

            try:
                result = await self._subagent_runtime.execute(
                    profile=profile,
                    task=task.get("task", ""),
                    context=task.get("context", {}),
                )
                self._active_tasks[task_id] = {"result": result, "status": "completed"}
            except Exception as e:
                logger.exception("subagent_dispatch_failed", task_id=task_id)
                self._active_tasks[task_id] = {"error": str(e), "status": "failed"}
        else:
            # Fallback to A2A message routing
            target = target_agent_id or self._get_orchestrator_id()
            if target:
                message = AgentMessage(
                    recipient_id=target,
                    message_type=MessageType.REQUEST,
                    priority=Priority.NORMAL,
                    payload={"task_id": task_id, "task": task},
                )
                await self._a2a_server.route_message(message)
                self._active_tasks[task_id] = {"target": target, "status": "dispatched"}

        logger.info("multi_agent_task_dispatched", task_id=task_id)
        return task_id

    def _get_orchestrator_id(self) -> str | None:
        """Get orchestrator agent ID."""
        orchestrators = [c for c in self._agents.values() if c.role == AgentRole.ORCHESTRATOR]
        return orchestrators[0].agent_id if orchestrators else None

    async def blend_intelligence(
        self,
        query: str,
        user_id: str,
        session_id: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Blend intelligence via ButlerBlender."""
        if not self._blender:
            return {"error": "Blender not configured"}

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
            logger.exception("blend_intelligence_failed")
            return {"success": False, "error": str(e)}


class ButlerDeepAgent:
    """Deep agent with hierarchical reasoning using Butler's planner.

    This agent:
    - Wraps services/orchestrator/planner.py for task decomposition
    - Integrates with Butler's ML runtime for reflection
    - Supports multi-step reasoning
    - Maintains internal state
    """

    def __init__(
        self,
        agent_id: str,
        planner: Any | None = None,
        ml_runtime: Any | None = None,
        max_depth: int = 5,
        reflection_enabled: bool = True,
    ):
        """Initialize the deep agent.

        Args:
            agent_id: Agent ID
            planner: Butler's Planner service
            ml_runtime: Butler's MLRuntimeManager
            max_depth: Maximum reasoning depth
            reflection_enabled: Enable reflection step
        """
        self._agent_id = agent_id
        self._planner = planner
        self._ml_runtime = ml_runtime
        self._max_depth = max_depth
        self._reflection_enabled = reflection_enabled
        self._reasoning_chain: list[dict[str, Any]] = []
        self._current_depth = 0

    async def decompose(self, task: str, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Decompose task using Butler's planner.

        Args:
            task: Task to decompose
            context: Optional context

        Returns:
            List of sub-tasks
        """
        if self._planner:
            try:
                # Use real Butler planner
                from services.orchestrator.planner import Plan

                plan = await self._planner.plan(task, context or {})
                return [{"action": step.action, "params": step.params} for step in plan.steps]
            except Exception as e:
                logger.exception("planner_decompose_failed")
                return [{"action": "fallback", "params": {"task": task}}]
        else:
            # Fallback to simple decomposition
            parts = task.split(" and ")
            if len(parts) > 1:
                return [{"action": "subtask", "params": {"task": part}} for part in parts]
            return [{"action": "execute", "params": {"task": task}}]

    async def reflect(self, result: dict[str, Any]) -> dict[str, Any]:
        """Reflect on result using Butler's ML runtime.

        Args:
            result: Result to reflect on

        Returns:
            Reflection with confidence and suggestions
        """
        if self._ml_runtime and self._reflection_enabled:
            try:
                # Use real ML runtime for reflection
                reflection_prompt = f"Reflect on this result: {result.get('result', '')}"
                reflection = await self._ml_runtime.generate(
                    messages=[{"role": "user", "content": reflection_prompt}],
                    model="gpt-4",
                )
                return {
                    "confidence": 0.8,
                    "reflection": reflection,
                    "alternative_paths": [],
                    "suggestions": [],
                }
            except Exception as e:
                logger.exception("ml_reflection_failed")

        return {
            "confidence": 0.7,
            "alternative_paths": [],
            "potential_issues": [],
            "suggestions": [],
        }

    async def reason(
        self,
        query: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform deep reasoning."""
        self._reasoning_chain = []
        self._current_depth = 0

        # Decompose task
        sub_tasks = await self.decompose(query, context)

        result = {
            "query": query,
            "sub_tasks": sub_tasks,
            "reasoning_chain": [],
            "depth_reached": len(sub_tasks),
        }

        # Reflection step
        if self._reflection_enabled:
            reflection = await self.reflect(result)
            result["reflection"] = reflection

        logger.info("deep_agent_reasoning_completed", depth=len(sub_tasks))
        return result


class ButlerAgentHierarchy:
    """Agent hierarchy manager using Butler's subagent SubagentTree.

    This class:
    - Wraps subagent_runtime.py for hierarchy management
    - Manages parent-child relationships
    - Handles delegation up/down the hierarchy
    """

    def __init__(
        self,
        orchestrator: ButlerMultiAgentOrchestrator,
        subagent_runtime: Any | None = None,
    ):
        """Initialize the hierarchy manager.

        Args:
            orchestrator: The multi-agent orchestrator
            subagent_runtime: Butler's SubagentRuntime service
        """
        self._orchestrator = orchestrator
        self._subagent_runtime = subagent_runtime

    def add_child(self, parent_id: str, child_id: str) -> None:
        """Add a child to a parent agent."""
        parent = self._orchestrator.get_agent(parent_id)
        child = self._orchestrator.get_agent(child_id)

        if parent and child:
            child.parent_id = parent_id
            parent.children_ids.append(child_id)
            logger.info("agent_hierarchy_child_added", parent=parent_id, child=child_id)

    def get_children(self, agent_id: str) -> list[AgentConfig]:
        """Get children of an agent."""
        agent = self._orchestrator.get_agent(agent_id)
        if not agent:
            return []

        children = []
        for cid in agent.children_ids:
            child = self._orchestrator.get_agent(cid)
            if child:
                children.append(child)
        return children

    async def delegate_to_children(
        self,
        parent_id: str,
        task: dict[str, Any],
    ) -> dict[str, Any]:
        """Delegate task to children via subagent runtime."""
        children = self.get_children(parent_id)
        results = {}

        for child in children:
            if self._subagent_runtime:
                from services.orchestrator.subagent_runtime import SubAgentProfile, RuntimeClass
                from domain.policy.capability_flags import TrustLevel

                profile = SubAgentProfile(
                    agent_id=f"sub:{child.agent_id}",
                    parent_agent_id=parent_id,
                    session_id=task.get("session_id", "default"),
                    runtime_class=RuntimeClass.IN_PROCESS,
                    trust_level=TrustLevel.VERIFIED_USER,
                    memory_scope=task.get("memory_scope", "session"),
                )

                try:
                    result = await self._subagent_runtime.execute(
                        profile=profile,
                        task=task.get("task", ""),
                        context=task.get("context", {}),
                    )
                    results[child.agent_id] = result
                except Exception as e:
                    logger.exception("subagent_delegation_failed", child=child.agent_id)
                    results[child.agent_id] = {"error": str(e)}
            else:
                child_result = await self._orchestrator.dispatch_task(
                    task=task,
                    target_agent_id=child.agent_id,
                )
                results[child.agent_id] = child_result

        logger.info("agent_hierarchy_delegation_completed", parent=parent_id, children=len(children))
        return results

    def get_hierarchy_tree(self, root_id: str) -> dict[str, Any]:
        """Get hierarchy tree."""
        agent = self._orchestrator.get_agent(root_id)
        if not agent:
            return {}

        tree = {
            "agent_id": root_id,
            "role": agent.role.value,
            "children": [],
        }

        for child_id in agent.children_ids:
            child_tree = self.get_hierarchy_tree(child_id)
            if child_tree:
                tree["children"].append(child_tree)

        return tree
