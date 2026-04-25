from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import uuid4

from core.envelope import ButlerEnvelope, OrchestratorResult
from services.orchestrator.graph import (
    compile_butler_graph,
    langgraph_available,
    run_fallback_graph,
)
from services.orchestrator.nodes.context import ContextProvider


class ButlerLangGraphRuntime:
    """Butler graph runtime.

    When LangGraph is installed, this runs a compiled named graph. Otherwise it
    runs the same node sequence locally so production code can be wired to the
    graph boundary before optional dependencies are present.
    """

    @staticmethod
    def available() -> bool:
        return True

    @staticmethod
    def langgraph_available() -> bool:
        return langgraph_available()

    async def run(
        self,
        envelope: ButlerEnvelope,
        *,
        core_runner: Callable[[ButlerEnvelope], Awaitable[OrchestratorResult]],
        context_provider: ContextProvider | None = None,
        checkpointer: object | None = None,
    ) -> OrchestratorResult:
        if self.langgraph_available():
            compiled = compile_butler_graph(
                core_runner=core_runner,
                context_provider=context_provider,
                checkpointer=checkpointer,
            )
            state = await compiled.ainvoke(
                {"envelope": envelope, "graph_path": []},
                config={
                    "configurable": {
                        "thread_id": envelope.session_id,
                        "checkpoint_ns": envelope.identity.tenant_id
                        if envelope.identity
                        else envelope.account_id,
                    }
                },
            )
        else:
            state = await run_fallback_graph(
                envelope=envelope,
                core_runner=core_runner,
                context_provider=context_provider,
            )

        final_result = state.get("final_result")
        if isinstance(final_result, OrchestratorResult):
            return final_result

        return OrchestratorResult(
            workflow_id=str(uuid4()),
            session_id=envelope.session_id,
            request_id=envelope.request_id,
            content="Butler could not complete the request.",
            actions=[],
            metadata={"phase": "langgraph_core_failed"},
        )
