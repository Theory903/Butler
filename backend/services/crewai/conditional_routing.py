"""CrewAI conditional routing integration with Butler.

This module provides integration between CrewAI's @router decorator
and Butler's conditional routing logic, enabling sophisticated
workflow control while maintaining Butler's governance boundaries.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from .config import CrewAIConfig

logger = logging.getLogger(__name__)


class ButlerRouterAdapter:
    """Adapter for integrating CrewAI's @router with Butler's routing logic.

    This adapter maps CrewAI's decorator-based conditional routing to
    Butler's intent classification and routing system, enabling:
    - CrewAI's @router for dynamic flow control
    - Butler's policy enforcement and approval gates
    - Butler's security guardrails on routing decisions

    Integration Principles:
    - Use CrewAI's @router for in-memory conditional logic
    - Use Butler for policy enforcement and security checks
    - Maintain Butler's service boundaries and governance
    """

    def __init__(
        self,
        config: CrewAIConfig | None = None,
        content_guard: Any = None,
    ) -> None:
        """Initialize Butler Router adapter.

        Args:
            config: CrewAI configuration.
            content_guard: Butler ContentGuard instance for safety checks.
        """
        self._config = config or CrewAIConfig()
        self._content_guard = content_guard
        self._router_functions: dict[str, Callable] = {}

    def register_router_function(
        self, name: str, func: Callable
    ) -> None:
        """Register a CrewAI router function with Butler.

        Args:
            name: Name of the router function.
            func: Router function to register.
        """
        self._router_functions[name] = func
        logger.info(f"Registered router function: {name}")

    def create_butler_aware_router(
        self,
        crewai_router_func: Callable,
        policy_check: Callable | None = None,
    ) -> Callable:
        """Create a Butler-aware wrapper for CrewAI router function.

        Args:
            crewai_router_func: Original CrewAI router function.
            policy_check: Optional Butler policy check function.

        Returns:
            Wrapped router function with Butler policy enforcement.
        """
        async def wrapped_router(*args: Any, **kwargs: Any) -> Any:
            # Apply Butler policy check if provided
            if policy_check:
                policy_result = await policy_check(*args, **kwargs)
                if not policy_result.get("allowed", True):
                    logger.warning(
                        f"Policy check blocked routing: {policy_result.get('reason')}"
                    )
                    return {
                        "blocked_by_policy": True,
                        "reason": policy_result.get("reason"),
                    }

            # Execute original CrewAI router function
            result = await crewai_router_func(*args, **kwargs)

            # Apply security guardrails to routing decision if enabled
            if self._content_guard:
                try:
                    decision_str = str(result)
                    safety_check = await self._content_guard.check(decision_str)
                    if not safety_check.get("safe", True):
                        logger.warning(
                            f"ContentGuard blocked routing decision: {safety_check.get('reason')}"
                        )
                        return {
                            "blocked_by_content_guard": True,
                            "reason": safety_check.get("reason"),
                        }
                except Exception as e:
                    logger.warning(f"ContentGuard check failed for routing: {e}")

            return result

        return wrapped_router

    async def execute_conditional_routing(
        self,
        context: dict[str, Any],
        router_name: str,
    ) -> dict[str, Any]:
        """Execute conditional routing using registered router function.

        Args:
            context: Execution context for routing decision.
            router_name: Name of the router function to use.

        Returns:
            Routing decision with metadata.
        """
        router_func = self._router_functions.get(router_name)

        if not router_func:
            logger.warning(f"Router function not found: {router_name}")
            return {
                "error": f"Router function not found: {router_name}",
                "fallback_route": "default",
            }

        try:
            # Execute router function
            result = await router_func(context)

            return {
                "route": result,
                "router_name": router_name,
                "metadata": {"butler_policy_enforced": True},
            }

        except Exception as e:
            logger.exception(f"Conditional routing execution failed: {e}")
            return {
                "error": str(e),
                "fallback_route": "default",
                "router_name": router_name,
            }


class ConditionalFlowBuilder:
    """Builder for creating conditional flows with CrewAI @router.

    This builder helps create complex conditional flows that combine:
    - CrewAI's @router decorator for dynamic routing
    - Butler's policy enforcement and approval gates
    - Butler's security guardrails
    """

    def __init__(
        self,
        config: CrewAIConfig | None = None,
    ) -> None:
        """Initialize Conditional Flow Builder.

        Args:
            config: CrewAI configuration.
        """
        self._config = config or CrewAIConfig()
        self._conditions: list[dict[str, Any]] = []

    def add_condition(
        self,
        name: str,
        condition_func: Callable,
        target_route: str,
    ) -> None:
        """Add a conditional routing rule.

        Args:
            name: Name of the condition.
            condition_func: Function that evaluates the condition.
            target_route: Route to take if condition is true.
        """
        self._conditions.append(
            {
                "name": name,
                "condition_func": condition_func,
                "target_route": target_route,
            }
        )
        logger.info(f"Added condition: {name} -> {target_route}")

    def build_crewai_router(self) -> Callable:
        """Build a CrewAI router function from registered conditions.

        Returns:
            CrewAI router function.
        """
        async def router_function(context: dict[str, Any]) -> str:
            for condition in self._conditions:
                try:
                    if await condition["condition_func"](context):
                        return condition["target_route"]
                except Exception as e:
                    logger.warning(
                        f"Condition evaluation failed for {condition['name']}: {e}"
                    )
                    continue

            # Default fallback route
            return "default"

        return router_function


# Example Butler policy check functions
async def butler_approval_policy_check(
    *args: Any, **kwargs: Any
) -> dict[str, Any]:
    """Butler policy check for routing decisions.

    Args:
        *args: Positional arguments.
        **kwargs: Keyword arguments.

    Returns:
        Policy check result.
    """
    # Phase 2: Basic policy check
    # Phase 3: Full integration with Butler's policy engine

    context = kwargs.get("context", {})
    requires_approval = context.get("requires_approval", False)

    if requires_approval:
        return {
            "allowed": False,
            "reason": "Requires human approval",
        }

    return {"allowed": True}


async def butler_resource_policy_check(
    *args: Any, **kwargs: Any
) -> dict[str, Any]:
    """Butler resource policy check for routing decisions.

    Args:
        *args: Positional arguments.
        **kwargs: Keyword arguments.

    Returns:
        Policy check result.
    """
    # Phase 2: Basic resource check
    # Phase 3: Full integration with Butler's resource management

    context = kwargs.get("context", {})
    resource_cost = context.get("estimated_cost", 0)

    if resource_cost > 1000:  # Example threshold
        return {
            "allowed": False,
            "reason": f"Resource cost too high: {resource_cost}",
        }

    return {"allowed": True}
