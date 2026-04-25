"""ACP Tool Adapter - Phase T2.

Converts Agent Control Protocol (ACP) tools into canonical ToolSpec.

ACP tools are for editor/client context, repo/file access, and coding agents.
This adapter converts them to Butler's canonical ToolSpec format.
"""

from __future__ import annotations

from typing import Any

from domain.tools.adapters import DiscoveredTool, ToolAdapter
from domain.tools.spec import ApprovalMode, RiskTier, ToolSpec


class ACPAdapter(ToolAdapter):
    """Adapter for ACP tools."""

    source_system = "acp_tool"

    def discover(self) -> list[DiscoveredTool]:
        """Discover ACP tools.

        Returns:
            List of discovered tools
        """
        # TODO: Implement actual discovery from ACP protocol
        # This would scan langchain/protocols/acp.py for ACP tools
        tools = [
            DiscoveredTool(
                name="acp_editor_context",
                source_file="langchain/protocols/acp.py",
                source_system=self.source_system,
                metadata={
                    "description": "ACP editor/client context tool",
                },
            ),
            DiscoveredTool(
                name="acp_repo_access",
                source_file="langchain/protocols/acp.py",
                source_system=self.source_system,
                metadata={
                    "description": "ACP repository/file access tool",
                },
            ),
            DiscoveredTool(
                name="acp_coding_agent",
                source_file="langchain/protocols/acp.py",
                source_system=self.source_system,
                metadata={
                    "description": "ACP coding agent tool",
                },
            ),
        ]
        return tools

    def to_tool_spec(self, discovered: DiscoveredTool) -> ToolSpec:
        """Convert a discovered ACP tool to ToolSpec.

        Args:
            discovered: Discovered tool

        Returns:
            ToolSpec instance
        """
        name = discovered.name
        metadata = discovered.metadata
        description = metadata.get("description", "")

        # ACP tools involve file/repo access and code execution
        # Default to L3 with sandbox requirement
        return ToolSpec.create(
            name=name,
            canonical_name=f"acp.{name}",
            description=description,
            owner="acp",
            category="code",
            version="1.0.0",
            source_system=self.source_system,
            risk_tier=RiskTier.L3,
            approval_mode=ApprovalMode.EXPLICIT,
            sandbox_required=True,
            network_required=True,
            filesystem_required=True,
            side_effects=True,
            idempotent=False,
            enabled=True,
        )

    def bind_executor(self, spec: ToolSpec) -> Any:
        """Bind executor to the tool spec.

        Args:
            spec: ToolSpec

        Returns:
            Executor callable (routes through ACP protocol -> ToolExecutor)
        """
        # ACP tools must route through ACP protocol -> canonical ToolExecutor
        # This returns a wrapper that calls ACP protocol -> ToolExecutor.execute()
        # TODO: Implement actual executor binding
        return None
