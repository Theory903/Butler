"""Tool Adapters - Phase T2.

Convert legacy tool formats into canonical ToolSpec.

Adapters:
- langchain_adapter: LangChain tools to ToolSpec
- mcp_adapter: MCP tools to ToolSpec
- acp_adapter: ACP tools to ToolSpec
- legacy_butler_adapter: Butler runtime tools to ToolSpec
- hermes_adapter: Hermes tools to ToolSpec
- openclaw_skill_adapter: OpenClaw skills to ToolSpec
- service_tool_adapter: Service internal tools to ToolSpec
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domain.tools.spec import ToolSpec


@dataclass(frozen=True)
class DiscoveredTool:
    """A discovered tool from a legacy system."""

    name: str
    source_file: str
    source_system: str
    metadata: dict[str, Any]


class ToolAdapter:
    """Base class for tool adapters.

    Converts legacy tool formats into canonical ToolSpec.
    """

    source_system: str

    def discover(self) -> list[DiscoveredTool]:
        """Discover tools from the legacy system.

        Returns:
            List of discovered tools
        """
        raise NotImplementedError

    def to_tool_spec(self, discovered: DiscoveredTool) -> ToolSpec:
        """Convert a discovered tool to ToolSpec.

        Args:
            discovered: Discovered tool

        Returns:
            ToolSpec instance
        """
        raise NotImplementedError

    def bind_executor(self, spec: ToolSpec) -> Any:
        """Bind an executor to the tool spec.

        Args:
            spec: ToolSpec

        Returns:
            Executor callable
        """
        raise NotImplementedError


# Import all adapter implementations
from domain.tools.adapters.acp_adapter import ACPAdapter
from domain.tools.adapters.hermes_adapter import HermesAdapter
from domain.tools.adapters.langchain_adapter import LangChainAdapter
from domain.tools.adapters.legacy_butler_adapter import LegacyButlerAdapter
from domain.tools.adapters.mcp_adapter import MCPAdapter
from domain.tools.adapters.openclaw_skill_adapter import OpenClawSkillAdapter
from domain.tools.adapters.service_tool_adapter import ServiceToolAdapter

__all__ = [
    "ToolAdapter",
    "DiscoveredTool",
    "ACPAdapter",
    "HermesAdapter",
    "LangChainAdapter",
    "LegacyButlerAdapter",
    "MCPAdapter",
    "OpenClawSkillAdapter",
    "ServiceToolAdapter",
]
