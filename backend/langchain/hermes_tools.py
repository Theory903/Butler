"""
Butler-Hermes LangChain tool adapter.

Wraps Hermes tool implementations as LangChain BaseTool objects,
routing through Butler ToolExecutor for governance.
"""

from __future__ import annotations

from typing import Any

from backend.langchain.hermes_registry import HermesImplementationSpec
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict

import structlog

logger = structlog.get_logger(__name__)


class ButlerHermesToolInput(BaseModel):
    """Default input schema for Butler Hermes tools.

    Allows extra fields to accommodate varying tool parameters.
    """

    model_config = ConfigDict(extra="allow")


class ButlerHermesTool(BaseTool):
    """LangChain BaseTool wrapper for Hermes implementations.

    This adapter:
    - Accepts a HermesImplementationSpec
    - Routes ALL execution through Butler ToolExecutor (never direct Hermes)
    - Risk-tier gating, sandbox dispatch, approval, audit happen inside ToolExecutor
    - Normalizes output into a stable result
    - Never calls Hermes handle_function_call() directly
    - Supports optional env injection from Butler, not Hermes config

    Production integration (Phase A.2):
    - L0/L1 tools: Direct dispatch with audit (via ToolExecutor)
    - L2/L3 tools: Full governance via ToolExecutor (approval, sandbox, audit)
    """

    spec: HermesImplementationSpec
    name: str
    description: str
    args_schema: type[BaseModel] = ButlerHermesToolInput
    tool_executor: Any | None = None
    tenant_id: str | None = None
    account_id: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    user_id: str | None = None

    def __init__(
        self,
        spec: HermesImplementationSpec,
        tool_executor: Any | None = None,
        tenant_id: str | None = None,
        account_id: str | None = None,
        session_id: str | None = None,
        trace_id: str | None = None,
        user_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            spec=spec,
            name=spec.name,
            description=spec.description,
            args_schema=spec.args_schema or ButlerHermesToolInput,
            **kwargs,
        )
        self.tool_executor = tool_executor
        self.tenant_id = tenant_id
        self.account_id = account_id
        self.session_id = session_id
        self.trace_id = trace_id
        self.user_id = user_id

    async def _arun(self, **kwargs: Any) -> Any:
        """Async execution through Butler ToolExecutor.

        Args:
            **kwargs: Tool arguments

        Returns:
            Normalized result from ToolExecutor

        Raises:
            RuntimeError: If ToolExecutor is not configured
        """
        if self.tool_executor is None:
            logger.error(
                "hermes_tool_executor_missing",
                tool_name=self.spec.name,
                risk_tier=self.spec.risk_tier,
            )
            raise RuntimeError(
                f"ToolExecutor required for ButlerHermesTool: {self.spec.name}. "
                "Configure tool_executor during initialization."
            )

        try:
            # Route through ToolExecutor for all governance
            result = await self.tool_executor.execute(
                tool_name=self.spec.name,
                parameters=kwargs,
                tenant_id=self.tenant_id or "default",
                account_id=self.account_id or "default",
                session_id=self.session_id,
                trace_id=self.trace_id,
                user_id=self.user_id,
            )

            # Return the data portion of ToolResult
            if hasattr(result, "data"):
                return result.data
            return result
        except Exception as exc:
            logger.error(
                "hermes_tool_execution_failed",
                tool_name=self.spec.name,
                error=str(exc),
            )
            raise

    def _run(self, **kwargs: Any) -> Any:
        """Sync execution is not supported for Butler Hermes tools.

        Raises:
            RuntimeError: Always - use async execution
        """
        raise RuntimeError("Use async execution for Butler Hermes tools")


def build_butler_hermes_langchain_tools(
    registry: Any | None = None,
    allowed_tool_names: list[str] | None = None,
    risk_tier_limit: int | None = None,
    tool_executor: Any | None = None,
    tenant_id: str | None = None,
    account_id: str | None = None,
    session_id: str | None = None,
    trace_id: str | None = None,
    user_id: str | None = None,
) -> list[ButlerHermesTool]:
    """Build LangChain tools from Butler-owned Hermes registry.

    Args:
        registry: Butler-owned Hermes registry. If None, uses global registry.
        allowed_tool_names: Filter to only these tool names. If None, include all.
        risk_tier_limit: Only include tools with risk_tier <= this value.
        tool_executor: Butler ToolExecutor for governance (required in production)
        tenant_id: Tenant UUID for multi-tenant isolation
        account_id: Account UUID
        session_id: Session UUID
        trace_id: Trace UUID
        user_id: User UUID

    Returns:
        List of ButlerHermesTool LangChain tools
    """
    if registry is None:
        from backend.langchain.hermes_registry import get_butler_hermes_registry

        registry = get_butler_hermes_registry()

    specs = registry.list()

    # Filter by allowed tool names
    if allowed_tool_names:
        specs = [spec for spec in specs if spec.name in allowed_tool_names]

    # Filter by risk tier
    if risk_tier_limit is not None:
        specs = [spec for spec in specs if spec.risk_tier <= risk_tier_limit]

    # Build LangChain tools with ToolExecutor
    return [
        ButlerHermesTool(
            spec=spec,
            tool_executor=tool_executor,
            tenant_id=tenant_id,
            account_id=account_id,
            session_id=session_id,
            trace_id=trace_id,
            user_id=user_id,
        )
        for spec in specs
    ]


def build_single_butler_hermes_tool(
    spec: HermesImplementationSpec,
    tool_executor: Any | None = None,
    tenant_id: str | None = None,
    account_id: str | None = None,
    session_id: str | None = None,
    trace_id: str | None = None,
    user_id: str | None = None,
) -> ButlerHermesTool:
    """Build a single LangChain tool from a Hermes spec.

    Args:
        spec: Hermes implementation specification
        tool_executor: Butler ToolExecutor for governance (required in production)
        tenant_id: Tenant UUID for multi-tenant isolation
        account_id: Account UUID
        session_id: Session UUID
        trace_id: Trace UUID
        user_id: User UUID

    Returns:
        ButlerHermesTool instance
    """
    return ButlerHermesTool(
        spec=spec,
        tool_executor=tool_executor,
        tenant_id=tenant_id,
        account_id=account_id,
        session_id=session_id,
        trace_id=trace_id,
        user_id=user_id,
    )
