"""Legacy Butler Runtime Tool Adapter - Phase T2.

Converts Butler runtime tools from butler_runtime/hermes/tools/ into canonical ToolSpec.

Tools to adapt:
- ButlerHermesUtilityTools: fuzzy_find_and_replace, strip_ansi, is_safe_url, check_package_for_malware
- ButlerHermesWebTools: web_search, web_extract
- ButlerHermesFileTools: read_file, write_file, list_files, search_files
- ButlerMemoryTools: memory_search, memory_store, memory_update_preference, memory_forget, memory_context
"""

from __future__ import annotations

from typing import Any

from domain.tools.adapters import DiscoveredTool, ToolAdapter
from domain.tools.spec import ApprovalMode, RiskTier, ToolSpec


class LegacyButlerAdapter(ToolAdapter):
    """Adapter for Butler runtime legacy tools."""

    source_system = "butler_runtime_legacy"

    def discover(self) -> list[DiscoveredTool]:
        """Discover Butler runtime tools.

        Returns:
            List of discovered tools
        """
        tools = [
            # Utility tools
            DiscoveredTool(
                name="fuzzy_find_and_replace",
                source_file="butler_runtime/hermes/tools/utility.py",
                source_system=self.source_system,
                metadata={
                    "class": "ButlerHermesUtilityTools",
                    "description": "Find and replace text using multiple strategies",
                },
            ),
            DiscoveredTool(
                name="strip_ansi",
                source_file="butler_runtime/hermes/tools/utility.py",
                source_system=self.source_system,
                metadata={
                    "class": "ButlerHermesUtilityTools",
                    "description": "Remove ANSI escape sequences from text",
                },
            ),
            DiscoveredTool(
                name="is_safe_url",
                source_file="butler_runtime/hermes/tools/utility.py",
                source_system=self.source_system,
                metadata={
                    "class": "ButlerHermesUtilityTools",
                    "description": "Check if a URL is safe (SSRF protection)",
                },
            ),
            DiscoveredTool(
                name="check_package_for_malware",
                source_file="butler_runtime/hermes/tools/utility.py",
                source_system=self.source_system,
                metadata={
                    "class": "ButlerHermesUtilityTools",
                    "description": "Check a package for malware using OSV API",
                },
            ),
            # Web tools
            DiscoveredTool(
                name="web_search",
                source_file="butler_runtime/hermes/tools/web.py",
                source_system=self.source_system,
                metadata={
                    "class": "ButlerHermesWebTools",
                    "description": "Search the web for information",
                },
            ),
            DiscoveredTool(
                name="web_extract",
                source_file="butler_runtime/hermes/tools/web.py",
                source_system=self.source_system,
                metadata={
                    "class": "ButlerHermesWebTools",
                    "description": "Extract content from a URL",
                },
            ),
            # File tools
            DiscoveredTool(
                name="read_file",
                source_file="butler_runtime/hermes/tools/file.py",
                source_system=self.source_system,
                metadata={
                    "class": "ButlerHermesFileTools",
                    "description": "Read file contents",
                },
            ),
            DiscoveredTool(
                name="write_file",
                source_file="butler_runtime/hermes/tools/file.py",
                source_system=self.source_system,
                metadata={
                    "class": "ButlerHermesFileTools",
                    "description": "Write content to a file",
                },
            ),
            DiscoveredTool(
                name="list_files",
                source_file="butler_runtime/hermes/tools/file.py",
                source_system=self.source_system,
                metadata={
                    "class": "ButlerHermesFileTools",
                    "description": "List directory contents",
                },
            ),
            DiscoveredTool(
                name="search_files",
                source_file="butler_runtime/hermes/tools/file.py",
                source_system=self.source_system,
                metadata={
                    "class": "ButlerHermesFileTools",
                    "description": "Search files by pattern",
                },
            ),
            # Memory tools
            DiscoveredTool(
                name="memory_search",
                source_file="butler_runtime/hermes/tools/memory.py",
                source_system=self.source_system,
                metadata={
                    "class": "ButlerMemoryTools",
                    "description": "Search memory for relevant information",
                },
            ),
            DiscoveredTool(
                name="memory_store",
                source_file="butler_runtime/hermes/tools/memory.py",
                source_system=self.source_system,
                metadata={
                    "class": "ButlerMemoryTools",
                    "description": "Store information in memory",
                },
            ),
            DiscoveredTool(
                name="memory_update_preference",
                source_file="butler_runtime/hermes/tools/memory.py",
                source_system=self.source_system,
                metadata={
                    "class": "ButlerMemoryTools",
                    "description": "Update user preference in memory",
                },
            ),
            DiscoveredTool(
                name="memory_forget",
                source_file="butler_runtime/hermes/tools/memory.py",
                source_system=self.source_system,
                metadata={
                    "class": "ButlerMemoryTools",
                    "description": "Forget information from memory",
                },
            ),
            DiscoveredTool(
                name="memory_context",
                source_file="butler_runtime/hermes/tools/memory.py",
                source_system=self.source_system,
                metadata={
                    "class": "ButlerMemoryTools",
                    "description": "Get memory context for a session",
                },
            ),
        ]
        return tools

    def to_tool_spec(self, discovered: DiscoveredTool) -> ToolSpec:
        """Convert a discovered Butler runtime tool to ToolSpec.

        Args:
            discovered: Discovered tool

        Returns:
            ToolSpec instance
        """
        name = discovered.name
        metadata = discovered.metadata
        description = metadata.get("description", "")

        # Determine risk tier based on tool name
        if name in ["fuzzy_find_and_replace", "strip_ansi", "is_safe_url"]:
            # L0: pure computation, no external calls
            return ToolSpec.l0_safe(
                name=name,
                canonical_name=f"butler.{name}",
                description=description,
                owner="tools",
                category="utility",
            )
        elif name in ["check_package_for_malware", "web_search", "web_extract"]:
            # L1: external API calls, read-only
            return ToolSpec.l1_readonly(
                name=name,
                canonical_name=f"butler.{name}",
                description=description,
                owner="tools",
                category="web" if "web" in name else "utility",
            )
        elif name in ["read_file", "list_files", "search_files", "memory_search", "memory_context"]:
            # L2: read operations with potential side effects
            return ToolSpec.l2_write(
                name=name,
                canonical_name=f"butler.{name}",
                description=description,
                owner="tools",
                category="file" if "file" in name else "memory",
                approval_mode=ApprovalMode.IMPLICIT,
            )
        elif name in ["write_file", "memory_store", "memory_update_preference", "memory_forget"]:
            # L2: write operations
            return ToolSpec.l2_write(
                name=name,
                canonical_name=f"butler.{name}",
                description=description,
                owner="tools",
                category="file" if "file" in name else "memory",
                approval_mode=ApprovalMode.IMPLICIT,
                required_permissions=frozenset(["file:write"] if "file" in name else ["memory:write"]),
            )
        else:
            # Default to L1 for unknown tools, mark as disabled until classified
            return ToolSpec.create(
                name=name,
                canonical_name=f"butler.{name}",
                description=description,
                owner="tools",
                category="utility",
                risk_tier=RiskTier.L1,
                approval_mode=ApprovalMode.NONE,
                enabled=False,
            )

    def bind_executor(self, spec: ToolSpec) -> Any:
        """Bind executor to the tool spec.

        Args:
            spec: ToolSpec

        Returns:
            Executor callable (placeholder for now)
        """
        # TODO: Implement actual executor binding
        # This would load the actual implementation from butler_runtime/hermes/tools/
        return None
