from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from starlette.requests import Request
from starlette.responses import Response

from api.routes.gateway import ChatRequest, chat
from domain.auth.contracts import AccountContext


class _RateResult:
    remaining = 99

    def ratelimit_header(self) -> str:
        return '"default"; r=99; t=60'

    def ratelimit_policy_header(self) -> str:
        return '"default"; q=100; w=60'


class _UpstreamResponse:
    def json(self) -> dict[str, object]:
        return {
            "workflow_id": "wf-123",
            "content": "Hello from Butler",
            "actions": [],
            "input_tokens": 0,
            "output_tokens": 0,
            "duration_ms": 0,
            "requires_approval": False,
            "approval_id": None,
            "execution_mode": None,
            "planner_source": None,
            "risk_level": None,
            "metadata": {},
        }


class _FakeRateLimiter:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def check(self, _account_id):
        return _RateResult()


@pytest.mark.asyncio
async def test_chat_maps_upstream_orchestrator_result(monkeypatch) -> None:
    async def fake_idempotency_check(self, _key, _body):
        return None

    async def fake_idempotency_store(self, _key, _request_body, _response_body):
        return None

    async def fake_orchestrator_call(_internal_request):
        return _UpstreamResponse()

    @asynccontextmanager
    async def fake_session_scope():
        yield object()

    async def fake_ensure_session(**_kwargs):
        return None

    monkeypatch.setattr("api.routes.gateway.RateLimiter", _FakeRateLimiter)
    monkeypatch.setattr("api.routes.gateway.IdempotencyService.check", fake_idempotency_check)
    monkeypatch.setattr("api.routes.gateway.IdempotencyService.store", fake_idempotency_store)
    monkeypatch.setattr("api.routes.gateway._orchestrator_client.call", fake_orchestrator_call)
    monkeypatch.setattr("api.routes.gateway._session_scope", fake_session_scope)
    monkeypatch.setattr("api.routes.gateway._ensure_session", fake_ensure_session)

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/chat",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
            "server": ("testserver", 80),
        }
    )
    response = Response()
    account = AccountContext(
        sub="03ab81ad-1849-4985-a69b-73079fdecc63",
        sid="ses_e93b57c13af541c6",
        aid="03ab81ad-1849-4985-a69b-73079fdecc63",
        amr=["pwd"],
        acr="aal1",
        device_id=None,
    )
    req = ChatRequest(
        message="Hello Butler, how are you today?",
        session_id="ses_e93b57c13af541c6",
        mode="auto",
        stream=False,
    )

    result = await chat(
        req=req, request=request, response=response, account=account, cache=object()
    )

    assert not isinstance(result, Response)
    assert result.response == "Hello from Butler"
    assert result.workflow_id == "wf-123"
    assert result.session_id == "ses_e93b57c13af541c6"
