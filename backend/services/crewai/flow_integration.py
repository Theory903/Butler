"""CrewAI Flow integration with Butler's Durable Workflow.

This module provides integration between CrewAI's event-driven Flows
and Butler's Durable Workflow Engine, maintaining Butler's security,
durability, and governance boundaries.
"""

from __future__ import annotations

import logging
from typing import Any

from .config import CrewAIConfig

logger = logging.getLogger(__name__)


class CrewAIFlowAdapter:
    """Adapter for integrating CrewAI Flows with Butler's Durable Workflow.

    This adapter maps CrewAI's decorator-based flow control to Butler's
    durable workflow nodes, enabling hybrid execution that combines:
    - CrewAI's event-driven @router and conditional logic
    - Butler's PostgreSQL checkpointing and compensation
    - Butler's approval gates and policy enforcement

    Integration Principles:
    - Use Butler for durable state (PostgreSQL checkpointing)
    - Use CrewAI for in-memory flow control and routing
    - All CrewAI operations pass through Butler's security guardrails
    - Maintain Butler's service boundaries and governance
    """

    def __init__(
        self,
        config: CrewAIConfig | None = None,
        content_guard: Any = None,
    ) -> None:
        """Initialize CrewAI Flow adapter.

        Args:
            config: CrewAI configuration.
            content_guard: Butler ContentGuard instance for safety checks.
        """
        self._config = config or CrewAIConfig()
        self._content_guard = content_guard

    async def create_flow_from_butler_workflow(
        self,
        workflow_definition: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> Any:
        """Create a CrewAI Flow from Butler workflow definition.

        Args:
            workflow_definition: Butler workflow definition with nodes and edges.
            context: Additional context for flow creation.

        Returns:
            CrewAI Flow instance or None if CrewAI is not installed.
        """
        try:
            from crewai import Flow

            # Map Butler workflow nodes to CrewAI Flow structure
            # Phase 2: Basic mapping of sequential nodes
            # Phase 3: Advanced mapping with conditional routing and parallel execution

            flow_tasks = self._map_workflow_nodes_to_tasks(workflow_definition)

            # Create CrewAI Flow
            flow = Flow(tasks=flow_tasks)

            logger.info(f"Created CrewAI Flow with {len(flow_tasks)} tasks")
            return flow

        except ImportError:
            logger.warning("CrewAI not installed - Flow integration disabled")
            return None
        except Exception as e:
            logger.exception(f"Failed to create CrewAI Flow: {e}")
            return None

    def _map_workflow_nodes_to_tasks(
        self, workflow_definition: dict[str, Any]
    ) -> list[Any]:
        """Map Butler workflow nodes to CrewAI Flow tasks.

        Args:
            workflow_definition: Butler workflow definition.

        Returns:
            List of CrewAI Flow tasks.
        """
        # Phase 2: Basic mapping - extract sequential tasks
        # Phase 3: Advanced mapping with conditional routing (@router decorator)

        nodes = workflow_definition.get("nodes", [])
        tasks = []

        for node in nodes:
            node_type = node.get("type")
            node_config = node.get("config", {})

            if node_type == "action":
                # Map Butler action nodes to CrewAI tasks
                task = self._create_action_task(node_config)
                if task:
                    tasks.append(task)
            elif node_type == "condition":
                # Map Butler condition nodes to CrewAI conditional logic
                # Phase 2: Simple conditions
                # Phase 3: Advanced with CrewAI's @router decorator
                pass
            elif node_type == "delay":
                # Map Butler delay nodes to CrewAI delays
                pass

        return tasks

    def _create_action_task(self, node_config: dict[str, Any]) -> Any:
        """Create a CrewAI action task from Butler action node config.

        Args:
            node_config: Butler action node configuration.

        Returns:
            CrewAI task or None.
        """
        try:
            from crewai import Task

            return Task(
                description=node_config.get("description", ""),
                expected_output=node_config.get("expected_output", ""),
            )
        except ImportError:
            return None

    async def execute_flow_with_butler_checkpointing(
        self,
        flow: Any,
        inputs: dict[str, Any],
        checkpoint_handler: Any = None,
    ) -> dict[str, Any]:
        """Execute CrewAI Flow with Butler checkpointing.

        Args:
            flow: CrewAI Flow instance.
            inputs: Input data for the flow.
            checkpoint_handler: Butler checkpoint handler for state persistence.

        Returns:
            Execution result with response and metadata.
        """
        try:
            # Apply security guardrails if enabled
            if self._content_guard:
                user_message = inputs.get("user_message", "")
                if user_message:
                    safety_check = await self._content_guard.check(user_message)
                    if not safety_check.get("safe", True):
                        logger.warning(
                            f"ContentGuard blocked unsafe flow input: {safety_check.get('reason')}"
                        )
                        return {
                            "response": "Input blocked by safety guardrails",
                            "metadata": {
                                "blocked_by_content_guard": True,
                                "reason": safety_check.get("reason"),
                            },
                        }

            # Execute CrewAI Flow
            result = flow.kickoff(inputs=inputs)

            # Extract response from result
            if hasattr(result, "raw"):
                response = result.raw
            elif hasattr(result, "result"):
                response = result.result
            else:
                response = str(result)

            # Apply Butler checkpointing if handler is available
            if checkpoint_handler:
                try:
                    await checkpoint_handler.save_checkpoint(
                        flow_state={"inputs": inputs, "outputs": response},
                        metadata={"flow_execution": True},
                    )
                    logger.info("Saved Butler checkpoint for CrewAI Flow execution")
                except Exception as e:
                    logger.warning(f"Failed to save Butler checkpoint: {e}")

            return {
                "response": response,
                "metadata": {
                    "flow_execution": True,
                    "checkpoint_saved": checkpoint_handler is not None,
                },
            }

        except Exception as e:
            logger.exception(f"CrewAI Flow execution failed: {e}")
            return {
                "response": f"CrewAI Flow execution failed: {e}",
                "metadata": {"error": str(e)},
            }


class ButlerCheckpointHandler:
    """Handler for Butler checkpointing in CrewAI Flow execution.

    This class provides an interface for saving and loading checkpoints
    during CrewAI Flow execution, enabling Butler's durable execution model.
    """

    def __init__(self, db_session: Any = None) -> None:
        """Initialize Butler checkpoint handler.

        Args:
            db_session: Butler database session for checkpoint storage.
        """
        self._db_session = db_session

    async def save_checkpoint(
        self, flow_state: dict[str, Any], metadata: dict[str, Any] | None = None
    ) -> str:
        """Save a checkpoint for CrewAI Flow execution.

        Args:
            flow_state: Current flow state to checkpoint.
            metadata: Additional metadata for the checkpoint.

        Returns:
            Checkpoint ID.
        """
        # Phase 2: Basic checkpointing placeholder
        # Phase 3: Full integration with Butler's PostgreSQL checkpointing
        checkpoint_id = f"crewai_checkpoint_{hash(str(flow_state))}"
        logger.info(f"Saved checkpoint: {checkpoint_id}")
        return checkpoint_id

    async def load_checkpoint(self, checkpoint_id: str) -> dict[str, Any] | None:
        """Load a checkpoint for CrewAI Flow execution.

        Args:
            checkpoint_id: Checkpoint ID to load.

        Returns:
            Checkpoint state or None if not found.
        """
        # Phase 2: Basic checkpoint loading placeholder
        # Phase 3: Full integration with Butler's PostgreSQL checkpointing
        logger.info(f"Loaded checkpoint: {checkpoint_id}")
        return None
