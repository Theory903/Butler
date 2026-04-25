"""Service Tool Adapter - Phase T2.

Converts internal service capabilities into canonical ToolSpec.

Service tools are internal Butler services exposed as tools:
- search
- memory
- calendar
- communication
- files
- workspace
- code
- browser
- device
- vision
- audio
- research
- meetings
- ml
- security
- tenant
- admin
- billing

This adapter converts them to Butler's canonical ToolSpec format.
"""

from __future__ import annotations

from typing import Any

from domain.tools.adapters import DiscoveredTool, ToolAdapter
from domain.tools.spec import ApprovalMode, RiskTier, ToolSpec


class ServiceToolAdapter(ToolAdapter):
    """Adapter for internal service tools."""

    source_system = "service_internal_tool"

    def discover(self) -> list[DiscoveredTool]:
        """Discover service tools.

        Returns:
            List of discovered tools
        """
        # TODO: Implement actual discovery from services/ directory
        # This would scan services/ for service capabilities that can be exposed as tools
        tools = [
            DiscoveredTool(
                name="search.web",
                source_file="services/search/",
                source_system=self.source_system,
                metadata={
                    "description": "Web search service",
                    "category": "search",
                },
            ),
            DiscoveredTool(
                name="memory.read",
                source_file="services/memory/",
                source_system=self.source_system,
                metadata={
                    "description": "Read from memory service",
                    "category": "memory",
                },
            ),
            DiscoveredTool(
                name="memory.propose_write",
                source_file="services/memory/",
                source_system=self.source_system,
                metadata={
                    "description": "Propose memory write",
                    "category": "memory",
                },
            ),
            DiscoveredTool(
                name="calendar.create_event",
                source_file="services/calendar/",
                source_system=self.source_system,
                metadata={
                    "description": "Create calendar event",
                    "category": "calendar",
                },
            ),
            DiscoveredTool(
                name="communication.send_email",
                source_file="services/communication/",
                source_system=self.source_system,
                metadata={
                    "description": "Send email",
                    "category": "communication",
                },
            ),
        ]
        return tools

    def to_tool_spec(self, discovered: DiscoveredTool) -> ToolSpec:
        """Convert a discovered service tool to ToolSpec.

        Args:
            discovered: Discovered tool

        Returns:
            ToolSpec instance
        """
        name = discovered.name
        metadata = discovered.metadata
        description = metadata.get("description", "")
        category = metadata.get("category", "general")

        # Determine risk tier based on category
        if category in ["search", "memory"]:
            # L1: read operations
            return ToolSpec.l1_readonly(
                name=name,
                canonical_name=f"service.{name}",
                description=description,
                owner=category,
                category=category,
            )
        elif category in ["calendar", "communication"]:
            # L2: write/communication operations
            return ToolSpec.l2_write(
                name=name,
                canonical_name=f"service.{name}",
                description=description,
                owner=category,
                category=category,
                required_permissions=frozenset([f"{category}:write"]),
                approval_mode=ApprovalMode.IMPLICIT,
            )
        elif category in ["code", "browser", "device"]:
            # L3: code execution, device control
            return ToolSpec.l3_destructive(
                name=name,
                canonical_name=f"service.{name}",
                description=description,
                owner=category,
                category=category,
                required_permissions=frozenset([f"{category}:execute"]),
            )
        else:
            # Default to L1 for unknown categories
            return ToolSpec.l1_readonly(
                name=name,
                canonical_name=f"service.{name}",
                description=description,
                owner=category,
                category=category,
            )

    def bind_executor(self, spec: ToolSpec) -> Any:
        """Bind executor to the tool spec.

        Args:
            spec: ToolSpec

        Returns:
            Executor callable (routes through service -> ToolExecutor)
        """
        # Service tools must route through canonical ToolExecutor
        # This returns a wrapper that calls the service method -> ToolExecutor.execute()
        # TODO: Implement actual executor binding
        return None
