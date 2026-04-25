from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from core.envelope import ButlerEnvelope, OrchestratorResult
from services.orchestrator import graph as graph_mod
from services.orchestrator.langgraph_runtime import ButlerLangGraphRuntime


@dataclass(frozen=True)
class _FakeCompiledGraph:
    nodes: dict
    edges: list[tuple[object, object]]

    async def ainvoke(self, state: dict, config: dict | None = None) -> dict:
        assert config is not None
        assert config["configurable"]["thread_id"] == state["envelope"].session_id

        node = "intake"
        while True:
            state = await self.nodes[node](state)
            next_nodes = [target for source, target in self.edges if source == node]
            if not next_nodes or next_nodes[0] is graph_mod.END:
                return state
            node = next_nodes[0]


class _FakeStateGraph:
    def __init__(self, _state_type: object) -> None:
        self._nodes = {}
        self._edges = []

    def add_node(self, name: str, node: object) -> None:
        self._nodes[name] = node

    def add_edge(self, source: object, target: object) -> None:
        self._edges.append((source, target))

    def compile(self, checkpointer: object | None = None) -> _FakeCompiledGraph:
        del checkpointer
        assert self._nodes
        return _FakeCompiledGraph(nodes=self._nodes, edges=self._edges)


@pytest.mark.asyncio
async def test_langgraph_runtime_compiles_named_graph(monkeypatch) -> None:
    monkeypatch.setattr(graph_mod, "StateGraph", _FakeStateGraph)
    monkeypatch.setattr(graph_mod, "START", "__start__")
    monkeypatch.setattr(graph_mod, "END", "__end__")

    runtime = ButlerLangGraphRuntime()
    assert runtime.available() is True
    assert runtime.langgraph_available() is True

    envelope = ButlerEnvelope(
        account_id="03ab81ad-1849-4985-a69b-73079fdecc63",
        session_id="ses_7c696aa078384d44",
        request_id="req_test",
        message="hello",
        model="gpt-test",
    )

    async def _core_runner(_envelope: ButlerEnvelope) -> OrchestratorResult:
        return OrchestratorResult(
            workflow_id="wf_test",
            session_id=_envelope.session_id,
            request_id=_envelope.request_id,
            content="wrapped",
            actions=[],
        )

    async def _context_provider(_envelope: ButlerEnvelope) -> object:
        return SimpleNamespace(
            session_history=[{"role": "user", "content": "hello"}],
            relevant_memories=[{"content": "memory"}],
            summary_anchor="summary",
        )

    result = await runtime.run(
        envelope,
        core_runner=_core_runner,
        context_provider=_context_provider,
    )

    assert result.content == "wrapped"
    assert result.metadata["graph_runtime"] is True
    assert result.metadata["graph_context"]["source"] == "memory_service"
    assert result.metadata["graph_context"]["history_count"] == 1
    assert result.metadata["graph_path"] == [
        "intake",
        "safety",
        "context",
        "plan",
        "execute",
        "approval_interrupt",
        "memory_writeback",
        "render",
    ]


@pytest.mark.asyncio
async def test_graph_runtime_fallback_runs_named_nodes(monkeypatch) -> None:
    monkeypatch.setattr(graph_mod, "StateGraph", None)
    monkeypatch.setattr(graph_mod, "START", None)
    monkeypatch.setattr(graph_mod, "END", None)

    runtime = ButlerLangGraphRuntime()
    assert runtime.langgraph_available() is False

    envelope = ButlerEnvelope(
        account_id="03ab81ad-1849-4985-a69b-73079fdecc63",
        session_id="ses_7c696aa078384d44",
        request_id="req_test",
        message="hello",
    )

    async def _core_runner(_envelope: ButlerEnvelope) -> OrchestratorResult:
        return OrchestratorResult(
            workflow_id="wf_test",
            session_id=_envelope.session_id,
            request_id=_envelope.request_id,
            content="fallback",
            actions=[],
        )

    result = await runtime.run(envelope, core_runner=_core_runner)

    assert result.content == "fallback"
    assert result.metadata["graph_runtime"] is True
    assert "execute" in result.metadata["graph_path"]
