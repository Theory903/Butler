"""Butler Tool Registry — Phase 11, SOLID edition.

Implements IToolRegistry. Depends on IHermesRegistryAdapter (D).
Single responsibility: bridge Hermes tools into Butler's domain (S).
New tool sources can extend IHermesRegistryAdapter without touching this class (O).
Implements IToolRegistry — fully substitutable (L).
IToolRegistry is a small focused interface — no fat base class (I).

Design:
    ButlerToolRegistry
        └── HermesRegistryAdapter  — wraps raw Hermes singleton
              (isolated; can swap for RemoteRegistryAdapter, MockAdapter, etc.)

Toolset → CapabilityFlag mapping lives HERE (S — single authority on who can use what).
Policy gate lives in domain/policy/ — this file never enforces, only provides capability info.

Usage:
    registry = make_default_tool_registry()
    schemas  = registry.get_schemas()
    result   = await registry.execute("web_search", {"query": "..."})

    # Tests:
    registry = ButlerToolRegistry(MockHermesAdapter())
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

import structlog

logger = structlog.get_logger(__name__)

# ── Toolset → Butler CapabilityFlag (S — single authority) ───────────────────

_TOOLSET_CAPABILITY_MAP: dict[str, str | None] = {
    "web":                "WEB_SEARCH",
    "files":              "FILE_OPS",
    "terminal":           "TERMINAL",
    "browser":            "BROWSER_AUTOMATION",
    "code_execution":     "CODE_EXECUTION",
    "delegate":           "DELEGATE",
    "mcp":                "MCP_ACCESS",
    "vision":             "VISION",
    "voice":              "VOICE",
    "tts":                "VOICE",
    "transcription":      "VOICE",
    "image_gen":          "IMAGE_GENERATION",
    "memory":             "MEMORY_WRITE",
    "todo":               "FILE_OPS",
    "session_search":     "MEMORY_READ",
    "skills":             "SKILLS",
    "homeassistant":      "IOT_CONTROL",
    "cronjob":            "CRON_SCHEDULE",
    "clarify":            None,            # no gate — always allowed
    "rl_training":        "ML_TRAINING",
    "mixture_of_agents":  "DELEGATE",
    "tirith_security":    "SECURITY_SCAN",
    "osv_check":          "SECURITY_SCAN",
}


# ── Adapter Protocol (D — bus depends on this, not on Hermes directly) ────────

class IHermesRegistryAdapter(Protocol):
    """Minimum surface exposed to ButlerToolRegistry from the Hermes side."""

    def discover(self) -> list[str]: ...
    def get_all_tool_names(self) -> list[str]: ...
    def get_definitions(self, names: set[str], quiet: bool) -> list[dict]: ...
    def get_toolset_for_tool(self, name: str) -> str | None: ...
    def get_entry(self, name: str) -> Any | None: ...
    def get_available_toolsets(self) -> dict[str, dict]: ...
    def get_toolset_requirements(self) -> dict[str, dict]: ...
    def get_emoji(self, name: str, default: str) -> str: ...


# ── Concrete adapter (O — swap this without touching ButlerToolRegistry) ──────

class HermesRegistryAdapter:
    """Wraps the raw Hermes ToolRegistry singleton.

    Single responsibility: import + delegate (S).
    Isolated behind IHermesRegistryAdapter — the bus never imports Hermes directly.
    """

    def __init__(self) -> None:
        self._reg = self._import()

    def _import(self) -> Any | None:
        try:
            from integrations.hermes.tools.registry import registry
            return registry
        except ImportError as exc:
            logger.warning("hermes_registry_unavailable", error=str(exc))
            return None

    def _ok(self) -> bool:
        return self._reg is not None

    def discover(self) -> list[str]:
        if not self._ok():
            return []
        try:
            from integrations.hermes.tools.registry import discover_builtin_tools
            result = discover_builtin_tools()
            logger.info("hermes_tools_discovered", count=len(result))
            return result
        except Exception as exc:
            logger.warning("hermes_tool_discovery_failed", error=str(exc))
            return []

    def get_all_tool_names(self) -> list[str]:
        return self._reg.get_all_tool_names() if self._ok() else []

    def get_definitions(self, names: set[str], quiet: bool) -> list[dict]:
        return self._reg.get_definitions(names, quiet=quiet) if self._ok() else []

    def get_toolset_for_tool(self, name: str) -> str | None:
        return self._reg.get_toolset_for_tool(name) if self._ok() else None

    def get_entry(self, name: str) -> Any | None:
        return self._reg.get_entry(name) if self._ok() else None

    def get_available_toolsets(self) -> dict[str, dict]:
        return self._reg.get_available_toolsets() if self._ok() else {}

    def get_toolset_requirements(self) -> dict[str, dict]:
        return self._reg.get_toolset_requirements() if self._ok() else {}

    def get_emoji(self, name: str, default: str = "⚡") -> str:
        return self._reg.get_emoji(name, default=default) if self._ok() else default


# ── ButlerToolRegistry (IToolRegistry, DI-friendly) ───────────────────────────

class ButlerToolRegistry:
    """Butler-owned tool registry.

    Depends on IHermesRegistryAdapter — injected in constructor (D).
    No singleton magic in the class itself — production wiring uses the factory.
    Implements IToolRegistry (L).
    """

    def __init__(self, adapter: IHermesRegistryAdapter) -> None:
        self._adapter   = adapter
        self._discovered = False

    def discover(self) -> list[str]:                 # IToolRegistry
        names = self._adapter.discover()
        self._discovered = True
        return names

    def _ensure_discovered(self) -> None:
        if not self._discovered:
            self.discover()

    def get_schemas(                                 # IToolRegistry
        self,
        toolset_filter: list[str] | None = None,
    ) -> list[dict]:
        self._ensure_discovered()
        all_names: set[str] = set(self._adapter.get_all_tool_names())
        if toolset_filter:
            all_names = {
                n for n in all_names
                if self._adapter.get_toolset_for_tool(n) in toolset_filter
            }
        try:
            return self._adapter.get_definitions(all_names, quiet=True)
        except Exception as exc:
            logger.warning("butler_tool_schemas_failed", error=str(exc))
            return []

    def get_capability_for_tool(self, tool_name: str) -> str | None:  # IToolRegistry
        toolset = self._adapter.get_toolset_for_tool(tool_name)
        if toolset is None:
            return None
        return _TOOLSET_CAPABILITY_MAP.get(toolset)

    async def execute(                               # IToolRegistry
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> str:
        import json
        entry = self._adapter.get_entry(tool_name)
        if entry is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        try:
            if entry.is_async:
                result = await entry.handler(args)
            else:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, entry.handler, args)
            return result if isinstance(result, str) else str(result)
        except Exception as exc:
            logger.warning("butler_tool_execute_failed", tool=tool_name, error=str(exc))
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

    def tool_names(self) -> list[str]:               # IToolRegistry
        self._ensure_discovered()
        return self._adapter.get_all_tool_names()

    def is_available(self) -> bool:                  # IToolRegistry
        return self._adapter.get_entry is not None

    # Extra helpers (not in IToolRegistry — extension methods)
    def get_toolset_map(self) -> dict[str, str]:
        self._ensure_discovered()
        return {
            n: self._adapter.get_toolset_for_tool(n) or "unknown"
            for n in self._adapter.get_all_tool_names()
        }

    def get_available_toolsets(self) -> dict[str, dict]:
        return self._adapter.get_available_toolsets()

    def get_toolset_requirements(self) -> dict[str, dict]:
        return self._adapter.get_toolset_requirements()

    def get_emoji(self, tool_name: str) -> str:
        return self._adapter.get_emoji(tool_name, "⚡")

    def capability_map(self) -> dict[str, str | None]:
        """Return {toolset: capability_flag} for introspection."""
        return dict(_TOOLSET_CAPABILITY_MAP)


# ── Default factory ───────────────────────────────────────────────────────────

def make_default_tool_registry() -> ButlerToolRegistry:
    """Production: wraps Hermes registry via the concrete adapter."""
    return ButlerToolRegistry(adapter=HermesRegistryAdapter())
