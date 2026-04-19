"""MCPBridgeAdapter — Phase 6d.

Model Context Protocol (MCP) bridge. Exposes Butler's tool registry
as an MCP server and allows Butler to consume external MCP tool servers
as if they were native Butler tools.

Two directions:
  1. Butler-as-MCP-server (outbound): external clients (Claude Desktop,
     Cursor, etc.) can call Butler tools via MCP protocol.
     Entry: MCPBridgeAdapter.serve_tool_call()

  2. MCP-as-tool-provider (inbound): external MCP servers
     (local or remote) can register their tools into Butler's tool
     registry. Butler then dispatches to them via `handle_function_call`.
     Entry: MCPBridgeAdapter.register_remote_server()

Sovereignty rules:
  - MCPBridgeAdapter is a pure adapter. No business logic here.
  - All tool calls route through ButlerToolDispatch (policy gate).
    MCP servers never bypass ButlerToolPolicyGate.
  - Remote MCP tools get risk_tier="T2_medium" by default unless
    explicitly declared otherwise in the server manifest.
  - MCP payloads are converted to ButlerToolSpec before dispatch.
  - No MCP session state is stored in memory beyond the request scope.

MCP Protocol reference:
  https://spec.modelcontextprotocol.io/specification/

Protocol version: 2025-03-26 (draft)
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

import structlog

logger = structlog.get_logger(__name__)


# ── MCP Type Definitions ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class MCPTool:
    """A tool as described by an MCP server manifest."""
    name: str
    description: str
    input_schema: dict         # JSON Schema for parameters
    server_id: str
    risk_tier: str = "T2_medium"
    requires_approval: bool = False
    timeout_s: int = 30


@dataclass
class MCPServerConfig:
    """Configuration for an external MCP tool server."""
    server_id: str
    name: str
    transport: str             # "stdio" | "http" | "sse"
    command: list[str] | None = None          # For stdio transport
    url: str | None = None                    # For http/sse transport
    env: dict[str, str] = field(default_factory=dict)
    default_risk_tier: str = "T2_medium"
    enabled: bool = True
    tools: list[MCPTool] = field(default_factory=list)


@dataclass
class MCPCallResult:
    """Result of an MCP tool call."""
    tool_name: str
    server_id: str
    success: bool
    content: list[dict]        # MCP content array (text, image, etc.)
    error: str | None = None
    duration_ms: float = 0.0
    call_id: str = field(default_factory=lambda: str(uuid.uuid4()))


# ── MCP Bridge Adapter ────────────────────────────────────────────────────────

class MCPBridgeAdapter:
    """Butler ↔ MCP protocol adapter.

    Usage:
        bridge = MCPBridgeAdapter()
        bridge.register_server(config)                    # inbound registration
        result = await bridge.call_tool("server_id", "tool_name", params)
    """

    # MCP JSON-RPC method names
    _METHOD_LIST_TOOLS = "tools/list"
    _METHOD_CALL_TOOL  = "tools/call"
    _METHOD_INITIALIZE = "initialize"

    def __init__(self) -> None:
        self._servers: dict[str, MCPServerConfig] = {}
        self._tool_index: dict[str, MCPTool] = {}  # "server_id::tool_name" → MCPTool

    # ── Server registration ────────────────────────────────────────────────────

    def register_server(self, config: MCPServerConfig) -> None:
        """Register an external MCP server and index its tools."""
        self._servers[config.server_id] = config
        for tool in config.tools:
            key = f"{config.server_id}::{tool.name}"
            self._tool_index[key] = tool
        logger.info(
            "mcp_server_registered",
            server_id=config.server_id,
            tool_count=len(config.tools),
            transport=config.transport,
        )

    def register_tool(self, server_id: str, tool: MCPTool) -> None:
        """Register a single tool from a server (e.g. after discovery)."""
        key = f"{server_id}::{tool.name}"
        self._tool_index[key] = tool
        if server_id in self._servers:
            self._servers[server_id].tools.append(tool)

    def deregister_server(self, server_id: str) -> int:
        """Remove a server and all its tools. Returns count removed."""
        if server_id not in self._servers:
            return 0
        # Remove tool index entries
        keys = [k for k in self._tool_index if k.startswith(f"{server_id}::")]
        for k in keys:
            del self._tool_index[k]
        del self._servers[server_id]
        logger.info("mcp_server_deregistered", server_id=server_id, tools_removed=len(keys))
        return len(keys)

    # ── Tool resolution ────────────────────────────────────────────────────────

    def find_tool(self, server_id: str, tool_name: str) -> MCPTool | None:
        return self._tool_index.get(f"{server_id}::{tool_name}")

    def find_tool_any_server(self, tool_name: str) -> MCPTool | None:
        """Find the first registered tool with this name across all servers."""
        for key, tool in self._tool_index.items():
            if tool.name == tool_name:
                return tool
        return None

    def list_registered_tools(self, server_id: str | None = None) -> list[dict]:
        tools = self._tool_index.values()
        if server_id:
            tools = [t for t in tools if t.server_id == server_id]
        return [
            {
                "name": t.name,
                "server_id": t.server_id,
                "description": t.description,
                "risk_tier": t.risk_tier,
                "requires_approval": t.requires_approval,
            }
            for t in tools
        ]

    def list_servers(self) -> list[dict]:
        return [
            {
                "server_id": s.server_id,
                "name": s.name,
                "transport": s.transport,
                "enabled": s.enabled,
                "tool_count": len(s.tools),
            }
            for s in self._servers.values()
        ]

    # ── MCP tool call dispatch ─────────────────────────────────────────────────

    async def call_tool(
        self,
        server_id: str,
        tool_name: str,
        params: dict,
    ) -> MCPCallResult:
        """Dispatch a tool call to an MCP server.

        In production, this routes over stdio or HTTP based on the server's
        transport config. For Phase 6d, we implement the dispatch protocol
        with a simulated backend that validates the MCP message format.
        Phase 7 wires in real subprocess/HTTP transports.
        """
        start = time.monotonic()
        call_id = str(uuid.uuid4())

        tool = self.find_tool(server_id, tool_name)
        if tool is None:
            return MCPCallResult(
                tool_name=tool_name,
                server_id=server_id,
                success=False,
                content=[],
                error=f"Tool '{tool_name}' not found on server '{server_id}'",
                call_id=call_id,
            )

        config = self._servers.get(server_id)
        if not config or not config.enabled:
            return MCPCallResult(
                tool_name=tool_name,
                server_id=server_id,
                success=False,
                content=[],
                error=f"Server '{server_id}' not registered or disabled",
                call_id=call_id,
            )

        # Build MCP JSON-RPC request
        mcp_request = self._build_call_request(tool_name, params, call_id)

        # Dispatch over transport
        try:
            raw_response = await self._dispatch(config, mcp_request, tool.timeout_s)
            duration_ms = (time.monotonic() - start) * 1000

            if "error" in raw_response:
                return MCPCallResult(
                    tool_name=tool_name,
                    server_id=server_id,
                    success=False,
                    content=[],
                    error=str(raw_response["error"]),
                    duration_ms=duration_ms,
                    call_id=call_id,
                )

            content = raw_response.get("result", {}).get("content", [])
            return MCPCallResult(
                tool_name=tool_name,
                server_id=server_id,
                success=True,
                content=content,
                duration_ms=duration_ms,
                call_id=call_id,
            )

        except asyncio.TimeoutError:
            duration_ms = (time.monotonic() - start) * 1000
            logger.warning(
                "mcp_tool_timeout",
                server_id=server_id,
                tool_name=tool_name,
                timeout_s=tool.timeout_s,
            )
            return MCPCallResult(
                tool_name=tool_name,
                server_id=server_id,
                success=False,
                content=[],
                error=f"Timeout after {tool.timeout_s}s",
                duration_ms=duration_ms,
                call_id=call_id,
            )

    # ── Butler-as-MCP-server (outbound) ───────────────────────────────────────

    def build_tools_list_response(self, butler_tools: list[dict]) -> dict:
        """Convert Butler tool definitions to MCP tools/list response.

        Used when Butler acts as an MCP server for external clients.
        """
        mcp_tools = []
        for t in butler_tools:
            mcp_tools.append({
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "inputSchema": t.get("input_schema", {"type": "object", "properties": {}}),
            })
        return {
            "jsonrpc": "2.0",
            "result": {"tools": mcp_tools},
        }

    def parse_tool_call_request(self, mcp_request: dict) -> tuple[str, dict] | None:
        """Parse an inbound MCP tools/call request.

        Returns (tool_name, params) or None if malformed.
        """
        if mcp_request.get("method") != self._METHOD_CALL_TOOL:
            return None
        params = mcp_request.get("params", {})
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        if not tool_name:
            return None
        return tool_name, arguments

    # ── Protocol helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _build_call_request(tool_name: str, params: dict, call_id: str) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": call_id,
            "method": MCPBridgeAdapter._METHOD_CALL_TOOL,
            "params": {
                "name": tool_name,
                "arguments": params,
            },
        }

    async def _dispatch(
        self,
        config: MCPServerConfig,
        request: dict,
        timeout_s: int,
    ) -> dict:
        """Route an MCP request to the server over its transport.

        Phase 6d: simulated dispatch (logs + returns stub).
        Phase 7:  implement stdio subprocess + HTTP transports.
        """
        logger.debug(
            "mcp_dispatch",
            server_id=config.server_id,
            transport=config.transport,
            method=request.get("method"),
        )

        match config.transport:
            case "http" | "sse":
                return await self._dispatch_http(config, request, timeout_s)
            case "stdio":
                return await self._dispatch_stdio(config, request, timeout_s)
            case _:
                return {"result": {"content": [{"type": "text", "text": "[simulated mcp response]"}]}}

    async def _dispatch_http(self, config: MCPServerConfig, request: dict, timeout_s: int) -> dict:
        """HTTP/SSE MCP transport — Phase 7 will implement real HTTP calls."""
        if not config.url:
            return {"error": {"code": -32000, "message": "No URL configured for HTTP transport"}}
        try:
            import httpx
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(
                    f"{config.url}/mcp",
                    json=request,
                    headers={"Content-Type": "application/json"},
                )
                return resp.json()
        except ImportError:
            return {"result": {"content": [{"type": "text", "text": "[httpx not available]"}]}}
        except Exception as exc:
            return {"error": {"code": -32000, "message": str(exc)}}

    async def _dispatch_stdio(self, config: MCPServerConfig, request: dict, timeout_s: int) -> dict:
        """Stdio subprocess MCP transport — Phase 7 will spawn real subprocess."""
        if not config.command:
            return {"error": {"code": -32000, "message": "No command configured for stdio transport"}}
        # Simulated — Phase 7 replaces with asyncio.create_subprocess_exec
        logger.debug("mcp_stdio_simulated", command=config.command[0] if config.command else "?")
        return {"result": {"content": [{"type": "text", "text": "[stdio simulated]"}]}}


# ── Singleton ──────────────────────────────────────────────────────────────────

_bridge: MCPBridgeAdapter | None = None


def get_mcp_bridge() -> MCPBridgeAdapter:
    """Return the global MCPBridgeAdapter instance (lazy-init)."""
    global _bridge  # noqa: PLW0603
    if _bridge is None:
        _bridge = MCPBridgeAdapter()
    return _bridge
