"""LangChain Tool Adapter - Phase T2.

Converts LangChain tools into canonical ToolSpec.

LangChain tools use BaseTool, StructuredTool, and ToolNode patterns.
This adapter converts them to Butler's canonical ToolSpec format.
"""

from __future__ import annotations

from typing import Any

from domain.tools.adapters import DiscoveredTool, ToolAdapter
from domain.tools.spec import ApprovalMode, RiskTier, ToolSpec


class LangChainAdapter(ToolAdapter):
    """Adapter for LangChain tools."""

    source_system = "langchain_tool"

    def discover(self) -> list[DiscoveredTool]:
        """Discover LangChain tools.

        Returns:
            List of discovered tools
        """
        # TODO: Implement actual discovery from langchain/tools.py
        # This would scan for BaseTool, StructuredTool, and ToolNode instances
        tools = [
            DiscoveredTool(
                name="ButlerLangChainTool",
                source_file="langchain/tools.py",
                source_system=self.source_system,
                metadata={
                    "class": "ButlerLangChainTool",
                    "description": "LangChain tool adapter for ButlerToolSpec with hybrid governance",
                },
            ),
        ]
        return tools

    def to_tool_spec(self, discovered: DiscoveredTool) -> ToolSpec:
        """Convert a discovered LangChain tool to ToolSpec.

        Args:
            discovered: Discovered tool

        Returns:
            ToolSpec instance
        """
        name = discovered.name
        metadata = discovered.metadata
        description = metadata.get("description", "")

        # LangChain tools are adapters, not direct executors
        # They route through canonical ToolExecutor
        return ToolSpec.create(
            name=name,
            canonical_name=f"langchain.{name}",
            description=description,
            owner="langchain",
            category="adapter",
            version="1.0.0",
            source_system=self.source_system,
            risk_tier=RiskTier.L1,
            approval_mode=ApprovalMode.NONE,
            sandbox_required=False,
            network_required=False,
            filesystem_required=False,
            side_effects=False,
            idempotent=True,
            enabled=True,
        )

    def bind_executor(self, spec: ToolSpec) -> Any:
        """Bind executor to the tool spec.

        Args:
            spec: ToolSpec

        Returns:
            Executor callable (routes through canonical ToolExecutor)
        """
        # LangChain tools must route through canonical ToolExecutor
        # This returns a wrapper that calls ToolExecutor.execute()
        # TODO: Implement actual executor binding
        return None
