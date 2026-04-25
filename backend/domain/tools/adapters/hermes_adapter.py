"""Hermes Tool Adapter - Phase T2.

Converts Hermes legacy tools from integrations/hermes/ into canonical ToolSpec.

Hermes tools are the original tool system from the Hermes agent.
This adapter converts them to Butler's canonical ToolSpec format.
"""

from __future__ import annotations

from typing import Any

from domain.tools.adapters import DiscoveredTool, ToolAdapter
from domain.tools.spec import ApprovalMode, RiskTier, ToolSpec


class HermesAdapter(ToolAdapter):
    """Adapter for Hermes legacy tools."""

    source_system = "hermes_legacy"

    def discover(self) -> list[DiscoveredTool]:
        """Discover Hermes tools.

        Returns:
            List of discovered tools
        """
        # TODO: Implement actual discovery from integrations/hermes/tools/
        # This would scan integrations/hermes/tools/ for Hermes tool definitions
        tools = [
            DiscoveredTool(
                name="docker_environment",
                source_file="integrations/hermes/tools/environments/docker.py",
                source_system=self.source_system,
                metadata={
                    "description": "Docker environment for Hermes tools",
                },
            ),
        ]
        return tools

    def to_tool_spec(self, discovered: DiscoveredTool) -> ToolSpec:
        """Convert a discovered Hermes tool to ToolSpec.

        Args:
            discovered: Discovered tool

        Returns:
            ToolSpec instance
        """
        name = discovered.name
        metadata = discovered.metadata
        description = metadata.get("description", "")

        # Hermes tools vary in risk based on their actual function
        # Docker environment is L3 (sandbox/container)
        return ToolSpec.create(
            name=name,
            canonical_name=f"hermes.{name}",
            description=description,
            owner="hermes",
            category="environment",
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
            Executor callable (routes through canonical ToolExecutor)
        """
        # Hermes tools must route through canonical ToolExecutor
        # This returns a wrapper that calls ToolExecutor.execute()
        # TODO: Implement actual executor binding
        return None
