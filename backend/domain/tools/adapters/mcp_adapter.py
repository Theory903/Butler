"""MCP Tool Adapter - Phase T2.

Converts Model Context Protocol (MCP) tools into canonical ToolSpec.

MCP tools are discovered dynamically from MCP servers.
This adapter converts them to Butler's canonical ToolSpec format.
"""

from __future__ import annotations

from typing import Any

from domain.tools.adapters import DiscoveredTool, ToolAdapter
from domain.tools.spec import ApprovalMode, RiskTier, ToolSpec


class MCPAdapter(ToolAdapter):
    """Adapter for MCP tools."""

    source_system = "mcp_tool"

    def discover(self) -> list[DiscoveredTool]:
        """Discover MCP tools.

        Returns:
            List of discovered tools
        """
        # TODO: Implement actual discovery from MCP servers
        # This would query MCP servers for their tool lists
        # For now, return placeholder for the mcp_bridge
        tools = [
            DiscoveredTool(
                name="mcp_tools",
                source_file="services/tools/mcp_bridge.py",
                source_system=self.source_system,
                metadata={
                    "description": "MCP tools discovered dynamically from MCP servers",
                    "dynamic": True,
                },
            ),
        ]
        return tools

    def to_tool_spec(self, discovered: DiscoveredTool) -> ToolSpec:
        """Convert a discovered MCP tool to ToolSpec.

        Args:
            discovered: Discovered tool

        Returns:
            ToolSpec instance
        """
        name = discovered.name
        metadata = discovered.metadata
        description = metadata.get("description", "")

        # MCP tools vary in risk based on their actual function
        # Default to L2 with sandbox requirement for safety
        # Individual MCP tools should be classified when discovered
        return ToolSpec.create(
            name=name,
            canonical_name=f"mcp.{name}",
            description=description,
            owner="mcp",
            category="mcp",
            version="1.0.0",
            source_system=self.source_system,
            risk_tier=RiskTier.L2,
            approval_mode=ApprovalMode.IMPLICIT,
            sandbox_required=True,  # MCP tools should run in sandbox by default
            network_required=True,
            filesystem_required=False,
            side_effects=True,
            idempotent=False,
            enabled=True,
        )

    def bind_executor(self, spec: ToolSpec) -> Any:
        """Bind executor to the tool spec.

        Args:
            spec: ToolSpec

        Returns:
            Executor callable (routes through mcp_bridge -> ToolExecutor)
        """
        # MCP tools must route through mcp_bridge -> canonical ToolExecutor
        # This returns a wrapper that calls mcp_bridge.execute() -> ToolExecutor.execute()
        # TODO: Implement actual executor binding
        return None
