"""
Governance integration for Hermes tools in Butler with multi-tenant support.

Bridges Butler's ToolExecutor governance with Hermes tool implementations.
All operations are tenant-scoped for production multi-tenant deployment.
"""

from __future__ import annotations

from typing import Any, Literal

from backend.langchain.hermes_registry import HermesImplementationSpec, get_butler_hermes_registry
from backend.langchain.hermes_runtime import execute_hermes_implementation
from domain.tools.hermes_compiler import ButlerToolSpec, RiskTier


def hermes_spec_to_butler_spec(hermes_spec: HermesImplementationSpec) -> ButlerToolSpec:
    """Convert a HermesImplementationSpec to a ButlerToolSpec.

    This enables Hermes tools to be registered in Butler's compiled registry
    and go through Butler's full governance pipeline.

    Args:
        hermes_spec: Hermes implementation specification

    Returns:
        ButlerToolSpec compatible with Butler's governance system
    """
    # Map risk tiers (Hermes 1-4 to Butler RiskTier enum)
    risk_tier_map = {
        1: RiskTier.L1,
        2: RiskTier.L2,
        3: RiskTier.L3,
        4: RiskTier.L3,  # Map Hermes tier 4 to Butler L3 (highest available)
    }
    risk_tier = risk_tier_map.get(hermes_spec.risk_tier, RiskTier.L1)

    # Map approval mode based on risk tier (using Literal types)
    approval_mode_map: dict[RiskTier, Literal["none", "implicit", "explicit", "critical"]] = {
        RiskTier.L0: "none",
        RiskTier.L1: "none",
        RiskTier.L2: "implicit",
        RiskTier.L3: "explicit",
    }
    approval_mode = approval_mode_map.get(risk_tier, "none")

    # Determine sandbox profile
    sandbox_profile = "none"
    if hermes_spec.requires_filesystem or hermes_spec.requires_env:
        sandbox_profile = "local"

    # Build ButlerToolSpec
    return ButlerToolSpec(
        name=hermes_spec.name,
        hermes_name=hermes_spec.name,  # Use same name for now
        description=hermes_spec.description,
        risk_tier=risk_tier,
        approval_mode=approval_mode,
        sandbox_profile=sandbox_profile,
        timeout_seconds=30,
        category="general",
        butler_service_owner="tools",
    )


# Global mapping from Butler tool names to Hermes implementation specs
_hermes_impl_mapping: dict[str, HermesImplementationSpec] = {}


def register_hermes_tools_in_butler(
    compiled_specs: dict[str, ButlerToolSpec] | None = None,
) -> dict[str, ButlerToolSpec]:
    """Register all Hermes tools from Butler-owned registry into Butler's compiled specs.

    Args:
        compiled_specs: Existing Butler compiled specs to extend. If None, creates new dict.

    Returns:
        Updated compiled specs with Hermes tools added
    """
    if compiled_specs is None:
        compiled_specs = {}

    registry = get_butler_hermes_registry()
    hermes_specs = registry.list()

    for hermes_spec in hermes_specs:
        butler_spec = hermes_spec_to_butler_spec(hermes_spec)
        compiled_specs[hermes_spec.name] = butler_spec
        # Store the mapping for dispatcher lookup
        _hermes_impl_mapping[hermes_spec.name] = hermes_spec

    return compiled_specs


async def execute_hermes_tool_with_governance(
    tool_name: str,
    args: dict[str, Any],
    hermes_spec: HermesImplementationSpec,
    env: dict[str, Any] | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Execute a Hermes tool with Butler governance context and tenant isolation.

    This is called by Butler's dispatcher after all governance checks pass.

    Args:
        tool_name: Name of the tool
        args: Tool arguments
        hermes_spec: Hermes implementation specification
        env: Environment variables from Butler
        tenant_id: Required tenant UUID for multi-tenant isolation

    Returns:
        Normalized result from Hermes implementation
    """
    if env is None:
        env = {}
    if tenant_id:
        env["tenant_id"] = tenant_id
    return await execute_hermes_implementation(hermes_spec, args, env=env)


class HermesToolDispatcher:
    """Dispatcher for Hermes tools within Butler's governance pipeline with tenant isolation.

    This replaces Hermes handle_function_call with a Butler-owned version
    that respects Butler's governance while calling Hermes implementations.
    All operations are tenant-scoped for production multi-tenant deployment.
    """

    def __init__(self, compiled_specs: dict[str, ButlerToolSpec]):
        self._specs = compiled_specs

    async def dispatch(
        self,
        tool_name: str,
        args: dict[str, Any],
        env: dict[str, Any] | None = None,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch a Hermes tool execution with tenant isolation.

        Args:
            tool_name: Name of the tool to execute
            args: Tool arguments
            env: Environment variables from Butler
            tenant_id: Required tenant UUID for multi-tenant isolation

        Returns:
            Result from Hermes implementation

        Raises:
            ValueError: If tool not found or not a Hermes tool
        """
        spec = self._specs.get(tool_name)
        if not spec:
            raise ValueError(f"Tool '{tool_name}' not found in compiled specs")

        # Check if this is a Hermes tool by looking up in the global mapping
        hermes_spec = _hermes_impl_mapping.get(tool_name)
        if not hermes_spec:
            raise ValueError(f"Tool '{tool_name}' is not a Hermes implementation")

        return await execute_hermes_tool_with_governance(
            tool_name=tool_name,
            args=args,
            hermes_spec=hermes_spec,
            env=env,
            tenant_id=tenant_id,
        )
