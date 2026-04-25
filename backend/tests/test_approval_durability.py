from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from core.base_config import ButlerBaseConfig
from core.envelope import ButlerEnvelope
from domain.tools.hermes_compiler import ButlerToolSpec, RiskTier
from services.orchestrator.backends import ButlerDeterministicExecutor
from services.orchestrator.executor import ApprovalRequired
from services.orchestrator.planner import ExecutionMode
from services.orchestrator.service import OrchestratorService


class _NullSpan:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeTracer:
    def span(self, *_args, **_kwargs) -> _NullSpan:
        return _NullSpan()

    def get_current_trace_id(self) -> str:
        return "trc_test"


class _FakeToolsService:
    def __init__(self) -> None:
        self._specs = {
            "send_message": ButlerToolSpec(
                name="send_message",
                hermes_name="send_message",
                risk_tier=RiskTier.L2,
                approval_mode="explicit",
            )
        }
        self.execute = AsyncMock()


def _orchestrator_config() -> ButlerBaseConfig:
    return ButlerBaseConfig(
        SERVICE_NAME="orchestrator",
        ENVIRONMENT="development",
        PORT=8000,
        LOG_LEVEL="DEBUG",
        MAX_CONCURRENCY=1000,
        BUTLER_INTERNAL_KEY=SecretStr("test-key"),
    )


@pytest.mark.asyncio
async def test_deterministic_executor_raises_before_risky_tool_dispatch() -> None:
    tools = _FakeToolsService()
    executor = ButlerDeterministicExecutor(tools)
    ctx = SimpleNamespace(
        task=SimpleNamespace(id="tsk_fake", tool_name=None, input_data={}),
        workflow=SimpleNamespace(
            plan_schema={"steps": [{"action": "send_message", "params": {"body": "hi"}}]}
        ),
        account_id="03ab81ad-1849-4985-a69b-73079fdecc63",
        session_id="ses_test",
    )

    with pytest.raises(ApprovalRequired) as exc_info:
        await executor.execute(ctx)

    assert exc_info.value.tool_name == "send_message"
    tools.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_orchestrator_returns_durable_approval_for_direct_runtime(
    monkeypatch,
) -> None:
    monkeypatch.setattr("services.orchestrator.service.get_tracer", lambda: _FakeTracer())

    db = AsyncMock(spec=AsyncSession)
    redis = MagicMock(spec=Redis)
    approval_id = uuid.uuid4()
    workflow_id = uuid.uuid4()

    config = ButlerBaseConfig(
        SERVICE_NAME="orchestrator",
        ENVIRONMENT="development",
        PORT=8000,
        LOG_LEVEL="DEBUG",
        MAX_CONCURRENCY=1000,
        BUTLER_INTERNAL_KEY=SecretStr("test-key"),
    )

    intake_proc = MagicMock()
    intake_proc.process = AsyncMock(return_value=SimpleNamespace(intent="message", mode="tool"))

    plan = MagicMock()
    plan.execution_mode = ExecutionMode.DETERMINISTIC
    plan.to_dict.return_value = {"steps": [{"action": "send_message", "params": {"body": "hi"}}]}

    executor = MagicMock()
    executor._model = "test-model"
    executor._system_prompt = "test"
    executor._extract_toolset.return_value = []
    executor._kernel.execute_result = AsyncMock(
        side_effect=ApprovalRequired(
            approval_type="tool_execution",
            description="Approve tool 'send_message'",
            risk_tier="L2",
            tool_name="send_message",
        )
    )
    executor.suspend_for_approval = AsyncMock(return_value=SimpleNamespace(id=approval_id))

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

    service._check_safety = AsyncMock(return_value={"safe": True})
    service._make_session_store = MagicMock(return_value=None)
    service._should_short_circuit_direct_response = AsyncMock(return_value=False)
    service._build_blended_candidates = AsyncMock(return_value=[])
    service._create_workflow = AsyncMock(
        return_value=SimpleNamespace(id=workflow_id, plan_schema=None)
    )
    service._create_plan = AsyncMock(return_value=plan)

    envelope = ButlerEnvelope(
        account_id="03ab81ad-1849-4985-a69b-73079fdecc63",
        session_id="ses_e93b57c13af541c6",
        request_id="req_approval",
        message="Send this message",
    )

    result = await service.intake(envelope)

    assert result.requires_approval is True
    assert result.approval_id == str(approval_id)
    assert result.workflow_id == str(workflow_id)
    assert result.metadata["status"] == "awaiting_approval"
    executor.suspend_for_approval.assert_awaited_once()


@pytest.mark.asyncio
async def test_approve_request_leaves_resume_transition_to_executor() -> None:
    db = AsyncMock(spec=AsyncSession)
    redis = MagicMock(spec=Redis)
    approval_id = uuid.uuid4()
    task_id = uuid.uuid4()

    approval = SimpleNamespace(
        status="pending",
        task_id=task_id,
        decided_at=None,
    )
    task = SimpleNamespace(
        id=task_id,
        status="awaiting_approval",
    )
    db.get = AsyncMock(side_effect=[approval, task])

    async def resume_task(resume_task_arg):
        assert resume_task_arg.status == "awaiting_approval"

    executor = MagicMock()
    executor.resume_task = AsyncMock(side_effect=resume_task)

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
        executor=executor,
        blender=MagicMock(),
        config=config,
        memory_service=MagicMock(),
    )

    returned_task = await service.approve_request(str(approval_id), "approved")

    assert returned_task is task
    assert approval.status == "approved"
    executor.resume_task.assert_awaited_once_with(task)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_approve_request_rejects_cross_tenant_resolution() -> None:
    db = AsyncMock(spec=AsyncSession)
    redis = MagicMock(spec=Redis)
    approval_id = uuid.uuid4()
    owner_account_id = uuid.uuid4()

    db.get = AsyncMock(
        return_value=SimpleNamespace(
            status="pending",
            account_id=owner_account_id,
            task_id=uuid.uuid4(),
        )
    )

    service = OrchestratorService(
        db=db,
        redis=redis,
        intake_proc=MagicMock(),
        planner=MagicMock(),
        executor=MagicMock(),
        blender=MagicMock(),
        config=_orchestrator_config(),
        memory_service=MagicMock(),
    )

    with pytest.raises(Exception) as exc_info:
        await service.approve_request(
            str(approval_id),
            "approved",
            account_id=str(uuid.uuid4()),
        )

    assert "Approval Request Not Found" in str(exc_info.value)
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_approve_request_blocks_expired_approval_resume() -> None:
    db = AsyncMock(spec=AsyncSession)
    redis = MagicMock(spec=Redis)
    approval_id = uuid.uuid4()

    approval = SimpleNamespace(
        status="pending",
        account_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        decided_at=None,
    )
    db.get = AsyncMock(return_value=approval)

    executor = MagicMock()
    executor.resume_task = AsyncMock()

    service = OrchestratorService(
        db=db,
        redis=redis,
        intake_proc=MagicMock(),
        planner=MagicMock(),
        executor=executor,
        blender=MagicMock(),
        config=_orchestrator_config(),
        memory_service=MagicMock(),
    )

    with pytest.raises(Exception) as exc_info:
        await service.approve_request(
            str(approval_id),
            "approved",
            account_id=str(approval.account_id),
        )

    assert "Approval Request Expired" in str(exc_info.value)
    assert approval.status == "expired"
    assert approval.decided_at is not None
    executor.resume_task.assert_not_awaited()
    db.commit.assert_awaited_once()
