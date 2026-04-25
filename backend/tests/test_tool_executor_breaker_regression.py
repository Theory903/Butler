from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.circuit_breaker import CircuitBreakerRegistry
from domain.tools.hermes_compiler import HermesToolCompiler
from domain.tools.hermes_dispatcher import ButlerToolResult
from services.tools.executor import ToolExecutor
from services.tools.verification import ToolVerifier


def _fake_execute_result(value):
    result = MagicMock()
    result.scalars.return_value.first.return_value = value
    return result


@pytest.mark.asyncio
async def test_tool_executor_uses_registry_and_breaker_guard_for_dispatch() -> None:
    compiler = HermesToolCompiler()
    specs = {"get_time": compiler.compile("get_time", {})}

    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock(return_value=_fake_execute_result(None))

    redis = AsyncMock()
    redis.get = AsyncMock(return_value=0)
    redis.incr = AsyncMock()
    redis.decr = AsyncMock()
    redis.setex = AsyncMock()

    executor = ToolExecutor(
        db=db,
        redis=redis,
        verifier=ToolVerifier(),
        compiled_specs=specs,
        breakers=CircuitBreakerRegistry(),
        node_id="node-1",
    )
    executor._dispatcher.dispatch = AsyncMock(
        return_value=ButlerToolResult(
            success=True,
            tool_name="get_time",
            execution_id="bte_test",
            risk_tier="L0",
            duration_ms=5,
            output={"text": "2026-04-24T19:01:40Z"},
        )
    )

    result = await executor.execute(
        "get_time",
        {},
        account_id="03ab81ad-1849-4985-a69b-73079fdecc63",
        session_id="ses_7c696aa078384d44",
        task_id="16c02b94-c064-4ab4-84f7-c8e457931253",
    )

    assert result.success is True
    assert result.tool_name == "get_time"
    assert result.data == {"text": "2026-04-24T19:01:40Z"}
    redis.incr.assert_awaited()
    redis.decr.assert_awaited()
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_tool_executor_rejects_duplicate_inflight_idempotency_key() -> None:
    executor = ToolExecutor(
        db=AsyncMock(),
        redis=AsyncMock(),
        verifier=ToolVerifier(),
        compiled_specs={},
        node_id="node-1",
    )
    executor._redis.set = AsyncMock(side_effect=[True, False])

    await executor._claim_idempotent_execution("idem_123", ttl_seconds=30)

    with pytest.raises(Exception) as exc_info:
        await executor._claim_idempotent_execution("idem_123", ttl_seconds=30)

    assert "already in progress" in exc_info.value.detail
