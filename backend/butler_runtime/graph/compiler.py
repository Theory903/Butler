"""Butler LangGraph compiler.

Compiles the Butler agent workflow into a LangGraph that wires together
Butler's unified agent runtime with memory, tools, and governance.
"""

import logging
from typing import Any

from ..agent.loop import ButlerExecutionContext, ButlerUnifiedAgentLoop
from .state import ButlerGraphState

logger = logging.getLogger(__name__)


class ButlerGraphCompiler:
    """Compiles Butler's agent workflow into a LangGraph.

    The graph flow:
    intake → safety → context → plan → unified_agent_loop → tool_execute → approval_if_needed → memory_writeback → render
    """

    def __init__(
        self,
        agent_loop: ButlerUnifiedAgentLoop,
    ) -> None:
        """Initialize Butler graph compiler.

        Args:
            agent_loop: Butler unified agent loop
        """
        self._agent_loop = agent_loop

    def compile(self) -> Any:
        """Compile the Butler agent workflow into a LangGraph.

        Returns:
            Compiled LangGraph

        Note: This is a stub. Real implementation would use LangGraph's
        StateGraph to define nodes and edges.
        """
        # Stub implementation - in production, use LangGraph StateGraph
        # For now, return a placeholder
        return {
            "graph_type": "butler_agent",
            "nodes": [
                "intake",
                "safety",
                "context",
                "plan",
                "unified_agent_loop",
                "tool_execute",
                "approval_if_needed",
                "memory_writeback",
                "render",
            ],
            "edges": [
                ("intake", "safety"),
                ("safety", "context"),
                ("context", "plan"),
                ("plan", "unified_agent_loop"),
                ("unified_agent_loop", "tool_execute"),
                ("tool_execute", "approval_if_needed"),
                ("approval_if_needed", "memory_writeback"),
                ("memory_writeback", "render"),
            ],
        }

    async def run(
        self,
        state: ButlerGraphState,
    ) -> ButlerGraphState:
        """Run the Butler agent workflow.

        Args:
            state: Initial graph state

        Returns:
            Final graph state

        Note: This is a simplified implementation that directly calls
        the agent loop. Full LangGraph implementation would use
        the compiled graph with proper state transitions.
        """
        try:
            # Build execution context from state
            ctx = ButlerExecutionContext(
                account_id=state.account_id,
                session_id=state.session_id,
                user_message=state.user_message,
                model=state.model,
                conversation_history=state.conversation_history,
                system_message=state.system_message,
                memory_context=state.memory_context,
                account_tier=state.account_tier,
                channel=state.channel,
                assurance_level=state.assurance_level,
                product_tier=state.product_tier,
                industry_profile=state.industry_profile,
            )

            # Run agent loop
            result = await self._agent_loop.run(ctx)

            # Update state with result
            state.final_response = result.get("final_response")
            state.iterations = result.get("metadata", {}).get("iterations", 0)
            state.input_tokens = result.get("metadata", {}).get("input_tokens", 0)
            state.output_tokens = result.get("metadata", {}).get("output_tokens", 0)
            state.duration_ms = result.get("metadata", {}).get("duration_ms", 0)
            state.stopped_reason = result.get("metadata", {}).get("stopped_reason", "completed")
            state.messages = result.get("messages", [])

            return state

        except Exception as e:
            logger.exception(f"Agent workflow failed: {e}")
            state.error = str(e)
            state.stopped_reason = "error"
            return state
