from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

os.environ.setdefault("ALLOWED_ORIGINS", "[]")

from domain.orchestrator.hermes_agent_backend import ButlerToolPolicyGate, HermesAgentBackend
from domain.orchestrator.runtime_kernel import (
    ExecutionContext,
    ExecutionMessage,
    ExecutionStrategy,
)
from domain.tools.hermes_compiler import ButlerToolSpec, RiskTier


def test_policy_gate_visible_tools_without_profile_context() -> None:
    compiled_specs = {
        "web_search": ButlerToolSpec(
            name="web_search",
            hermes_name="web_search",
            risk_tier=RiskTier.L0,
            approval_mode="none",
            visible_tiers=["free", "pro", "enterprise"],
            visible_channels=["api"],
        )
    }

    gate = ButlerToolPolicyGate(
        compiled_specs=compiled_specs,
        account_tier="free",
        channel="api",
        assurance_level="AAL1",
        product_tier=None,
        industry_profile=None,
    )

    assert gate.get_visible_tool_names() == ["web_search"]


@pytest.mark.asyncio
async def test_hermes_backend_passes_user_message_and_history_to_ai_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeAIAgent:
        def __init__(self, **kwargs) -> None:
            captured["init_kwargs"] = kwargs

        def run_conversation(
            self,
            user_message: str,
            system_message: str | None = None,
            conversation_history: list[dict[str, object]] | None = None,
            **_kwargs,
        ) -> SimpleNamespace:
            captured["user_message"] = user_message
            captured["system_message"] = system_message
            captured["conversation_history"] = conversation_history
            return SimpleNamespace(final_output="Hello from Hermes")

    class FakeSessionDB:
        def get_messages_as_conversation(self, _session_id: str) -> list[dict[str, object]]:
            return []

    monkeypatch.setattr("infrastructure.config.get_hermes_env", dict)
    sys.modules["integrations.hermes.run_agent"] = SimpleNamespace(AIAgent=FakeAIAgent)
    sys.modules["integrations.hermes.hermes_state"] = SimpleNamespace(SessionDB=FakeSessionDB)

    backend = HermesAgentBackend(compiled_specs={})
    context = ExecutionContext(
        task=SimpleNamespace(id="task-123"),
        workflow=SimpleNamespace(id="wf-123"),
        strategy=ExecutionStrategy.HERMES_AGENT,
        model="claude-sonnet-4-5",
        toolset=[],
        system_prompt="Butler system prompt",
        messages=[
            ExecutionMessage(role="system", content="Summary context"),
            ExecutionMessage(role="assistant", content="Previous reply"),
            ExecutionMessage(role="user", content="Find latest AI news"),
        ],
        trace_id="trc_123",
        account_id="acct-123",
        session_id="ses-123",
    )

    result = await backend.run(context)

    assert result.content == "Hello from Hermes"
    assert captured["user_message"] == "Find latest AI news"
    assert captured["system_message"] is None
    assert captured["conversation_history"] == [
        {"role": "system", "content": "Summary context"},
        {"role": "assistant", "content": "Previous reply"},
    ]
