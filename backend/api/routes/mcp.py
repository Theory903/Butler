"""Butler MCP Edge Terminator — Phase 4 (v3.1, Streamable HTTP spec).

Implements the Model Context Protocol Streamable HTTP compatible transport:
  POST /mcp  — JSON-RPC 2.0 request dispatcher (tools/list, tools/call,
               initialize, ping, resources/list, prompts/list)
  GET  /mcp  — SSE multi-message streaming channel (long-lived)

MCP Session lifecycle:
  1. Client sends POST /mcp  { method: "initialize", ... }
  2. Server allocates a session, returns Mcp-Session-Id header + init result.
  3. Client uses Mcp-Session-Id on subsequent POST requests.
  4. Client may open GET /mcp?mcp_session_id=... for server-push events.
  5. Session expires after idle TTL (default 30 min in Redis).

Auth:
  Every request MUST carry a valid Butler Bearer token (RFC 9068 at+jwt).
  The Mcp-Session-Id is an opaque capability token scoped to one account;
  it cannot be used across accounts.

Error mapping (JSON-RPC 2.0 error codes):
  -32700  Parse error
  -32600  Invalid Request
  -32601  Method not found
  -32602  Invalid params
  -32000  Server error (tool execution failure)
  -32001  Session not found / expired
  -32002  Rate limited
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
import structlog

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from redis.asyncio import Redis

from core.deps import get_cache
from domain.auth.contracts import AccountContext
from domain.auth.exceptions import GatewayErrors
from services.gateway.auth_middleware import JWTAuthMiddleware
from services.gateway.stream_bridge import SSE_HEADERS
from services.auth.jwt import get_jwks_manager

logger = structlog.get_logger(__name__)

mcp_router = APIRouter(tags=["mcp"])

# ── Session store ─────────────────────────────────────────────────────────────

_MCP_SESSION_TTL_S = 1800  # 30 minutes idle
_MCP_SESSION_PREFIX = "mcp:session:"

MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_SERVER_INFO = {"name": "Butler", "version": "3.1.0"}
MCP_CAPABILITIES = {
    "tools": {"listChanged": True},
    "resources": {"listChanged": False},
    "prompts": {"listChanged": False},
    "logging": {},
}


async def _get_account(request: Request, cache: Redis) -> AccountContext:
    """Shared auth for MCP routes."""
    middleware = JWTAuthMiddleware(jwks=get_jwks_manager(), redis=cache)
    authorization = request.headers.get("Authorization")
    return await middleware.authenticate(authorization)


async def _create_session(cache: Redis, account_id: str) -> str:
    session_id = str(uuid.uuid4())
    key = f"{_MCP_SESSION_PREFIX}{session_id}"
    await cache.setex(key, _MCP_SESSION_TTL_S, json.dumps({"account_id": account_id}))
    return session_id


async def _validate_session(cache: Redis, session_id: str, account_id: str) -> bool:
    key = f"{_MCP_SESSION_PREFIX}{session_id}"
    raw = await cache.get(key)
    if not raw:
        return False
    data = json.loads(raw)
    if data.get("account_id") != account_id:
        return False
    # Refresh TTL on use
    await cache.expire(key, _MCP_SESSION_TTL_S)
    return True


# ── JSON-RPC helpers ──────────────────────────────────────────────────────────

def _ok(req_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id, code: int, message: str, data=None) -> dict:
    error: dict = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": error}


def _parse_error(req_id=None):
    return _err(req_id, -32700, "Parse error")


def _invalid_request(req_id=None, detail: str = "Invalid Request"):
    return _err(req_id, -32600, detail)


def _method_not_found(req_id, method: str):
    return _err(req_id, -32601, f"Method not found: {method}")


def _session_error(req_id):
    return _err(req_id, -32001, "MCP session not found or expired")


# ── POST /mcp — JSON-RPC dispatcher ──────────────────────────────────────────

@mcp_router.post("/mcp")
async def mcp_post(request: Request, cache: Redis = Depends(get_cache)):
    """MCP Streamable HTTP POST — JSON-RPC 2.0 dispatcher.

    Handles single-request and batch (array) payloads.
    """
    # Authenticate
    try:
        account = await _get_account(request, cache)
    except Exception:
        return JSONResponse(
            status_code=401,
            content=_err(None, -32600, "Unauthorized"),
            media_type="application/json",
        )

    # Parse body
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content=_parse_error(), media_type="application/json")

    # Batch support — dispatch concurrently (max 10 parallel calls per spec)
    if isinstance(body, list):
        if len(body) > 10:
            return JSONResponse(
                status_code=413,
                content={"error": "Batch size exceeds maximum of 10 requests"},
            )
        results = await asyncio.gather(
            *[_dispatch(req, account, cache, request) for req in body]
        )
        return JSONResponse(content=list(results), media_type="application/json")

    result = await _dispatch(body, account, cache, request)
    return JSONResponse(content=result, media_type="application/json")


async def _dispatch(payload: dict, account: AccountContext, cache: Redis, request: Request) -> dict:
    """Route a single JSON-RPC call."""
    if not isinstance(payload, dict):
        return _invalid_request()

    req_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params", {})

    if not method:
        return _invalid_request(req_id, "Missing method field")

    # ── initialize — first call, allocates session ────────────────────────────
    if method == "initialize":
        session_id = await _create_session(cache, account.account_id)
        result = {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": MCP_CAPABILITIES,
            "serverInfo": MCP_SERVER_INFO,
            "sessionId": session_id,
        }
        return _ok(req_id, result)

    # ── All other methods REQUIRE a valid Mcp-Session-Id header ──────────────
    # ping is an explicit exception — it can refresh keepalive without a session
    mcp_session_id = request.headers.get("Mcp-Session-Id", "")
    if method != "ping":
        if not mcp_session_id:
            return _err(req_id, -32001, "Mcp-Session-Id header required for this method")
        valid = await _validate_session(cache, mcp_session_id, account.account_id)
        if not valid:
            return _session_error(req_id)

    # ── ping ──────────────────────────────────────────────────────────────────
    if method == "ping":
        return _ok(req_id, {})

    # ── tools/list ────────────────────────────────────────────────────────────
    if method == "tools/list":
        try:
            from services.tools.mcp_bridge import get_mcp_bridge
            bridge = get_mcp_bridge()
            tools = bridge.list_registered_tools()
            return _ok(req_id, {"tools": tools})
        except Exception as exc:
            logger.exception("mcp_tools_list_error")
            return _err(req_id, -32000, "Failed to list tools", str(exc))

    # ── tools/call ────────────────────────────────────────────────────────────
    if method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})
        if not tool_name:
            return _err(req_id, -32602, "Missing required param: name")
        try:
            from services.tools.mcp_bridge import get_mcp_bridge
            bridge = get_mcp_bridge()
            call_result = await bridge.call_tool("butler_native", tool_name, tool_args)
            if not call_result.success:
                return _err(req_id, -32000, call_result.error or "Tool execution failed")
            return _ok(req_id, {"content": call_result.content, "isError": False})
        except Exception as exc:
            logger.exception("mcp_tool_call_error", tool=tool_name)
            return _err(req_id, -32000, str(exc))

    # ── resources/list ────────────────────────────────────────────────────────
    if method == "resources/list":
        try:
            from integrations.hermes.tools.registry import registry
            toolsets = registry.get_available_toolsets()
            resources = []
            for name, meta in toolsets.items():
                resources.append({
                    "uri": f"butler://toolsets/{name}",
                    "name": name,
                    "description": meta.get("description", f"Butler toolset: {name}"),
                    "mimeType": "application/json",
                })
            return _ok(req_id, {"resources": resources})
        except Exception as exc:
            return _err(req_id, -32000, "Failed to list resources", str(exc))

    # ── prompts/list ──────────────────────────────────────────────────────────
    if method == "prompts/list":
        try:
            from integrations.hermes.tools.registry import registry
            entries = registry._snapshot_entries()
            prompts = []
            for entry in entries:
                # Map OpenAI schema properties to MCP prompt arguments
                props = entry.schema.get("parameters", {}).get("properties", {})
                args = []
                for p_name, p_meta in props.items():
                    args.append({
                        "name": p_name,
                        "description": p_meta.get("description", ""),
                        "required": p_name in entry.schema.get("parameters", {}).get("required", []),
                    })
                prompts.append({
                    "name": entry.name,
                    "description": entry.description,
                    "arguments": args,
                })
            return _ok(req_id, {"prompts": prompts})
        except Exception as exc:
            return _err(req_id, -32000, "Failed to list prompts", str(exc))

    # ── prompts/get ──────────────────────────────────────────────────────────
    if method == "prompts/get":
        prompt_name = params.get("name")
        if not prompt_name:
            return _err(req_id, -32602, "Missing required param: name")
        try:
            from integrations.hermes.tools.registry import registry
            entry = registry.get_entry(prompt_name)
            if not entry:
                return _err(req_id, -32601, f"Prompt not found: {prompt_name}")
            
            # Surface tool schema as a structured prompt instruction
            instruction = f"Tool: {entry.name}\nDescription: {entry.description}\nSchema:\n{json.dumps(entry.schema, indent=2)}"
            return _ok(req_id, {
                "description": entry.description,
                "messages": [
                    {
                        "role": "user",
                        "content": {"type": "text", "text": instruction}
                    }
                ]
            })
        except Exception as exc:
            return _err(req_id, -32000, "Failed to get prompt", str(exc))

    return _method_not_found(req_id, method)


# ── GET /mcp — SSE server-push channel ───────────────────────────────────────

@mcp_router.get("/mcp")
async def mcp_get(request: Request, cache: Redis = Depends(get_cache)):
    """MCP Streamable HTTP GET — long-lived SSE channel for server-push events.

    The client connects and the server can push:
      - notifications/tools/list_changed
      - notifications/message  (log messages)
      - ping (keepalive)

    Connection is protected by the same Bearer token requirement.
    """
    try:
        account = await _get_account(request, cache)
    except Exception:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    mcp_session_id = request.headers.get("Mcp-Session-Id", "")
    if mcp_session_id:
        valid = await _validate_session(cache, mcp_session_id, account.account_id)
        if not valid:
            return JSONResponse(
                status_code=404,
                content={
                    "type": "https://butler.lasmoid.ai/errors/mcp-session-expired",
                    "title": "MCP Session Expired",
                    "status": 404,
                    "detail": "The MCP session has expired. Send initialize to start a new session.",
                },
                media_type="application/problem+json",
            )

    async def _server_push():
        """Stream MCP server notifications via SSE."""
        # Opening endpoint event (MCP spec requires this for SSE channels)
        yield _mcp_sse_event(
            "endpoint",
            f"/api/v1/mcp",
        )

        try:
            while True:
                # Keepalive ping every 30 s
                try:
                    notification = await asyncio.wait_for(
                        _poll_notifications(cache, account.account_id),
                        timeout=30.0,
                    )
                    if notification:
                        yield _mcp_sse_event("message", json.dumps(notification))
                except asyncio.TimeoutError:
                    # Send MCP ping
                    yield _mcp_sse_event(
                        "message",
                        json.dumps({"jsonrpc": "2.0", "method": "ping", "params": {}}),
                    )

                if await request.is_disconnected():
                    break
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        _server_push(),
        media_type="text/event-stream",
        headers={**SSE_HEADERS, "Mcp-Session-Id": mcp_session_id or ""},
    )


async def _poll_notifications(cache: Redis, account_id: str) -> dict | None:
    """Poll Redis for pending MCP notifications for this account."""
    key = f"mcp:notifications:{account_id}"
    raw = await cache.lpop(key)
    if raw:
        return json.loads(raw)
    # No notification — sleep briefly before re-polling
    await asyncio.sleep(1.0)
    return None


def _mcp_sse_event(event_type: str, data: str) -> str:
    return f"event: {event_type}\ndata: {data}\n\n"
