"""Butler MCP (Model Context Protocol) Integration.

Phase C.1: Thin LangChain wrapper around services/tools/mcp_bridge.py.
Exposes MCP tools as ButlerLangChainTools with full governance.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from langchain.tools import StructuredTool
from langchain_core.tools import BaseTool

from services.tools.mcp_bridge import MCPCallResult, MCPBridgeAdapter, MCPTool, get_mcp_bridge

logger = logging.getLogger(__name__)


@dataclass
class MCPResource:
    """An MCP resource."""

    uri: str
    name: str
    description: str = ""
    mime_type: str = "text/plain"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPPrompt:
    """An MCP prompt template."""

    name: str
    description: str = ""
    arguments: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ButlerMCPTool(BaseTool):
    """LangChain BaseTool wrapper for MCP tools via Butler's MCPBridgeAdapter.

    This wrapper:
    - Routes through Butler's ToolExecutor for governance
    - Uses MCPBridgeAdapter for actual MCP protocol communication
    - Maintains risk-tier gating, approval, audit
    """

    name: str = ""
    description: str = ""
    mcp_bridge: MCPBridgeAdapter | None = None
    server_id: str = ""
    account_id: str = "default"
    tenant_id: str = "default"

    def _run(self, **kwargs: Any) -> Any:
        """Synchronous run - not supported for MCP tools."""
        raise NotImplementedError("MCP tools require async execution")

    async def _arun(self, **kwargs: Any) -> Any:
        """Execute MCP tool via Butler's MCPBridgeAdapter.

        Args:
            **kwargs: Tool arguments

        Returns:
            Tool result
        """
        if not self.mcp_bridge:
            raise RuntimeError("MCP bridge not configured")

        result = await self.mcp_bridge.call_tool(
            server_id=self.server_id,
            tool_name=self.name,
            params=kwargs,
            account_id=self.account_id,
        )

        if not result.success:
            raise Exception(f"MCP tool failed: {result.error}")

        # Return content as text for LangChain
        content_items = result.content or []
        text_content = "\n".join(
            item.get("text", "") for item in content_items if item.get("type") == "text"
        )
        return text_content or str(result.content)


def build_mcp_langchain_tools(
    server_id: str,
    account_id: str = "default",
    tenant_id: str = "default",
) -> list[BaseTool]:
    """Build LangChain tools from MCP server via Butler's MCPBridgeAdapter.

    Args:
        server_id: MCP server ID registered in MCPBridgeAdapter
        account_id: Account ID for governance
        tenant_id: Tenant ID for multi-tenant isolation

    Returns:
        List of LangChain BaseTool objects
    """
    bridge = get_mcp_bridge()
    server_tools = bridge.list_registered_tools(server_id=server_id)

    langchain_tools = []
    for tool_dict in server_tools:
        tool = ButlerMCPTool(
            name=tool_dict["name"],
            description=tool_dict["description"],
            mcp_bridge=bridge,
            server_id=server_id,
            account_id=account_id,
            tenant_id=tenant_id,
        )
        langchain_tools.append(tool)

    logger.info(
        "mcp_langchain_tools_built",
        server_id=server_id,
        tool_count=len(langchain_tools),
    )
    return langchain_tools


def build_all_mcp_langchain_tools(
    account_id: str = "default",
    tenant_id: str = "default",
) -> list[BaseTool]:
    """Build LangChain tools from all registered MCP servers.

    Args:
        account_id: Account ID for governance
        tenant_id: Tenant ID for multi-tenant isolation

    Returns:
        List of LangChain BaseTool objects from all MCP servers
    """
    bridge = get_mcp_bridge()
    all_tools = []

    for server in bridge.list_servers():
        server_id = server["server_id"]
        if server.get("enabled", True):
            server_tools = build_mcp_langchain_tools(
                server_id=server_id,
                account_id=account_id,
                tenant_id=tenant_id,
            )
            all_tools.extend(server_tools)

    logger.info(
        "all_mcp_langchain_tools_built",
        server_count=len(bridge.list_servers()),
        total_tool_count=len(all_tools),
    )
    return all_tools


class ButlerMCPServer:
    """Butler's MCP server for exposing Butler capabilities.

    This server:
    - Exposes Butler tools via MCP
    - Provides Butler memory as resources
    - Offers Butler prompt templates
    - Handles MCP protocol requests
    """

    def __init__(self, host: str = "localhost", port: int = 8000):
        """Initialize the MCP server.

        Args:
            host: Server host
            port: Server port
        """
        self._host = host
        self._port = port
        self._tools: dict[str, MCPTool] = {}
        self._resources: dict[str, MCPResource] = {}
        self._prompts: dict[str, MCPPrompt] = {}

    def register_tool(self, tool: MCPTool) -> None:
        """Register a tool for MCP exposure.

        Args:
            tool: The MCP tool to register
        """
        self._tools[tool.name] = tool
        logger.info("mcp_server_tool_registered", tool_name=tool.name)

    def register_resource(self, resource: MCPResource) -> None:
        """Register a resource for MCP exposure.

        Args:
            resource: The MCP resource to register
        """
        self._resources[resource.uri] = resource
        logger.info("mcp_server_resource_registered", uri=resource.uri)

    def register_prompt(self, prompt: MCPPrompt) -> None:
        """Register a prompt for MCP exposure.

        Args:
            prompt: The MCP prompt to register
        """
        self._prompts[prompt.name] = prompt
        logger.info("mcp_server_prompt_registered", prompt_name=prompt.name)

    async def start(self) -> None:
        """Start the MCP server."""
        logger.info("mcp_server_starting", host=self._host, port=self._port)
        # In production, this would start the actual MCP server

    async def stop(self) -> None:
        """Stop the MCP server."""
        logger.info("mcp_server_stopping")
        # In production, this would stop the actual MCP server

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle an MCP request.

        Args:
            request: The MCP request

        Returns:
            MCP response
        """
        method = request.get("method")

        if method == "tools/list":
            return {
                "result": {
                    "tools": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": tool.input_schema,
                        }
                        for tool in self._tools.values()
                    ]
                }
            }
        elif method == "resources/list":
            return {
                "result": {
                    "resources": [
                        {
                            "uri": resource.uri,
                            "name": resource.name,
                            "description": resource.description,
                            "mimeType": resource.mime_type,
                        }
                        for resource in self._resources.values()
                    ]
                }
            }
        elif method == "prompts/list":
            return {
                "result": {
                    "prompts": [
                        {
                            "name": prompt.name,
                            "description": prompt.description,
                            "arguments": prompt.arguments,
                        }
                        for prompt in self._prompts.values()
                    ]
                }
            }

        return {"error": {"code": -32601, "message": "Method not found"}}
