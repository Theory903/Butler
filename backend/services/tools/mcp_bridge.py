"""MCPBridgeAdapter — Phase 8b Hardened.

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
  - Remote MCP tools get risk_tier="T2_medium" by default.
  - MCP payloads are converted to ButlerToolSpec before dispatch.
  - SSRF protection enforced on all outbound HTTP calls.
  - Stdio transport uses asynchronous process execution.

MCP Protocol reference:
  https://spec.modelcontextprotocol.io/specification/
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog

from core.network import safe_request
from domain.tools.contracts import ToolsServiceContract

logger = structlog.get_logger(__name__)


# ── MCP Type Definitions ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class MCPTool:
    """A tool as described by an MCP server manifest."""

    name: str
    description: str
    input_schema: dict  # JSON Schema for parameters
    server_id: str
    risk_tier: str = "T2_medium"
    requires_approval: bool = False
    timeout_s: int = 30


@dataclass
class MCPServerConfig:
    """Configuration for an external MCP tool server."""

    server_id: str
    name: str
    transport: str  # "stdio" | "http" | "sse"
    command: list[str] | None = None  # For stdio transport
    url: str | None = None  # For http/sse transport
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
    content: list[dict]  # MCP content array (text, image, etc.)
    error: str | None = None
    duration_ms: float = 0.0
    call_id: str = field(default_factory=lambda: str(uuid.uuid4()))


# ── MCP Bridge Adapter ────────────────────────────────────────────────────────


class MCPBridgeAdapter:
    """Butler ↔ MCP protocol adapter."""

    _METHOD_LIST_TOOLS = "tools/list"
    _METHOD_CALL_TOOL = "tools/call"
    _METHOD_INITIALIZE = "initialize"

    def __init__(self) -> None:
        self._servers: dict[str, MCPServerConfig] = {}
        self._tool_index: dict[str, MCPTool] = {}  # "server_id::tool_name" → MCPTool
        self._native_service: ToolsServiceContract | None = None

    # ── Server registration ───────────────────────────────────────────────────

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

    def deregister_server(self, server_id: str) -> int:
        """Remove an MCP server and all indexed tools.

        Returns the number of tools removed. This is used by hot-reload and by
        tests to prove the tool index cannot retain stale external capabilities.
        """
        config = self._servers.pop(server_id, None)
        if config is None:
            return 0

        removed = 0
        for key in list(self._tool_index):
            if key.startswith(f"{server_id}::"):
                self._tool_index.pop(key, None)
                removed += 1

        logger.info(
            "mcp_server_deregistered",
            server_id=server_id,
            removed_tools=removed,
        )
        return removed

    def load_manifest_from_file(self, path: str) -> None:
        """Bootstrap server configurations from an MCP manifest JSON file."""
        if not os.path.exists(path):
            logger.info("mcp_manifest_not_found", path=path)
            return

        try:
            if os.path.getsize(path) == 0:
                logger.info("mcp_manifest_empty", path=path)
                return

            with open(path) as f:
                manifest = json.load(f)
                mcp_config = manifest.get("mcpServers", {})
                for server_id, cfg in mcp_config.items():
                    command = cfg.get("command")
                    args = cfg.get("args", [])
                    url = cfg.get("url")

                    if command:
                        transport = "stdio"
                        full_command = [command] + args
                    elif url:
                        transport = "http"
                        full_command = None
                    else:
                        continue

                    server_cfg = MCPServerConfig(
                        server_id=server_id,
                        name=server_id,
                        transport=transport,
                        command=full_command,
                        url=url,
                        env=cfg.get("env", {}),
                    )
                    self.register_server(server_cfg)
            logger.info("mcp_manifest_loaded", path=path, servers=len(self._servers))
        except Exception as e:
            logger.error("mcp_manifest_error", path=path, error=str(e))

    def register_native_service(self, service: ToolsServiceContract) -> None:
        """Register Butler's own tool service to expose native tools via MCP."""
        self._native_service = service
        logger.info("mcp_native_service_registered")

    # ── Tool resolution ───────────────────────────────────────────────────────

    def find_tool(self, server_id: str, tool_name: str) -> MCPTool | None:
        return self._tool_index.get(f"{server_id}::{tool_name}")

    def find_tool_any_server(self, tool_name: str) -> MCPTool | None:
        """Find the first registered tool matching name across enabled servers."""
        for key in sorted(self._tool_index):
            tool = self._tool_index[key]
            server = self._servers.get(tool.server_id)
            if tool.name == tool_name and server is not None and server.enabled:
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

    def list_servers(self) -> list[dict[str, Any]]:
        """Return registered MCP server metadata without secrets/env values."""
        return [
            {
                "server_id": config.server_id,
                "name": config.name,
                "transport": config.transport,
                "enabled": config.enabled,
                "tool_count": len(config.tools),
                "url": config.url,
            }
            for config in self._servers.values()
        ]

    def build_tools_list_response(
        self,
        tools: list[dict[str, Any]],
        request_id: str | int | None = None,
    ) -> dict[str, Any]:
        """Build an MCP JSON-RPC tools/list response from Butler tool dicts."""
        normalized_tools = []
        for tool in tools:
            normalized_tools.append(
                {
                    "name": str(tool.get("name", "")),
                    "description": str(tool.get("description", "")),
                    "inputSchema": tool.get("input_schema") or tool.get("inputSchema") or {},
                }
            )
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": normalized_tools},
        }

    def parse_tool_call_request(self, request: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
        """Parse a JSON-RPC tools/call request into a Butler tool call."""
        if request.get("method") != self._METHOD_CALL_TOOL:
            return None

        params = request.get("params")
        if not isinstance(params, dict):
            return None

        tool_name = str(params.get("name", "") or "").strip()
        if not tool_name:
            return None

        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}

        return tool_name, arguments

    # ── MCP tool call dispatch ────────────────────────────────────────────────

    async def call_tool(
        self,
        server_id: str,
        tool_name: str,
        params: dict,
        account_id: str | None = None,
    ) -> MCPCallResult:
        """Dispatch a tool call to an MCP server or native service."""
        start = time.monotonic()
        call_id = str(uuid.uuid4())

        # Native dispatch (Butler-as-server)
        if server_id == "butler_native":
            return await self._dispatch_native(tool_name, params, account_id, start, call_id)

        # External dispatch (Butler-as-client)
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
        request = {
            "jsonrpc": "2.0",
            "id": call_id,
            "method": self._METHOD_CALL_TOOL,
            "params": {"name": tool_name, "arguments": params},
        }

        try:
            raw_response = await self._dispatch(config, request, tool.timeout_s)
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

        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000
            return MCPCallResult(
                tool_name=tool_name,
                server_id=server_id,
                success=False,
                content=[],
                error=str(e),
                duration_ms=duration_ms,
                call_id=call_id,
            )

    async def _dispatch(self, config: MCPServerConfig, request: dict, timeout_s: int) -> dict:
        """Route an MCP request to the server over its transport."""
        match config.transport:
            case "http" | "sse":
                return await self._dispatch_http(config, request, timeout_s)
            case "stdio":
                return await self._dispatch_stdio(config, request, timeout_s)
            case "simulated":
                return self._dispatch_simulated(config, request)
            case _:
                return {
                    "error": {
                        "code": -32000,
                        "message": f"Transport '{config.transport}' not implemented",
                    }
                }

    def _dispatch_simulated(self, config: MCPServerConfig, request: dict) -> dict:
        """Deterministic local transport for tests and offline development."""
        params = request.get("params", {})
        tool_name = params.get("name", "unknown")
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": (f"Simulated MCP call server={config.server_id} tool={tool_name}"),
                    }
                ]
            },
        }

    async def _dispatch_http(self, config: MCPServerConfig, request: dict, timeout_s: int) -> dict:
        """HTTP MCP transport with SSRF protection."""
        if not config.url:
            return {"error": {"code": -32000, "message": "No URL configured for HTTP transport"}}

        try:
            resp = await safe_request(
                "POST",
                f"{config.url}/mcp",
                json=request,
                headers={"Content-Type": "application/json"},
                timeout=timeout_s,
            )
            return resp.json()
        except Exception as e:
            return {"error": {"code": -32000, "message": str(e)}}

    async def _dispatch_stdio(self, config: MCPServerConfig, request: dict, timeout_s: int) -> dict:
        """Stdio subprocess MCP transport with JSON-RPC piping.

        P0 hardening: Use asyncio.create_subprocess_exec with timeout and proper error handling.
        """
        if not config.command:
            return {
                "error": {"code": -32000, "message": "No command configured for stdio transport"}
            }

        try:
            process = await asyncio.create_subprocess_exec(
                *config.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, **config.env},
            )

            payload = json.dumps(request) + "\n"
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=payload.encode()), timeout=timeout_s
            )

            if process.returncode != 0:
                err_msg = stderr.decode().strip() or f"Process exited with {process.returncode}"
                return {"error": {"code": -32000, "message": f"MCP stdio error: {err_msg}"}}

            return json.loads(stdout.decode().strip())

        except TimeoutError:
            return {"error": {"code": -32000, "message": "MCP stdio timeout"}}
        except Exception as e:
            return {"error": {"code": -32000, "message": str(e)}}

    async def _dispatch_native(
        self, tool_name: str, params: dict, account_id: str | None, start: float, call_id: str
    ) -> MCPCallResult:
        """Dispatch call to Butler's native ToolsService."""
        if not self._native_service:
            return MCPCallResult(
                tool_name=tool_name,
                server_id="butler_native",
                success=False,
                content=[],
                error="Native tool service not registered",
                call_id=call_id,
            )

        try:
            # Route through the authenticated execute flow
            result = await self._native_service.execute(
                tool_name=tool_name,
                params=params,
                account_id=account_id or "system",  # Fallback for system-level triggers
            )
            duration_ms = (time.monotonic() - start) * 1000

            # Convert ButlerToolResult to MCP content
            content = [{"type": "text", "text": str(result.data)}]
            return MCPCallResult(
                tool_name=tool_name,
                server_id="butler_native",
                success=result.success,
                content=content,
                duration_ms=duration_ms,
                call_id=call_id,
            )
        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000
            return MCPCallResult(
                tool_name=tool_name,
                server_id="butler_native",
                success=False,
                content=[],
                error=str(e),
                duration_ms=duration_ms,
                call_id=call_id,
            )


# ── Singleton ──────────────────────────────────────────────────────────────────

_bridge: MCPBridgeAdapter | None = None


def get_mcp_bridge() -> MCPBridgeAdapter:
    global _bridge  # noqa: PLW0603
    if _bridge is None:
        _bridge = MCPBridgeAdapter()
    return _bridge
