"""
LangChain Tool Factory - Canonical ToolSpec to LangChain tools with hybrid governance.

This factory converts Butler's canonical ToolSpec into LangChain BaseTool instances,
preserving Butler's governance through hybrid execution:
- L0/L1 tools: Direct dispatch with audit logging
- L2/L3/L4 tools: Route through ToolExecutor.execute_canonical with approval interrupts
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from langchain_core.tools import BaseTool
from pydantic import BaseModel, create_model

from domain.tools.hermes_compiler import ButlerToolSpec, RiskTier
from langchain.runtime import ButlerToolContext

logger = structlog.get_logger(__name__)


class ButlerLangChainTool(BaseTool):
    """LangChain tool adapter for canonical ToolSpec with hybrid governance.

    This adapter:
    - Wraps canonical ToolSpec from domain/tools/spec.py
    - Implements hybrid governance based on RiskTier
    - L0/L1: Direct dispatch with audit
    - L2/L3/L4: Route through ToolExecutor.execute_canonical with approval interrupts
    - Preserves tenant/account/session context
    """

    spec: ButlerToolSpec | None = None
    tool_context: ButlerToolContext | None = None
    tool_executor: Any | None = None
    direct_implementation: Any | None = None

    name: str = ""
    description: str = ""
    args_schema: type[BaseModel] | None = None

    def __init__(
        self,
        spec: ButlerToolSpec | None = None,
        tool_context: ButlerToolContext | None = None,
        tool_executor: Any | None = None,
        direct_implementation: Any | None = None,
        **kwargs: Any,
    ):
        """Initialize ButlerLangChainTool.

        Args:
            spec: Canonical ToolSpec from domain/tools/spec.py
            tool_context: ButlerToolContext for tenant/account/session propagation
            tool_executor: Butler's ToolExecutor for L2/L3/L4 governance
            direct_implementation: Direct function for L0/L1 tools
            **kwargs: Additional BaseTool parameters
        """
        super().__init__(**kwargs)
        self.spec = spec
        self.tool_context = tool_context
        self.tool_executor = tool_executor
        self.direct_implementation = direct_implementation

        # Only set name/description/schema if spec is provided
        if spec is not None:
            self.name = spec.canonical_name
            # Prefer real description; fall back to name if missing.
            self.description = (
                (spec.description or spec.name) if hasattr(spec, "description") else spec.name
            )

            # Build Pydantic schema from input_schema if available
            if spec.input_schema:
                self.args_schema = self._build_args_schema(spec.input_schema)
            else:
                # Provide minimal schema for tools without input_schema
                # This allows tool calling to work even when schema is not defined
                self.args_schema = create_model(f"{spec.name}_Args")
        else:
            # Set default empty schema if spec is None
            self.args_schema = create_model("EmptyArgs")

    def _build_args_schema(self, input_schema: dict) -> type[BaseModel]:
        """Build Pydantic args_schema from ButlerToolSpec input_schema."""
        fields: dict[str, Any] = {}
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])

        for field_name, field_def in properties.items():
            field_type = self._map_json_type_to_python(field_def.get("type", "string"))
            default = ... if field_name in required else None
            fields[field_name] = (field_type, default)

        return create_model(f"{self.spec.name}_Args", **fields)

    def _map_json_type_to_python(self, json_type: str) -> type:
        """Map JSON Schema type to Python type."""
        mapping = {
            "string": str,
            "number": float,
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        return mapping.get(json_type, str)

    def _run(self, **kwargs: Any) -> Any:
        """Synchronous execution with hybrid governance."""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self._arun(**kwargs))

    async def _arun(self, **kwargs: Any) -> Any:
        """Async execution with hybrid governance based on RiskTier."""
        if self.spec is None:
            raise RuntimeError(
                "ButlerLangChainTool.spec is not initialized. Tool must be created via ButlerToolFactory."
            )

        # Check if tool is enabled
        if not self.spec.enabled:
            logger.error(
                "tool_execution_disabled",
                tool_name=self.spec.canonical_name,
            )
            raise PermissionError(f"Tool {self.spec.canonical_name} is disabled")

        # Hybrid governance: L0/L1 direct, L2/L3/L4 through ToolExecutor
        if self.spec.risk_tier in (RiskTier.L0, RiskTier.L1):
            return await self._execute_direct(**kwargs)
        return await self._execute_with_governance(**kwargs)

    async def _execute_direct(self, **kwargs: Any) -> Any:
        """Direct execution for L0/L1 tools with audit logging."""
        if self.spec is None:
            raise RuntimeError(
                "ButlerLangChainTool.spec is not initialized. Tool must be created via ButlerToolFactory."
            )
        if self.tool_context is None:
            raise RuntimeError(
                "ButlerLangChainTool.tool_context is not initialized. Tool must be created via ButlerToolFactory."
            )

        if self.direct_implementation is None:
            logger.warning(
                "tool_direct_implementation_missing",
                tool_name=self.spec.canonical_name,
                risk_tier=self.spec.risk_tier.value,
            )
            raise RuntimeError(
                f"No direct implementation for L0/L1 tool: {self.spec.canonical_name}"
            )

        try:
            result = await self._call_direct(**kwargs)

            # Audit logging for L1 (logged tier)
            if self.spec.risk_tier == RiskTier.L1:
                logger.info(
                    "tool_executed_direct",
                    tool_name=self.spec.canonical_name,
                    risk_tier=self.spec.risk_tier.value,
                    tenant_id=self.tool_context.tenant_id,
                    account_id=self.tool_context.account_id,
                    session_id=self.tool_context.session_id,
                )

            return result
        except Exception as exc:
            logger.error(
                "tool_direct_execution_failed",
                tool_name=self.spec.canonical_name,
                error=str(exc),
            )
            raise

    async def _execute_with_governance(self, **kwargs: Any) -> Any:
        """Execution through ToolExecutor for L2/L3/L4 tools with full governance."""
        if self.spec is None:
            raise RuntimeError(
                "ButlerLangChainTool.spec is not initialized. Tool must be created via ButlerToolFactory."
            )
        if self.tool_context is None:
            raise RuntimeError(
                "ButlerLangChainTool.tool_context is not initialized. Tool must be created via ButlerToolFactory."
            )

        if self.tool_executor is None:
            logger.error(
                "tool_executor_missing",
                tool_name=self.spec.canonical_name,
                risk_tier=self.spec.risk_tier.value,
            )
            raise RuntimeError(f"No ToolExecutor for L2/L3/L4 tool: {self.spec.canonical_name}")

        try:
            # For L2/L3/L4, route through ToolExecutor.execute_canonical
            # This handles approval checks, sandboxing, and full audit trail
            import uuid

            from domain.runtime.context import RuntimeContext
            from services.tools.executor import ToolExecutionRequest

            # Build RuntimeContext for canonical execution
            context = RuntimeContext.create(
                tenant_id=self.tool_context.tenant_id or "default",
                account_id=self.tool_context.account_id,
                session_id=self.tool_context.session_id,
                request_id=str(uuid.uuid4()),
                trace_id=self.tool_context.trace_id or str(uuid.uuid4()),
                channel="langchain",
                user_id=self.tool_context.user_id,
            )

            exec_request = ToolExecutionRequest(
                tool_name=self.spec.canonical_name,
                input=kwargs,
                context=context,
                idempotency_key=None,
            )

            result = await self.tool_executor.execute_canonical(exec_request)
            return result
        except Exception as exc:
            logger.error(
                "tool_governed_execution_failed",
                tool_name=self.spec.canonical_name,
                risk_tier=self.spec.risk_tier.value,
                error=str(exc),
            )
            raise

    async def _call_direct(self, **kwargs: Any) -> Any:
        """Call the direct implementation function."""
        if asyncio.iscoroutinefunction(self.direct_implementation):
            return await self.direct_implementation(**kwargs)
        return self.direct_implementation(**kwargs)


class ButlerToolFactory:
    """Factory for creating LangChain tools from canonical ToolSpec.

    This factory:
    - Converts canonical ToolSpec to LangChain BaseTool instances
    - Applies hybrid governance based on RiskTier
    - Wires direct implementations for L0/L1 tools
    - Wires ToolExecutor for L2/L3/L4 tools
    """

    @staticmethod
    def create_tool(
        spec: ButlerToolSpec,
        tool_context: ButlerToolContext,
        tool_executor: Any | None = None,
        direct_implementation: Any | None = None,
    ) -> ButlerLangChainTool:
        """Create a LangChain tool from canonical ToolSpec.

        Args:
            spec: Canonical ButlerToolSpec from domain/tools/hermes_compiler.py
            tool_context: ButlerToolContext for context propagation
            tool_executor: Butler's ToolExecutor for L2/L3/L4 governance
            direct_implementation: Direct function for L0/L1 tools

        Returns:
            ButlerLangChainTool instance
        """
        return ButlerLangChainTool(
            spec=spec,
            tool_context=tool_context,
            tool_executor=tool_executor,
            direct_implementation=direct_implementation,
        )

    @staticmethod
    def create_tools_from_specs(
        specs: list[ButlerToolSpec],
        tool_context: ButlerToolContext,
        tool_executor: Any | None = None,
        direct_implementations: dict[str, Any] | None = None,
    ) -> list[ButlerLangChainTool]:
        """Create multiple LangChain tools from canonical ToolSpec list.

        Args:
            specs: List of canonical ToolSpec instances
            tool_context: ButlerToolContext for context propagation
            tool_executor: Butler's ToolExecutor for L2/L3/L4 governance
            direct_implementations: Dict mapping tool name to direct implementation

        Returns:
            List of ButlerLangChainTool instances
        """
        direct_implementations = direct_implementations or {}
        tools = []

        for spec in specs:
            if not spec.enabled:
                logger.debug("skipping_disabled_tool", tool_name=spec.canonical_name)
                continue

            # Skip blocked tools
            if hasattr(spec, "blocked") and spec.blocked:
                logger.debug("skipping_blocked_tool", tool_name=spec.canonical_name, block_reason=spec.block_reason)
                continue

            direct_impl = direct_implementations.get(spec.canonical_name)
            logger.info(
                "tool_direct_impl_lookup",
                tool_name=spec.canonical_name,
                risk_tier=spec.risk_tier.value if hasattr(spec, "risk_tier") else "unknown",
                has_direct_impl=direct_impl is not None,
                available_direct_impls=list(direct_implementations.keys())
                if direct_implementations
                else [],
            )
            tool = ButlerToolFactory.create_tool(
                spec=spec,
                tool_context=tool_context,
                tool_executor=tool_executor,
                direct_implementation=direct_impl,
            )
            tools.append(tool)

        logger.info(
            "butler_tools_created",
            total=len(specs),
            created=len(tools),
            disabled=sum(1 for s in specs if not s.enabled),
        )

        return tools

    @staticmethod
    def filter_by_risk_tier(
        specs: list[ButlerToolSpec],
        max_tier: RiskTier = RiskTier.L3,
    ) -> list[ButlerToolSpec]:
        """Filter specs by maximum risk tier.

        Args:
            specs: List of canonical ToolSpec instances
            max_tier: Maximum risk tier to include

        Returns:
            Filtered list of canonical ToolSpec instances
        """
        tier_order = {
            RiskTier.L0: 0,
            RiskTier.L1: 1,
            RiskTier.L2: 2,
            RiskTier.L3: 3,
            RiskTier.L4: 4,
        }
        max_level = tier_order.get(max_tier, 3)

        return [
            spec
            for spec in specs
            if spec.enabled and tier_order.get(spec.risk_tier, 0) <= max_level
        ]

    @staticmethod
    def filter_by_visibility(
        specs: list[ButlerToolSpec],
        account_tier: str = "free",
        channel: str = "api",
    ) -> list[ButlerToolSpec]:
        """Filter specs by visibility rules.

        Args:
            specs: List of canonical ToolSpec instances
            account_tier: Account tier (free, pro, enterprise)
            channel: Channel (mobile, web, voice, api)

        Returns:
            Filtered list of canonical ToolSpec instances
        """
        filtered = []

        for spec in specs:
            if not spec.enabled:
                continue

            # Note: Canonical ToolSpec doesn't have visible_tiers/visible_channels
            # This is a placeholder for future visibility filtering
            filtered.append(spec)

        return filtered
