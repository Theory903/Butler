"""Butler Runtime LangChain Tools.

Provides LangChain-compatible tool wrappers for Butler's unified tool registry.
"""

import logging
from typing import Any

from ..tools.registry import UnifiedToolRegistry

import structlog

logger = structlog.get_logger(__name__)


class ButlerLangChainTools:
    """LangChain-compatible tool adapter for Butler tools.

    Converts Butler tool specifications to LangChain StructuredTool format.
    """

    def __init__(self, registry: UnifiedToolRegistry) -> None:
        """Initialize LangChain tools adapter.

        Args:
            registry: Butler UnifiedToolRegistry instance
        """
        self._registry = registry

    def to_langchain_tools(
        self,
        tool_names: list[str] | None = None,
        risk_tier_limit: str = "critical",
    ) -> list[Any]:
        """Convert Butler tools to LangChain StructuredTool format.

        Args:
            tool_names: Optional list of tool names to convert (defaults to all visible)
            risk_tier_limit: Maximum risk tier to include

        Returns:
            List of LangChain StructuredTool instances

        Note:
            This is a stub. Real implementation would use LangChain's
            StructuredTool class to wrap Butler tool implementations.
        """
        # Get visible tools
        if tool_names:
            tools = [self._registry.get(name) for name in tool_names if self._registry.get(name)]
        else:
            tools = self._registry.get_visible(risk_tier_limit=risk_tier_limit)

        # Convert to LangChain format (stub implementation)
        langchain_tools = []
        for tool_spec in tools:
            if not tool_spec or not tool_spec.implementation:
                continue

            # Stub: In production, create actual LangChain StructuredTool
            langchain_tool = {
                "name": tool_spec.name,
                "description": tool_spec.description,
                "parameters": tool_spec.parameters,
                "implementation": tool_spec.implementation,
            }
            langchain_tools.append(langchain_tool)

        logger.debug(f"Converted {len(langchain_tools)} Butler tools to LangChain format")
        return langchain_tools

    def get_tool_schemas(self, tool_names: list[str] | None = None) -> list[dict[str, Any]]:
        """Get tool schemas for LangChain.

        Args:
            tool_names: Optional list of tool names

        Returns:
            List of tool schemas in LangChain format
        """
        if tool_names:
            tools = [self._registry.get(name) for name in tool_names if self._registry.get(name)]
        else:
            tools = list(self._registry.get_enabled().values())

        # Filter out None values and convert to schemas
        valid_tools = [t for t in tools if t is not None]
        return self._registry.to_schemas(valid_tools)
