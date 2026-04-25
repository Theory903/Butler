"""OpenClaw Skill Adapter - Phase T2.

Converts OpenClaw skills from skills_library/ into canonical ToolSpec.

OpenClaw skills are 70+ skills from the OpenClaw project.
Each skill may expose one or more tools.
This adapter converts them to Butler's canonical ToolSpec format.
"""

from __future__ import annotations

from typing import Any

from domain.tools.adapters import DiscoveredTool, ToolAdapter
from domain.tools.spec import ApprovalMode, RiskTier, ToolSpec


class OpenClawSkillAdapter(ToolAdapter):
    """Adapter for OpenClaw skills."""

    source_system = "openclaw_skill"

    def discover(self) -> list[DiscoveredTool]:
        """Discover OpenClaw skills.

        Returns:
            List of discovered tools
        """
        # TODO: Implement actual discovery from skills_library/
        # This would scan skills_library/*/SKILL.md for skill definitions
        # For now, return placeholder for the 70+ skills
        tools = [
            DiscoveredTool(
                name="openclaw_skills",
                source_file="skills_library/",
                source_system=self.source_system,
                metadata={
                    "description": "70+ OpenClaw skills from skills_library/",
                    "count": 70,
                    "dynamic": True,
                },
            ),
        ]
        return tools

    def to_tool_spec(self, discovered: DiscoveredTool) -> ToolSpec:
        """Convert a discovered OpenClaw skill to ToolSpec.

        Args:
            discovered: Discovered tool

        Returns:
            ToolSpec instance
        """
        name = discovered.name
        metadata = discovered.metadata
        description = metadata.get("description", "")

        # OpenClaw skills vary in risk based on their actual function
        # Default to L2 with sandbox requirement for safety
        # Individual skills should be classified when discovered
        return ToolSpec.create(
            name=name,
            canonical_name=f"skill.{name}",
            description=description,
            owner="skills",
            category="skills",
            version="1.0.0",
            source_system=self.source_system,
            risk_tier=RiskTier.L2,
            approval_mode=ApprovalMode.IMPLICIT,
            sandbox_required=True,  # Skills should run in sandbox by default
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
            Executor callable (routes through canonical ToolExecutor)
        """
        # OpenClaw skills must route through canonical ToolExecutor
        # This returns a wrapper that calls ToolExecutor.execute()
        # TODO: Implement actual executor binding
        return None
