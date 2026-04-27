"""Butler Time Travel - State history and rollback via checkpointing.

Leverages LangGraph's checkpointing system for state inspection and rollback.
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from langchain_core.runnables import RunnableConfig

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CheckpointState:
    """A snapshot of agent state at a specific checkpoint."""

    checkpoint_id: str
    thread_id: str
    timestamp: datetime
    state: dict[str, Any]
    parent_checkpoint_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ButlerTimeTravel:
    """Time Travel service for LangGraph agents.

    This service:
    - Queries checkpoint history for a thread
    - Allows rollback to previous states
    - Supports branching from historical states
    - Provides state inspection capabilities
    """

    def __init__(self, compiled_graph: Any, checkpointer: Any):
        """Initialize the Time Travel service.

        Args:
            compiled_graph: The compiled LangGraph StateGraph
            checkpointer: The LangGraph checkpointer (PostgresSaver or MemorySaver)
        """
        self._compiled_graph = compiled_graph
        self._checkpointer = checkpointer

    async def get_checkpoint_history(
        self,
        thread_id: str,
        limit: int = 10,
        before: str | None = None,
    ) -> list[CheckpointState]:
        """Get checkpoint history for a thread.

        Args:
            thread_id: The thread identifier (typically session_id)
            limit: Maximum number of checkpoints to return
            before: Optional checkpoint ID to get history before

        Returns:
            List of checkpoint states in reverse chronological order
        """
        history = []

        try:
            # Use checkpointer's asearch method to get checkpoints
            config = RunnableConfig(
                configurable={"thread_id": thread_id},
            )

            async for checkpoint in self._checkpointer.asearch(config, limit=limit, before=before):
                checkpoint_state = CheckpointState(
                    checkpoint_id=checkpoint.get("config", {}).get("checkpoint_ns", ""),
                    thread_id=thread_id,
                    timestamp=datetime.fromtimestamp(
                        checkpoint.get("checkpoint", {}).get("step", 0) or 0,
                        tz=UTC,
                    ),
                    state=checkpoint.get("checkpoint", {}),
                    parent_checkpoint_id=checkpoint.get("checkpoint", {}).get("parent_checkpoint"),
                    metadata=checkpoint.get("metadata", {}),
                )
                history.append(checkpoint_state)

        except Exception as exc:
            logger.warning("checkpoint_history_fetch_failed", error=str(exc))

        return history

    async def get_checkpoint(self, thread_id: str, checkpoint_id: str) -> CheckpointState | None:
        """Get a specific checkpoint.

        Args:
            thread_id: The thread identifier
            checkpoint_id: The checkpoint identifier

        Returns:
            The checkpoint state or None if not found
        """
        try:
            config = RunnableConfig(
                configurable={"thread_id": thread_id, "checkpoint_ns": checkpoint_id},
            )
            checkpoint = await self._checkpointer.aget(config)

            if not checkpoint:
                return None

            return CheckpointState(
                checkpoint_id=checkpoint_id,
                thread_id=thread_id,
                timestamp=datetime.fromtimestamp(
                    checkpoint.get("step", 0) or 0,
                    tz=UTC,
                ),
                state=checkpoint,
                parent_checkpoint_id=checkpoint.get("parent_checkpoint"),
                metadata={},
            )
        except Exception as exc:
            logger.warning("checkpoint_fetch_failed", error=str(exc))
            return None

    async def rollback_to_checkpoint(
        self,
        thread_id: str,
        checkpoint_id: str,
    ) -> dict[str, Any] | None:
        """Roll back the agent to a previous checkpoint.

        Args:
            thread_id: The thread identifier
            checkpoint_id: The checkpoint to roll back to

        Returns:
            The state at the checkpoint, or None if rollback failed
        """
        checkpoint_state = await self.get_checkpoint(thread_id, checkpoint_id)
        if not checkpoint_state:
            logger.warning(
                "rollback_failed_checkpoint_not_found",
                checkpoint_id=checkpoint_id,
            )
            return None

        logger.info(
            "rollback_to_checkpoint",
            thread_id=thread_id,
            checkpoint_id=checkpoint_id,
        )

        return checkpoint_state.state

    async def branch_from_checkpoint(
        self,
        thread_id: str,
        checkpoint_id: str,
        new_thread_id: str | None = None,
    ) -> str:
        """Create a new branch from a historical checkpoint.

        Args:
            thread_id: The source thread identifier
            checkpoint_id: The checkpoint to branch from
            new_thread_id: Optional new thread ID (auto-generated if None)

        Returns:
            The new thread ID
        """
        if not new_thread_id:
            import uuid

            new_thread_id = f"{thread_id}_branch_{uuid.uuid4().hex[:8]}"

        checkpoint_state = await self.get_checkpoint(thread_id, checkpoint_id)
        if not checkpoint_state:
            raise ValueError(f"Checkpoint {checkpoint_id} not found")

        # Write the checkpoint state to the new thread
        config = RunnableConfig(
            configurable={"thread_id": new_thread_id},
        )
        await self._checkpointer.aput(config, checkpoint_state.state)

        logger.info(
            "branch_created_from_checkpoint",
            source_thread=thread_id,
            new_thread=new_thread_id,
            checkpoint_id=checkpoint_id,
        )

        return new_thread_id

    async def get_state_diff(
        self,
        thread_id: str,
        checkpoint_id_1: str,
        checkpoint_id_2: str,
    ) -> dict[str, Any]:
        """Get the difference between two checkpoints.

        Args:
            thread_id: The thread identifier
            checkpoint_id_1: First checkpoint ID
            checkpoint_id_2: Second checkpoint ID

        Returns:
            Dictionary containing the diff between the two states
        """
        state1 = await self.get_checkpoint(thread_id, checkpoint_id_1)
        state2 = await self.get_checkpoint(thread_id, checkpoint_id_2)

        if not state1 or not state2:
            return {"error": "One or both checkpoints not found"}

        diff = {
            "checkpoint_1": checkpoint_id_1,
            "checkpoint_2": checkpoint_id_2,
            "timestamp_delta": (state2.timestamp - state1.timestamp).total_seconds(),
            "state_changes": self._compute_state_diff(state1.state, state2.state),
        }

        return diff

    def _compute_state_diff(self, state1: dict[str, Any], state2: dict[str, Any]) -> dict[str, Any]:
        """Compute the difference between two state dictionaries."""
        changes = {}

        all_keys = set(state1.keys()) | set(state2.keys())

        for key in all_keys:
            val1 = state1.get(key)
            val2 = state2.get(key)

            if val1 != val2:
                changes[key] = {"old": val1, "new": val2}

        return changes

    async def get_execution_timeline(
        self,
        thread_id: str,
    ) -> list[dict[str, Any]]:
        """Get the full execution timeline for a thread.

        Args:
            thread_id: The thread identifier

        Returns:
            List of timeline events with timestamps and state changes
        """
        checkpoints = await self.get_checkpoint_history(thread_id, limit=100)
        timeline = []

        for i, checkpoint in enumerate(checkpoints):
            event = {
                "sequence": i,
                "checkpoint_id": checkpoint.checkpoint_id,
                "timestamp": checkpoint.timestamp.isoformat(),
                "state_summary": {
                    "messages_count": len(checkpoint.state.get("messages", [])),
                    "has_tool_context": checkpoint.state.get("tool_context") is not None,
                },
            }
            timeline.append(event)

        return timeline

    async def replay_from_checkpoint(
        self,
        thread_id: str,
        checkpoint_id: str,
        steps: int = 1,
    ) -> AsyncIterator[dict[str, Any]]:
        """Replay execution from a checkpoint.

        Args:
            thread_id: The thread identifier
            checkpoint_id: The checkpoint to start from
            steps: Number of steps to replay

        Yields:
            State snapshots at each step
        """
        state = await self.rollback_to_checkpoint(thread_id, checkpoint_id)
        if not state:
            return

        for i in range(steps):
            # This would require re-invoking the graph with the state
            # For now, this is a placeholder for the replay logic
            yield {
                "step": i,
                "state": state,
                "message": f"Replay step {i + 1}",
            }

    async def delete_thread_history(self, thread_id: str) -> bool:
        """Delete all checkpoint history for a thread.

        Args:
            thread_id: The thread identifier

        Returns:
            True if deletion succeeded, False otherwise
        """
        try:
            config = RunnableConfig(
                configurable={"thread_id": thread_id},
            )
            await self._checkpointer.adelete(config)

            logger.info("thread_history_deleted", thread_id=thread_id)
            return True
        except Exception as exc:
            logger.warning("thread_history_deletion_failed", error=str(exc))
            return False
