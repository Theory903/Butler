from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from domain.orchestrator.runtime_kernel import (
    ExecutionContext,
    ExecutionResult as HermesBackendExecutionResult,
    ExecutionStrategy,
    RuntimeKernel,
)


@dataclass
class _FakeTask:
    id: str = "tsk_fake"
    task_type: str = "respond"


@dataclass
class _FakeWorkflow:
    id: str = "wf_fake"
    account_id: str = "acct_fake"
    session_id: str = "ses_fake"
    mode: str = "macro"
    plan_schema: dict = field(default_factory=dict)


class _HermesBackend:
    async def run(self, _ctx: ExecutionContext) -> HermesBackendExecutionResult:
        return HermesBackendExecutionResult(
            content="The current time is 18:40 UTC.",
            actions=[{"tool_name": "get_time", "success": True}],
            input_tokens=12,
            output_tokens=7,
            duration_ms=42,
            tool_calls_made=1,
            stopped_reason="end_turn",
        )


@pytest.mark.asyncio
async def test_execute_result_normalizes_backend_result_object() -> None:
    kernel = RuntimeKernel(hermes_backend=_HermesBackend())
    ctx = ExecutionContext(
        task=_FakeTask(),
        workflow=_FakeWorkflow(),
        strategy=ExecutionStrategy.HERMES_AGENT,
        model="gpt-test",
        toolset=[],
        system_prompt="You are Butler.",
        messages=[],
        trace_id="trc_test",
        account_id="acct_fake",
        session_id="ses_fake",
    )

    result = await kernel.execute_result(ctx)

    assert result.content == "The current time is 18:40 UTC."
    assert result.tool_calls_made == 1
    assert result.duration_ms == 42
    assert result.token_usage.input_tokens == 12
    assert result.token_usage.output_tokens == 7
