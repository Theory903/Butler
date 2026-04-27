"""Canonical tool registry for Butler runtime.

This is the single source of truth for tool registration and lookup.
All tool execution flows through this registry.
"""

from __future__ import annotations

from typing import Any

from domain.tools.specs import (
    GET_TIME_SPEC,
    KAG_QUERY_SPEC,
    RAG_RETRIEVE_SPEC,
    USER_CONTEXT_PROBE_SPEC,
    ButlerToolSpec,
    RiskTier,
)


class ToolRegistryError(Exception):
    """Base exception for tool registry errors."""


class GhostToolError(ToolRegistryError):
    """Tool visible but missing direct implementation."""


class DuplicateToolError(ToolRegistryError):
    """Tool name already registered."""


class SchemaValidationError(ToolRegistryError):
    """Tool input/output schema validation failed."""


class ToolRegistry:
    """Canonical tool registry.

    Invariants enforced at startup:
    - No L0/L1 tool visible unless a direct implementation exists.
    - No L2/L3 tool executable unless an approval/sandbox policy exists.
    - No tool can execute without schema validation.
    - No model-visible tool can be missing from ToolRegistry.
    - No duplicate tool names.
    - No ghost tools (visible without implementation).

    Note: ``ButlerToolSpec`` must declare ``model_visible: bool = True``
    for ``is_visible()`` to work correctly.  Until that field is added,
    ``is_visible()`` uses ``getattr(..., 'model_visible', True)`` as a
    safe fallback.
    """

    def __init__(self) -> None:
        self._specs: dict[str, ButlerToolSpec] = {}
        self._implementations: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, spec: ButlerToolSpec, implementation: Any | None = None) -> None:
        """Register a tool with its specification and optional direct implementation."""
        if spec.name in self._specs:
            raise DuplicateToolError(f"Tool '{spec.name}' already registered")

        self._specs[spec.name] = spec
        if implementation is not None:
            self._implementations[spec.name] = implementation

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_spec(self, name: str) -> ButlerToolSpec | None:
        return self._specs.get(name)

    def get_implementation(self, name: str) -> Any | None:
        return self._implementations.get(name)

    def is_visible(self, name: str) -> bool:
        """Return True if the tool is enabled and model-visible."""
        spec = self.get_spec(name)
        if spec is None:
            return False
        # ButlerToolSpec should declare `model_visible: bool = True`.
        # Use getattr as a safe fallback until that field is added.
        return spec.enabled and getattr(spec, "model_visible", True)

    def is_executable(self, name: str) -> bool:
        """Return True if the tool is enabled and has a direct implementation."""
        spec = self.get_spec(name)
        if spec is None or not spec.enabled:
            return False
        return spec.binding_ref in self._implementations

    def visible_tools(self, max_tools: int | None = None) -> list[ButlerToolSpec]:
        """Return all model-visible tools, optionally capped at ``max_tools``."""
        visible = [s for s in self._specs.values() if self.is_visible(s.name)]
        if max_tools is not None and len(visible) > max_tools:
            visible.sort(key=lambda s: s.risk_tier.value)
            visible = visible[:max_tools]
        return visible

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_input(self, name: str, input_data: dict[str, Any]) -> None:
        """Validate tool input against the spec's input schema."""
        spec = self.get_spec(name)
        if spec is None:
            raise ToolRegistryError(f"Tool '{name}' not found")

        try:
            required: list[str] = spec.input_schema.get("required", [])
            properties: dict[str, Any] = spec.input_schema.get("properties", {})
            for field in required:
                if field not in input_data:
                    raise SchemaValidationError(f"Missing required field: '{field}'")
            for key in input_data:
                if key not in properties:
                    raise SchemaValidationError(f"Unexpected field: '{key}'")
        except SchemaValidationError:
            raise
        except Exception as exc:
            raise SchemaValidationError(
                f"Input validation failed for '{name}': {exc}"
            ) from exc

    def validate_output(self, name: str, output_data: dict[str, Any]) -> None:
        """Validate tool output against the spec's output schema."""
        spec = self.get_spec(name)
        if spec is None:
            raise ToolRegistryError(f"Tool '{name}' not found")

        try:
            required: list[str] = spec.output_schema.get("required", [])
            for field in required:
                if field not in output_data:
                    raise SchemaValidationError(f"Missing required output field: '{field}'")
        except SchemaValidationError:
            raise
        except Exception as exc:
            raise SchemaValidationError(
                f"Output validation failed for '{name}': {exc}"
            ) from exc

    def validate_invariants(self) -> list[str]:
        """Validate all registry invariants.

        Returns:
            List of error messages.  An empty list means all invariants pass.
        """
        errors: list[str] = []

        for spec in self._specs.values():
            if not (spec.enabled and getattr(spec, "model_visible", True)):
                continue

            # Ghost-tool check: L0/L1 visible without implementation.
            if spec.risk_tier in (RiskTier.L0, RiskTier.L1):
                if spec.binding_ref not in self._implementations:
                    errors.append(
                        f"Ghost tool: '{spec.name}' is {spec.risk_tier} and visible "
                        f"but has no direct implementation"
                    )

        for spec in self._specs.values():
            if not (spec.enabled and self.is_executable(spec.name)):
                continue

            # Risk-policy check: L2/L3 executable without governance.
            if spec.risk_tier in (RiskTier.L2, RiskTier.L3):
                if spec.approval_mode in (None, "none"):
                    errors.append(
                        f"Risk violation: '{spec.name}' is {spec.risk_tier} executable "
                        f"but has no approval mode"
                    )
                if not getattr(spec, "sandbox_required", False):
                    errors.append(
                        f"Risk violation: '{spec.name}' is {spec.risk_tier} executable "
                        f"but has no sandbox requirement"
                    )

        return errors

    def get_all_specs(self) -> dict[str, ButlerToolSpec]:
        return self._specs.copy()


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_global_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """Return the process-wide ``ToolRegistry`` singleton.

    Initialisation is deferred to first access and happens exactly once.
    ``_initialize_default_registry`` receives the registry instance explicitly
    to prevent the re-entrant call that existed in the original code.
    """
    global _global_registry
    if _global_registry is None:
        registry = ToolRegistry()
        _initialize_default_registry(registry)
        # Assign after initialization is complete so concurrent (sync) callers
        # that race here don't see a half-initialized registry.
        _global_registry = registry
    return _global_registry


def _initialize_default_registry(registry: ToolRegistry) -> None:
    """Populate *registry* with built-in tools.

    Called exactly once from ``get_tool_registry()``.  Accepts the registry
    instance as an argument to avoid the circular ``get_tool_registry()``
    call that existed in the original implementation.
    """
    from langchain.butler_direct_tools import get_time_tool

    registry.register(GET_TIME_SPEC, get_time_tool)

    from services.context.user_context_probe import UserContextProbe

    async def user_context_probe_impl(input_data: dict[str, Any]) -> dict[str, Any]:
        probe = UserContextProbe()
        consent_granted = bool(input_data.get("consent_granted", False))
        snapshot = probe.collect(input_data, consent_granted=consent_granted)
        if snapshot.trust_score >= 80:
            trust_level = "high"
        elif snapshot.trust_score >= 50:
            trust_level = "medium"
        else:
            trust_level = "low"
        return {
            "platform": snapshot.platform,
            "browser": snapshot.browser,
            "language": snapshot.language,
            "timezone": snapshot.timezone,
            "trust_level": trust_level,
            "consent_state": snapshot.consent_state.value,
        }

    registry.register(USER_CONTEXT_PROBE_SPEC, user_context_probe_impl)

    # RAG/KAG tools registered without implementations — blocked until ready.
    registry.register(RAG_RETRIEVE_SPEC)
    registry.register(KAG_QUERY_SPEC)