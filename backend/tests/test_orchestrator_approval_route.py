from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.routes.orchestrator import (
    ApprovalDecisionRequest,
    decide_approval_legacy,
    resolve_approval,
)
from domain.auth.contracts import AccountContext


def _account_context(account_id: str) -> AccountContext:
    return AccountContext(
        sub=account_id,
        sid="ses_test",
        aid=account_id,
        amr=["pwd"],
        acr="aal1",
    )


@pytest.mark.asyncio
async def test_resolve_approval_returns_serialized_decision_response() -> None:
    approval_id = str(uuid.uuid4())
    account_id = str(uuid.uuid4())
    task_id = uuid.uuid4()
    service = SimpleNamespace(
        approve_request=AsyncMock(return_value=SimpleNamespace(id=task_id, status="completed"))
    )

    response = await resolve_approval(
        approval_id=approval_id,
        req=ApprovalDecisionRequest(decision="approved"),
        account=_account_context(account_id),
        svc=service,
    )

    assert response.approval_id == approval_id
    assert response.decision == "approved"
    assert response.task_id == str(task_id)
    assert response.task_status == "completed"
    service.approve_request.assert_awaited_once_with(
        approval_id,
        "approved",
        account_id=account_id,
    )


@pytest.mark.asyncio
async def test_legacy_approval_route_delegates_to_canonical_resolution() -> None:
    approval_id = str(uuid.uuid4())
    account_id = str(uuid.uuid4())
    task_id = uuid.uuid4()
    service = SimpleNamespace(
        approve_request=AsyncMock(return_value=SimpleNamespace(id=task_id, status="failed"))
    )

    response = await decide_approval_legacy(
        approval_id=approval_id,
        req=ApprovalDecisionRequest(decision="denied"),
        account=_account_context(account_id),
        svc=service,
    )

    assert response.approval_id == approval_id
    assert response.decision == "denied"
    assert response.task_status == "failed"
    service.approve_request.assert_awaited_once_with(
        approval_id,
        "denied",
        account_id=account_id,
    )
