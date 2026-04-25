from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from core.base_config import ButlerBaseConfig
from core.envelope import ButlerEnvelope
from services.ml.smart_router import ModelTier
from services.orchestrator.executor import WorkflowResult
from services.orchestrator.service import OrchestratorService


class _NullSpan:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeTracer:
    def span(self, *_args, **_kwargs) -> _NullSpan:
        return _NullSpan()


class _FailingWorkflow:
    def __init__(self, workflow_id: str) -> None:
        self._workflow_id = workflow_id
        self.raise_on_access = False
        self.plan_schema = None

    @property
    def id(self) -> str:
        if self.raise_on_access:
            raise RuntimeError("expired workflow id")
        return self._workflow_id


class _FakePlan:
    def to_dict(self) -> dict[str, object]:
        return {"steps": []}

    execution_mode = type("ExecutionMode", (), {"value": "workflow"})()


class _RoutingDecision:
    def __init__(self, tier: ModelTier) -> None:
        self.tier = tier


def _orchestrator_config() -> ButlerBaseConfig:
    return ButlerBaseConfig(
        SERVICE_NAME="orchestrator",
        ENVIRONMENT="development",
        PORT=8000,
        LOG_LEVEL="DEBUG",
        MAX_CONCURRENCY=1000,
        BUTLER_INTERNAL_KEY=SecretStr("test-key"),
    )


def test_make_session_store_reuses_canonical_memory_service() -> None:
    service = OrchestratorService(
        db=AsyncMock(spec=AsyncSession),
        redis=MagicMock(spec=Redis),
        intake_proc=MagicMock(),
        planner=MagicMock(),
        executor=MagicMock(),
        blender=MagicMock(),
        config=_orchestrator_config(),
        memory_store=MagicMock(),
        memory_service=MagicMock(),
    )

    store = service._make_session_store(
        session_id="ses_e93b57c13af541c6",
        account_id="03ab81ad-1849-4985-a69b-73079fdecc63",
    )

    assert store is not None
    assert store._memory is service._memory


@pytest.mark.asyncio
async def test_intake_uses_safe_workflow_id_on_executor_failure(monkeypatch) -> None:
    monkeypatch.setattr("services.orchestrator.service.get_tracer", lambda: _FakeTracer())

    db = AsyncMock(spec=AsyncSession)
    redis = MagicMock(spec=Redis)
    executor = MagicMock()

    config = ButlerBaseConfig(
        SERVICE_NAME="orchestrator",
        ENVIRONMENT="development",
        PORT=8000,
        LOG_LEVEL="DEBUG",
        MAX_CONCURRENCY=1000,
        BUTLER_INTERNAL_KEY=SecretStr("test-key"),
    )

    intake_proc = MagicMock()
    intake_proc.process = AsyncMock(return_value=SimpleNamespace())

    service = OrchestratorService(
        db=db,
        redis=redis,
        intake_proc=intake_proc,
        planner=MagicMock(),
        executor=executor,
        blender=MagicMock(),
        config=config,
        memory_service=MagicMock(),
    )

    workflow = _FailingWorkflow("wf-123")

    async def fake_execute_workflow(*, workflow, plan):
        workflow.raise_on_access = True
        raise RuntimeError("boom")

    executor.execute_workflow = AsyncMock(side_effect=fake_execute_workflow)

    service._check_safety = AsyncMock(return_value={"safe": True})
    service._make_session_store = MagicMock(return_value=None)
    service._should_short_circuit_direct_response = AsyncMock(return_value=False)
    service._build_blended_candidates = AsyncMock(return_value=[])
    service._create_workflow = AsyncMock(return_value=workflow)
    service._create_plan = AsyncMock(return_value=_FakePlan())

    envelope = ButlerEnvelope(
        account_id="03ab81ad-1849-4985-a69b-73079fdecc63",
        session_id="ses_e93b57c13af541c6",
        message="Hello Butler",
    )

    result = await service.intake(envelope)

    assert result.workflow_id == "wf-123"
    assert result.content == "Butler could not complete the request."
    db.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_intake_leaves_plan_lowering_to_executor(monkeypatch) -> None:
    monkeypatch.setattr("services.orchestrator.service.get_tracer", lambda: _FakeTracer())

    db = AsyncMock(spec=AsyncSession)
    redis = MagicMock(spec=Redis)
    executor = MagicMock()

    config = ButlerBaseConfig(
        SERVICE_NAME="orchestrator",
        ENVIRONMENT="development",
        PORT=8000,
        LOG_LEVEL="DEBUG",
        MAX_CONCURRENCY=1000,
        BUTLER_INTERNAL_KEY=SecretStr("test-key"),
    )

    intake_proc = MagicMock()
    intake_proc.process = AsyncMock(return_value=SimpleNamespace())

    service = OrchestratorService(
        db=db,
        redis=redis,
        intake_proc=intake_proc,
        planner=MagicMock(),
        executor=executor,
        blender=MagicMock(),
        config=config,
        memory_service=MagicMock(),
    )

    workflow = _FailingWorkflow("wf-456")

    async def fake_execute_workflow(*, workflow, plan):
        assert workflow.plan_schema is None
        return WorkflowResult(workflow_id="wf-456", content="Hello from Butler")

    executor.execute_workflow = AsyncMock(side_effect=fake_execute_workflow)

    service._check_safety = AsyncMock(return_value={"safe": True})
    service._make_session_store = MagicMock(return_value=None)
    service._should_short_circuit_direct_response = AsyncMock(return_value=False)
    service._build_blended_candidates = AsyncMock(return_value=[])
    service._create_workflow = AsyncMock(return_value=workflow)
    service._create_plan = AsyncMock(return_value=_FakePlan())

    envelope = ButlerEnvelope(
        account_id="03ab81ad-1849-4985-a69b-73079fdecc63",
        session_id="ses_e93b57c13af541c6",
        message="Hello Butler",
    )

    result = await service.intake(envelope)

    assert result.workflow_id == "wf-456"
    assert result.content == "Hello from Butler"


@pytest.mark.asyncio
async def test_intake_short_circuits_general_intent_to_direct_response(monkeypatch) -> None:
    monkeypatch.setattr("services.orchestrator.service.get_tracer", lambda: _FakeTracer())

    db = AsyncMock(spec=AsyncSession)
    redis = MagicMock(spec=Redis)
    executor = MagicMock()

    config = ButlerBaseConfig(
        SERVICE_NAME="orchestrator",
        ENVIRONMENT="development",
        PORT=8000,
        LOG_LEVEL="DEBUG",
        MAX_CONCURRENCY=1000,
        BUTLER_INTERNAL_KEY=SecretStr("test-key"),
    )

    intake_proc = MagicMock()
    intake_proc.process = AsyncMock(
        return_value=SimpleNamespace(intent="general", requires_tools=False, mode="agentic")
    )

    smart_router = MagicMock()
    smart_router.route.return_value = _RoutingDecision(ModelTier.T3)

    executor = MagicMock()
    executor.execute = AsyncMock(
        return_value=MagicMock(
            content="Hello from workflow",
            actions=[],
        )
    )
    executor.execute_workflow = AsyncMock(
        return_value=MagicMock(
            content="Hello from workflow",
            workflow_id="test-workflow",
        )
    )

    blender = MagicMock()
    blender.blend = AsyncMock(return_value=[])

    planner = MagicMock()
    planner.create_plan = AsyncMock(
        return_value=MagicMock(
            steps=[],
            intent="general",
        )
    )

    service = OrchestratorService(
        db=db,
        redis=redis,
        intake_proc=intake_proc,
        planner=planner,
        executor=executor,
        blender=blender,
        config=config,
        memory_service=MagicMock(),
        smart_router=smart_router,
    )

    service._check_safety = AsyncMock(return_value={"safe": True})
    service._make_session_store = MagicMock(return_value=None)
    service._generate_direct_llm_response = AsyncMock(return_value="Hello! I'm doing well.")
    service._create_workflow = AsyncMock()

    envelope = ButlerEnvelope(
        account_id="03ab81ad-1849-4985-a69b-73079fdecc63",
        session_id="ses_e93b57c13af541c6",
        message="Hello Butler",
    )

    result = await service.intake(envelope)

    # No short-circuit - goes through workflow (LLM decides)
    assert result.content == "Hello from workflow"


@pytest.mark.asyncio
async def test_short_circuit_excludes_research_and_research_mode(monkeypatch) -> None:
    monkeypatch.setattr("services.orchestrator.service.get_tracer", lambda: _FakeTracer())

    db = AsyncMock(spec=AsyncSession)
    redis = MagicMock(spec=Redis)

    config = ButlerBaseConfig(
        SERVICE_NAME="orchestrator",
        ENVIRONMENT="development",
        PORT=8000,
        LOG_LEVEL="DEBUG",
        MAX_CONCURRENCY=1000,
        BUTLER_INTERNAL_KEY=SecretStr("test-key"),
    )

    intake_proc = MagicMock()

    smart_router = MagicMock()

    service = OrchestratorService(
        db=db,
        redis=redis,
        intake_proc=intake_proc,
        planner=MagicMock(),
        executor=MagicMock(),
        blender=MagicMock(),
        config=config,
        memory_service=MagicMock(),
        smart_router=smart_router,
    )

    intake_general = SimpleNamespace(intent="general", requires_tools=False)
    intake_research = SimpleNamespace(
        intent="question", requires_tools=False, requires_research=True
    )
    intake_research_mode = SimpleNamespace(intent="general", requires_tools=False, mode="research")

    should_general = await service._should_short_circuit_direct_response(
        intake_result=intake_general,
        message="hello",
    )
    should_research = await service._should_short_circuit_direct_response(
        intake_result=intake_research,
        message="latest news",
    )
    should_mode = await service._should_short_circuit_direct_response(
        intake_result=intake_research_mode,
        message="find info",
    )

    # Always returns False - LLM decides what to do
    assert should_general is False
    assert should_research is False
    assert should_mode is False


@pytest.mark.asyncio
async def test_build_messages_hydrates_butler_history_from_hermes_when_empty(monkeypatch) -> None:
    monkeypatch.setattr("services.orchestrator.service.get_tracer", lambda: _FakeTracer())

    class FakeSessionDB:
        def get_messages_as_conversation(self, session_id: str) -> list[dict[str, str]]:
            assert session_id == "ses_e93b57c13af541c6"
            return [
                {"role": "user", "content": "Earlier Butler question"},
                {"role": "assistant", "content": "Earlier Butler answer"},
            ]

    sys.modules["integrations.hermes.hermes_state"] = SimpleNamespace(SessionDB=FakeSessionDB)

    db = AsyncMock(spec=AsyncSession)
    redis = MagicMock(spec=Redis)

    config = ButlerBaseConfig(
        SERVICE_NAME="orchestrator",
        ENVIRONMENT="development",
        PORT=8000,
        LOG_LEVEL="DEBUG",
        MAX_CONCURRENCY=1000,
        BUTLER_INTERNAL_KEY=SecretStr("test-key"),
    )

    service = OrchestratorService(
        db=db,
        redis=redis,
        intake_proc=MagicMock(),
        planner=MagicMock(),
        executor=MagicMock(),
        blender=MagicMock(),
        config=config,
        memory_service=MagicMock(),
    )

    empty_context = SimpleNamespace(summary_anchor="", session_history=[])
    hydrated_context = SimpleNamespace(
        summary_anchor="",
        session_history=[
            {"role": "user", "content": "Earlier Butler question"},
            {"role": "assistant", "content": "Earlier Butler answer"},
        ],
    )
    store = MagicMock()
    store.get_context = AsyncMock(side_effect=[empty_context, hydrated_context])
    store.append_turn = AsyncMock()

    messages = await service._build_messages(
        store=store,
        envelope=ButlerEnvelope(
            account_id="03ab81ad-1849-4985-a69b-73079fdecc63",
            session_id="ses_e93b57c13af541c6",
            message="Latest request",
        ),
        candidates=[],
    )

    assert [message.content for message in messages] == [
        "Earlier Butler question",
        "Earlier Butler answer",
        "Latest request",
    ]
    assert store.append_turn.await_count == 2
