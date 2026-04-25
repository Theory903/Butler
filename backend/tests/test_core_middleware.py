from __future__ import annotations

import json

import pytest
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

from core.middleware import TrafficGuardMiddleware


class _RedisCritical:
    async def get(self, _key: str) -> str:
        return "CRITICAL"


async def _redis_getter() -> _RedisCritical:
    return _RedisCritical()


async def _call_next(_request: Request) -> Response:
    return Response(status_code=204)


async def _dummy_app(_scope: Scope, _receive: Receive, _send: Send) -> None:
    return None


@pytest.mark.asyncio
async def test_traffic_guard_returns_service_unavailable_problem() -> None:
    middleware = TrafficGuardMiddleware(app=_dummy_app, redis_getter=_redis_getter)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/orchestrator/intake",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
            "server": ("testserver", 80),
        }
    )

    response = await middleware.dispatch(request, _call_next)

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"
    body = json.loads(bytes(response.body))
    assert body["title"] == "Service Unavailable"
    assert body["status"] == 503
