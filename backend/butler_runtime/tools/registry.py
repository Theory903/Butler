"""Unified Tool Registry for Butler Runtime.

Fuses Hermes tool discovery with Butler's governance layer.
"""

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class ButlerToolSpec:
    """Butler tool specification.

    Represents a tool in Butler's unified registry with governance metadata.
    """

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        category: str = "general",
        risk_tier: str = "low",
        source: str = "butler",
        implementation: Callable[..., Any] | None = None,
        requires_approval: bool = False,
        enabled: bool = True,
    ) -> None:
        """Initialize Butler tool specification.

        Args:
            name: Tool name
            description: Tool description
            parameters: JSON Schema for parameters
            category: Tool category (file, web, memory, etc.)
            risk_tier: Risk tier (low, medium, high, critical)
            source: Tool source (butler, hermes, user)
            implementation: Tool implementation function
            requires_approval: Whether tool requires approval
            enabled: Whether tool is enabled
        """
        self.name = name
        self.description = description
        self.parameters = parameters
        self.category = category
        self.risk_tier = risk_tier
        self.source = source
        self.implementation = implementation
        self.requires_approval = requires_approval
        self.enabled = enabled

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "category": self.category,
            "risk_tier": self.risk_tier,
            "source": self.source,
            "requires_approval": self.requires_approval,
            "enabled": self.enabled,
        }


class UnifiedToolRegistry:
    """Unified tool registry for Butler.

    This registry replaces Hermes' separate tool registry with a Butler-native
    implementation that supports both Butler tools and Hermes-derived tools.
    """

    def __init__(self) -> None:
        """Initialize unified tool registry."""
        self._tools: dict[str, ButlerToolSpec] = {}
        self._toolsets: dict[str, list[str]] = {}

    def register(
        self,
        spec: ButlerToolSpec,
        implementation: Callable[..., Any] | None = None,
    ) -> None:
        """Register a tool in the unified registry.

        Args:
            spec: Butler tool specification
            implementation: Optional implementation function (overrides spec.implementation)
        """
        if implementation:
            spec.implementation = implementation

        self._tools[spec.name] = spec

        # Add to toolset
        if spec.category not in self._toolsets:
            self._toolsets[spec.category] = []
        if spec.name not in self._toolsets[spec.category]:
            self._toolsets[spec.category].append(spec.name)

        logger.debug(f"Registered tool: {spec.name} (category: {spec.category})")

    def register_hermes_tool(
        self,
        hermes_name: str,
        hermes_schema: dict[str, Any],
        implementation: Callable[..., Any],
        category: str = "hermes",
        risk_tier: str = "medium",
    ) -> None:
        """Register a Hermes-derived tool in Butler registry.

        Args:
            hermes_name: Original Hermes tool name
            hermes_schema: Hermes tool schema
            implementation: Tool implementation function
            category: Tool category
            risk_tier: Risk tier (Hermes tools default to medium)
        """
        # Convert Hermes schema to Butler spec
        spec = ButlerToolSpec(
            name=hermes_name,
            description=hermes_schema.get("description", ""),
            parameters=hermes_schema.get("parameters", {}),
            category=category,
            risk_tier=risk_tier,
            source="hermes",
            implementation=implementation,
        )

        self.register(spec)

    def get(self, name: str) -> ButlerToolSpec | None:
        """Get a tool specification by name.

        Args:
            name: Tool name

        Returns:
            Tool specification or None if not found
        """
        return self._tools.get(name)

    def get_all(self) -> dict[str, ButlerToolSpec]:
        """Get all registered tools.

        Returns:
            Dictionary of all tool specifications
        """
        return self._tools.copy()

    def get_by_category(self, category: str) -> list[ButlerToolSpec]:
        """Get all tools in a category.

        Args:
            category: Tool category

        Returns:
            List of tool specifications
        """
        return [
            self._tools[name] for name in self._toolsets.get(category, []) if name in self._tools
        ]

    def get_by_source(self, source: str) -> list[ButlerToolSpec]:
        """Get all tools from a source.

        Args:
            source: Tool source (butler, hermes, user)

        Returns:
            List of tool specifications
        """
        return [spec for spec in self._tools.values() if spec.source == source]

    def get_enabled(self) -> dict[str, ButlerToolSpec]:
        """Get all enabled tools.

        Returns:
            Dictionary of enabled tool specifications
        """
        return {name: spec for name, spec in self._tools.items() if spec.enabled}

    def get_visible(
        self,
        account_tier: str = "free",
        channel: str = "api",
        risk_tier_limit: str = "critical",
    ) -> list[ButlerToolSpec]:
        """Get visible tools for a context.

        Args:
            account_tier: Account tier (free, pro, enterprise)
            channel: Channel (api, cli, telegram, etc.)
            risk_tier_limit: Maximum risk tier to show

        Returns:
            List of visible tool specifications
        """
        risk_hierarchy = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        limit_level = risk_hierarchy.get(risk_tier_limit, 3)

        visible = []
        for spec in self._tools.values():
            if not spec.enabled:
                continue

            # Risk tier check
            spec_level = risk_hierarchy.get(spec.risk_tier, 1)
            if spec_level > limit_level:
                continue

            visible.append(spec)

        return visible

    def to_schemas(self, tools: list[ButlerToolSpec] | None = None) -> list[dict[str, Any]]:
        """Convert tools to OpenAI-style function schemas.

        Args:
            tools: Optional list of tools (defaults to all enabled)

        Returns:
            List of function schemas
        """
        if tools is None:
            tools = list(self.get_enabled().values())

        schemas = []
        for spec in tools:
            schema = {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
            schemas.append(schema)

        return schemas

    def enable(self, name: str) -> bool:
        """Enable a tool.

        Args:
            name: Tool name

        Returns:
            True if tool was enabled, False if not found
        """
        if name in self._tools:
            self._tools[name].enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        """Disable a tool.

        Args:
            name: Tool name

        Returns:
            True if tool was disabled, False if not found
        """
        if name in self._tools:
            self._tools[name].enabled = False
            return True
        return False

    def unregister(self, name: str) -> bool:
        """Unregister a tool.

        Args:
            name: Tool name

        Returns:
            True if tool was unregistered, False if not found
        """
        if name in self._tools:
            spec = self._tools[name]
            del self._tools[name]

            # Remove from toolset
            if spec.category in self._toolsets:
                self._toolsets[spec.category] = [
                    n for n in self._toolsets[spec.category] if n != name
                ]

            return True
        return False

    def __len__(self) -> int:
        """Return number of registered tools."""
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        """Check if tool is registered."""
        return name in self._tools

    def __repr__(self) -> str:
        return f"UnifiedToolRegistry(tools={len(self._tools)}, toolsets={len(self._toolsets)})"
