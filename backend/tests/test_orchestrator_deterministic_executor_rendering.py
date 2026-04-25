from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from services.orchestrator.backends import ButlerDeterministicExecutor


@dataclass
class _FakeTask:
    id: str = "tsk_fake"
    tool_name: str | None = None
    input_data: dict = field(default_factory=dict)


@dataclass
class _FakeWorkflow:
    plan_schema: dict = field(default_factory=dict)


@dataclass
class _FakeContext:
    task: _FakeTask
    workflow: _FakeWorkflow
    account_id: str = "acct_fake"
    session_id: str = "ses_fake"


class _FakeToolsService:
    async def execute(self, **_kwargs):
        return {"data": {"content": "The current time is 2026-04-24 19:05:44 UTC."}}


@pytest.mark.asyncio
async def test_deterministic_executor_prefers_nested_content_field() -> None:
    executor = ButlerDeterministicExecutor(_FakeToolsService())
    ctx = _FakeContext(
        task=_FakeTask(),
        workflow=_FakeWorkflow(plan_schema={"steps": [{"action": "get_time", "params": {}}]}),
    )

    result = await executor.execute(ctx)

    assert result["content"] == "The current time is 2026-04-24 19:05:44 UTC."
