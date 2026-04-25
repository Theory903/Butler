"""
Tool Registry - Phase T3: Canonical Tool Registry Integration.

Loads canonical tools, adapted tools, deduplicates by canonical_name,
validates schemas/risk tier/approval mode/timeout/tenant_scope_required,
compiles once at boot, caches compiled registry, emits boot log summary,
exposes query APIs by category/risk/permission.
"""

from __future__ import annotations

import structlog
from collections import Counter
from typing import Any

from langchain_core.tools import BaseTool, ToolInputSchema
from pydantic import BaseModel

from domain.tools.adapters import (
    ACPAdapter,
    DiscoveredTool,
    HermesAdapter,
    LangChainAdapter,
    LegacyButlerAdapter,
    MCPAdapter,
    OpenClawSkillAdapter,
    ServiceToolAdapter,
    ToolAdapter,
)
from domain.tools.spec import ApprovalMode, RiskTier, ToolSpec as DomainToolSpec

logger = structlog.get_logger(__name__)


class LegacyToolSpec(BaseModel):
    """Legacy ToolSpec for backward compatibility with LangChain interface."""

    name: str
    description: str
    args_schema: type[ToolInputSchema] | None = None
    risk_tier: int = 0
    approval_mode: str = "auto"
    required_permissions: list[str] = []
    sandbox_required: bool = False

    @classmethod
    def from_domain_spec(cls, spec: DomainToolSpec) -> LegacyToolSpec:
        """Convert from canonical domain ToolSpec to legacy ToolSpec."""
        return cls(
            name=spec.canonical_name,
            description=spec.description,
            risk_tier=int(spec.risk_tier.value.replace("L", "")),
            approval_mode=spec.approval_mode.value,
            required_permissions=list(spec.required_permissions),
            sandbox_required=spec.sandbox_required,
        )


class ToolRegistry:
    """Canonical Butler tool registry with adapter support.

    Loads tools from:
    - Canonical domain ToolSpecs
    - Legacy Butler runtime tools (via LegacyButlerAdapter)
    - LangChain tools (via LangChainAdapter)
    - MCP tools (via MCPAdapter)
    - ACP tools (via ACPAdapter)
    - Hermes tools (via HermesAdapter)
    - OpenClaw skills (via OpenClawSkillAdapter)
    - Service tools (via ServiceToolAdapter)

    Uses canonical DomainToolSpec internally. LegacyToolSpec only for
    LangChain compatibility layer.
    """

    _tools: dict[str, BaseTool] = {}
    _specs: dict[str, DomainToolSpec] = {}
    _legacy_specs: dict[str, LegacyToolSpec] = {}  # For LangChain compatibility only
    _executor: Any = None
    _auditor: Any = None
    _compiled: bool = False

    # Adapters for different tool sources
    _adapters: dict[str, ToolAdapter] = {}

    @classmethod
    def initialize(cls, executor: Any, auditor: Any = None):
        cls._executor = executor
        cls._auditor = auditor

        # Initialize adapters
        cls._adapters = {
            "legacy_butler": LegacyButlerAdapter(),
            "langchain": LangChainAdapter(),
            "mcp": MCPAdapter(),
            "acp": ACPAdapter(),
            "hermes": HermesAdapter(),
            "openclaw": OpenClawSkillAdapter(),
            "service": ServiceToolAdapter(),
        }

    @classmethod
    def compile(cls) -> None:
        """Compile all tools from adapters and canonical sources.

        This should be called once at boot.
        Emits a single boot log summary.
        """
        if cls._compiled:
            logger.warning("tool_registry_already_compiled")
            return

        all_discovered: list[DiscoveredTool] = []

        # Discover tools from all adapters
        for adapter_name, adapter in cls._adapters.items():
            try:
                discovered = adapter.discover()
                all_discovered.extend(discovered)
                logger.info(
                    "adapter_discovered_tools",
                    adapter=adapter_name,
                    count=len(discovered),
                )
            except Exception as e:
                logger.error(
                    "adapter_discovery_failed",
                    adapter=adapter_name,
                    error=str(e),
                )

        # Convert discovered tools to ToolSpecs
        specs_by_canonical_name: dict[str, DomainToolSpec] = {}

        for discovered in all_discovered:
            try:
                adapter = cls._adapters[discovered.source_system]
                spec = adapter.to_tool_spec(discovered)

                # Deduplicate by canonical_name
                if spec.canonical_name in specs_by_canonical_name:
                    logger.warning(
                        "tool_duplicate_skipped",
                        canonical_name=spec.canonical_name,
                        existing_source=specs_by_canonical_name[spec.canonical_name].source_system,
                        new_source=discovered.source_system,
                    )
                else:
                    specs_by_canonical_name[spec.canonical_name] = spec
            except Exception as e:
                logger.error(
                    "tool_conversion_failed",
                    tool_name=discovered.name,
                    source_system=discovered.source_system,
                    error=str(e),
                )

        # Store compiled specs
        cls._specs = specs_by_canonical_name

        # Emit boot log summary
        tier_counts = Counter(spec.risk_tier.value for spec in cls._specs.values())
        disabled_count = sum(1 for spec in cls._specs.values() if not spec.enabled)

        logger.info(
            "tool_registry_compiled",
            total=len(cls._specs),
            l0=tier_counts.get("L0", 0),
            l1=tier_counts.get("L1", 0),
            l2=tier_counts.get("L2", 0),
            l3=tier_counts.get("L3", 0),
            l4=tier_counts.get("L4", 0),
            disabled=disabled_count,
        )

        cls._compiled = True

    @classmethod
    def register(cls, spec: DomainToolSpec) -> BaseTool:
        """Register a canonical ToolSpec.

        Args:
            spec: Canonical DomainToolSpec

        Returns:
            BaseTool adapter
        """
        if not cls._compiled:
            logger.warning("tool_registry_not_compiled_calling_compile")
            cls.compile()

        # Deduplicate by canonical_name
        if spec.canonical_name in cls._specs:
            logger.warning(
                "tool_already_registered_skipping",
                canonical_name=spec.canonical_name,
            )
            return cls._tools.get(spec.canonical_name)

        # Validate spec
        cls._validate_spec(spec)

        # Store canonical spec
        cls._specs[spec.canonical_name] = spec

        # Store legacy spec for LangChain compatibility
        legacy_spec = LegacyToolSpec.from_domain_spec(spec)
        cls._legacy_specs[spec.canonical_name] = legacy_spec

        # Create LangChain adapter (for compatibility with existing code)
        from langchain.tools import ButlerToolAdapter

        adapter = ButlerToolAdapter(
            spec=legacy_spec,
            executor=cls._executor,
            auditor=cls._auditor,
        )
        cls._tools[spec.canonical_name] = adapter

        return adapter

    @classmethod
    def _validate_spec(cls, spec: DomainToolSpec) -> None:
        """Validate a ToolSpec.

        Args:
            spec: ToolSpec to validate

        Raises:
            ValueError: If validation fails
        """
        # Validate risk tier
        if spec.risk_tier not in RiskTier:
            raise ValueError(f"Invalid risk tier: {spec.risk_tier}")

        # Validate approval mode
        if spec.approval_mode not in ApprovalMode:
            raise ValueError(f"Invalid approval mode: {spec.approval_mode}")

        # Validate timeout
        if spec.timeout_seconds <= 0:
            raise ValueError(f"Invalid timeout: {spec.timeout_seconds}")

        # Validate max retries
        if spec.max_retries < 0:
            raise ValueError(f"Invalid max_retries: {spec.max_retries}")

        # Validate tenant scope requirement for non-L0 tools
        if spec.risk_tier != RiskTier.L0 and not spec.tenant_scope_required:
            raise ValueError(
                f"Tenant scope required for {spec.risk_tier} tools"
            )

    @classmethod
    def get_tool(cls, name: str) -> BaseTool | None:
        """Get a tool by canonical name.

        Args:
            name: Canonical tool name

        Returns:
            BaseTool or None
        """
        if not cls._compiled:
            cls.compile()
        return cls._tools.get(name)

    @classmethod
    def get_spec(cls, name: str) -> DomainToolSpec | None:
        """Get a ToolSpec by canonical name.

        Args:
            name: Canonical tool name

        Returns:
            ToolSpec or None
        """
        if not cls._compiled:
            cls.compile()
        return cls._specs.get(name)

    @classmethod
    def query_by_category(cls, category: str) -> list[DomainToolSpec]:
        """Query tools by category.

        Args:
            category: Tool category

        Returns:
            List of ToolSpecs
        """
        if not cls._compiled:
            cls.compile()
        return [spec for spec in cls._specs.values() if spec.category == category]

    @classmethod
    def query_by_risk(cls, risk_tier: RiskTier) -> list[DomainToolSpec]:
        """Query tools by risk tier.

        Args:
            risk_tier: Risk tier

        Returns:
            List of ToolSpecs
        """
        if not cls._compiled:
            cls.compile()
        return [spec for spec in cls._specs.values() if spec.risk_tier == risk_tier]

    @classmethod
    def query_by_permission(cls, permission: str) -> list[DomainToolSpec]:
        """Query tools that require a specific permission.

        Args:
            permission: Permission name

        Returns:
            List of ToolSpecs
        """
        if not cls._compiled:
            cls.compile()
        return [
            spec
            for spec in cls._specs.values()
            if permission in spec.required_permissions
        ]

    @classmethod
    def all_tools(cls) -> list[BaseTool]:
        """Get all tools.

        Returns:
            List of all BaseTools
        """
        if not cls._compiled:
            cls.compile()
        return list(cls._tools.values())

    @classmethod
    def all_specs(cls) -> list[DomainToolSpec]:
        """Get all ToolSpecs.

        Returns:
            List of all ToolSpecs
        """
        if not cls._compiled:
            cls.compile()
        return list(cls._specs.values())

    @classmethod
    def unregister(cls, name: str) -> bool:
        """Unregister a tool by canonical name.

        Args:
            name: Canonical tool name

        Returns:
            True if tool was unregistered, False otherwise
        """
        if name in cls._tools:
            del cls._tools[name]
        if name in cls._specs:
            del cls._specs[name]
            return True
        return False

    @classmethod
    def clear(cls) -> None:
        """Clear all tools and specs."""
        cls._tools.clear()
        cls._specs.clear()
        cls._compiled = False
