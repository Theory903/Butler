"""
Butler-owned Hermes tool registry.

This registry stores normalized tool specifications for Hermes implementations
that have been safely imported into Butler. It does not expose Hermes' raw registry
as production truth - Hermes is treated as an implementation library only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

HermesCallable = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class HermesImplementationSpec:
    """Normalized specification for a Hermes tool implementation."""

    name: str
    description: str
    implementation: HermesCallable
    args_schema: type | None = None
    source_file: str | None = None
    risk_tier: int = 1
    tags: tuple[str, ...] = field(default_factory=tuple)
    supports_async: bool = False
    requires_env: bool = False
    requires_filesystem: bool = False
    requires_network: bool = False


class ButlerHermesRegistry:
    """Butler-owned registry for Hermes tool implementations.

    This registry is the single source of truth for Hermes tools in Butler.
    It may import Hermes implementations, but it must not expose Hermes' raw
    registry as production truth.
    """

    def __init__(self) -> None:
        self._specs: dict[str, HermesImplementationSpec] = {}

    def register(self, spec: HermesImplementationSpec) -> None:
        """Register a Hermes tool implementation."""
        self._specs[spec.name] = spec

    def get(self, name: str) -> HermesImplementationSpec | None:
        """Get a tool specification by name."""
        return self._specs.get(name)

    def list(self) -> list[HermesImplementationSpec]:
        """List all registered tool specifications."""
        return list(self._specs.values())

    def get_by_tag(self, tag: str) -> list[HermesImplementationSpec]:
        """Get all tools with a specific tag."""
        return [spec for spec in self._specs.values() if tag in spec.tags]

    def get_by_risk_tier(self, tier: int) -> list[HermesImplementationSpec]:
        """Get all tools with a specific risk tier."""
        return [spec for spec in self._specs.values() if spec.risk_tier == tier]

    def clear(self) -> None:
        """Clear all registered specifications."""
        self._specs.clear()

    def deregister(self, name: str) -> bool:
        """Remove a tool specification by name."""
        if name in self._specs:
            del self._specs[name]
            return True
        return False


# Global registry instance
_butler_hermes_registry = ButlerHermesRegistry()


def get_butler_hermes_registry() -> ButlerHermesRegistry:
    """Get the global Butler-owned Hermes registry instance."""
    return _butler_hermes_registry
