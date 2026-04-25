"""
Execution runtime for Hermes tool implementations with multi-tenant support.

Handles calling Hermes implementation functions directly without
invoking Hermes registry, memory, session, or CLI subsystems.
All operations support tenant isolation for production multi-tenant deployment.
"""

from __future__ import annotations

import inspect
from typing import Any

from backend.langchain.hermes_errors import (
    normalize_hermes_exception,
    normalize_hermes_result,
)
from backend.langchain.hermes_registry import HermesImplementationSpec


async def execute_hermes_implementation(
    spec: HermesImplementationSpec,
    args: dict[str, Any],
    *,
    env: dict[str, Any] | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Execute a Hermes tool implementation directly with tenant isolation.

    Supports the common Hermes function signatures:
    - async def tool(params: dict, env: dict) -> dict
    - def tool(params: dict, env: dict) -> dict
    - async def tool(**kwargs) -> dict
    - def tool(**kwargs) -> dict
    - class Tool: async def execute(...)

    Does NOT use Hermes SessionDB, memory providers, CLI, or gateway.

    Args:
        spec: Hermes implementation specification
        args: Tool arguments
        env: Environment variables (from Butler, not Hermes config)
        tenant_id: Required tenant UUID for multi-tenant isolation

    Returns:
        Normalized result dict with tenant_id included

    Raises:
        HermesExecutionError: If execution fails
    """
    impl = spec.implementation
    env = env or {}
    if tenant_id:
        env["tenant_id"] = tenant_id

    try:
        # Handle class-based tools
        if inspect.isclass(impl):
            instance = impl()
            if hasattr(instance, "execute"):
                result = instance.execute(args, env)
            elif callable(instance):
                result = instance(args, env)
            else:
                raise TypeError(
                    f"Hermes tool class {impl.__name__} has no execute() or __call__() method"
                )
        else:
            # Handle function-based tools
            signature = inspect.signature(impl)
            params = signature.parameters

            # Try different signature patterns
            if "params" in params and "env" in params:
                result = impl(params=args, env=env)
            elif "env" in params:
                result = impl(env=env, **args)
            else:
                result = impl(**args)

        # Handle async results
        if inspect.isawaitable(result):
            result = await result

        # Normalize result and include tenant_id
        normalized = normalize_hermes_result(result)
        if tenant_id and isinstance(normalized, dict):
            normalized["tenant_id"] = tenant_id
        return normalized

    except Exception as exc:
        raise normalize_hermes_exception(exc, tool_name=spec.name) from exc


def execute_hermes_implementation_sync(
    spec: HermesImplementationSpec,
    args: dict[str, Any],
    *,
    env: dict[str, Any] | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Synchronous wrapper for Hermes tool execution with tenant isolation.

    This is provided for compatibility but async execution is preferred.

    Args:
        spec: Hermes implementation specification
        args: Tool arguments
        env: Environment variables (from Butler, not Hermes config)
        tenant_id: Required tenant UUID for multi-tenant isolation

    Returns:
        Normalized result dict with tenant_id included

    Raises:
        HermesExecutionError: If execution fails
    """
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()

    return loop.run_until_complete(
        execute_hermes_implementation(spec, args, env=env, tenant_id=tenant_id)
    )
