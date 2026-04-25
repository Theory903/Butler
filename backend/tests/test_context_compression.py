"""Verification tests for Context Compression (Anchored Iterative Summarization)."""

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.memory.contracts import ContextPack
from services.memory.anchored_summarizer import AnchoredSummarizer
from services.memory.session_store import ButlerSessionStore
from services.orchestrator.service import OrchestratorService


@pytest.fixture
def mock_ml_runtime():
    runtime = AsyncMock()
    runtime.execute_inference = AsyncMock(
        return_value={
            "generated_text": "## Session Intent\nTest intent\n\n## Decisions Made\n- Decision 1\n\n## Artifact Trail (Files Modified)\n- No files modified yet\n\n## Current State\n- Test state\n\n## Next Steps\n1. Step 1"
        }
    )
    return runtime


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    # Mock for a session with a running summary
    session_data = {
        "session_id": "test_session",
        "account_id": str(uuid.uuid4()),
        "running_summary": "Existing summary content",
        "created_at": datetime.now(UTC).isoformat(),
    }
    redis.get = AsyncMock(
        side_effect=lambda k: (
            json.dumps(session_data) if "butler:session:test_session" in k else None
        )
    )
    redis.lrange = AsyncMock(
        return_value=[
            json.dumps({"role": "user", "content": f"msg {i}", "ts": datetime.now(UTC).isoformat()})
            for i in range(20)
        ]
    )
    return redis


# ─────────────────────────────────────────────────────────────────────────────
# 1. AnchoredSummarizer Tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_summarizer_prompt_generation(mock_ml_runtime):
    summarizer = AnchoredSummarizer(mock_ml_runtime)
    history = [{"role": "user", "content": "hello"}]

    summary = await summarizer.generate_initial_summary(history)

    assert "Session Intent" in summary
    assert mock_ml_runtime.execute_inference.called
    # Check that it uses the fast profile
    args = mock_ml_runtime.execute_inference.call_args[1]
    assert args["profile_name"] == "cloud_fast_general"


# ─────────────────────────────────────────────────────────────────────────────
# 2. SessionStore Context Injection Tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_context_includes_anchor(mock_redis):
    store = ButlerSessionStore(
        account_id="acc_1", session_id="test_session", redis=mock_redis, memory_store=MagicMock()
    )

    context = await store.get_context(query="test")

    assert isinstance(context, ContextPack)
    # History should have 20 original turns + 1 summary anchor
    assert len(context.session_history) == 21
    assert context.session_history[0]["role"] == "system"
    assert "PREVIOUS CONTEXT SUMMARY" in context.session_history[0]["content"]


# ─────────────────────────────────────────────────────────────────────────────
# 3. Compression Trigger Tests (Orchestrator integration)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_triggers_compression():
    # Setup mocks
    db = AsyncMock()
    redis = AsyncMock()
    memory_svc = AsyncMock()
    store = AsyncMock()

    # Mock store to return 20 turns, triggering compression
    store.get_context = AsyncMock(
        return_value=ContextPack(
            session_history=[{"role": "user", "content": "msg"}] * 20,
            relevant_memories=[],
            preferences=[],
            entities=[],
            context_token_budget=4096,
        )
    )

    orchestrator = OrchestratorService(
        db=db,
        redis=redis,
        intake_proc=MagicMock(),
        planner=MagicMock(),
        executor=MagicMock(),
        kernel=MagicMock(),
        blender=MagicMock(),
        memory_service=memory_svc,
    )

    await orchestrator._trigger_compression("acc_1", "sess_1", store)

    assert memory_svc.compress_session.called
    memory_svc.compress_session.assert_called_with("acc_1", "sess_1")
