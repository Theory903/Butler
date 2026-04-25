"""Tool Policy Service - Phase T4.

Service layer integration for ToolPolicy.

This service wraps the domain ToolPolicy and provides
service-specific implementations for tenant service, rate limiter,
quota service, and admission controller.
"""

from __future__ import annotations

from typing import Any

import structlog

from domain.runtime.context import RuntimeContext
from domain.tools.policy import ToolPolicy, ToolPolicyDecision
from domain.tools.spec import ToolSpec

logger = structlog.get_logger(__name__)


class ToolPolicyService:
    """Service layer for tool policy enforcement."""

    def __init__(
        self,
        tenant_service: Any = None,
        rate_limiter: Any = None,
        quota_service: Any = None,
        admission_controller: Any = None,
    ):
        """Initialize ToolPolicyService.

        Args:
            tenant_service: Service for tenant plan checks
            rate_limiter: Rate limiter for tool execution
            quota_service: Quota/budget service
            admission_controller: AdmissionController for operation routing
        """
        self._policy = ToolPolicy(
            tenant_service=tenant_service,
            rate_limiter=rate_limiter,
            quota_service=quota_service,
            admission_controller=admission_controller,
        )

    def evaluate(
        self,
        context: RuntimeContext | None,
        spec: ToolSpec,
        user_permissions: frozenset[str] | None = None,
        approval_id: str | None = None,
    ) -> ToolPolicyDecision:
        """Evaluate tool execution policy.

        Args:
            context: RuntimeContext with request-scoped information
            spec: ToolSpec for the tool being executed
            user_permissions: User permissions
            approval_id: Approval ID if already approved

        Returns:
            ToolPolicyDecision with allow/deny and requirements
        """
        decision = self._policy.evaluate(
            context=context,
            spec=spec,
            user_permissions=user_permissions,
            approval_id=approval_id,
        )

        # Log policy decision
        logger.info(
            "tool_policy_decision",
            tool_name=spec.canonical_name,
            allowed=decision.allowed,
            requires_approval=decision.requires_approval,
            requires_sandbox=decision.requires_sandbox,
            degraded_mode=decision.degraded_mode.value if decision.degraded_mode else None,
            reason=decision.reason,
            tenant_id=context.tenant_id if context else None,
            account_id=context.account_id if context else None,
        )

        return decision

    def check_rate_limit(
        self,
        tenant_id: str,
        account_id: str,
        tool_name: str,
    ) -> bool:
        """Check if rate limit allows execution.

        Args:
            tenant_id: Tenant ID
            account_id: Account ID
            tool_name: Tool canonical name

        Returns:
            True if rate limit allows, False otherwise
        """
        if self._policy._rate_limiter:
            return self._policy._rate_limiter.check_rate_limit(
                tenant_id, account_id, tool_name
            )
        return True

    def check_quota(
        self,
        tenant_id: str,
        account_id: str,
        tool_name: str,
    ) -> bool:
        """Check if quota/budget allows execution.

        Args:
            tenant_id: Tenant ID
            account_id: Account ID
            tool_name: Tool canonical name

        Returns:
            True if quota allows, False otherwise
        """
        if self._policy._quota_service:
            return self._policy._quota_service.check_quota(
                tenant_id, account_id, tool_name
            )
        return True

    def is_risk_tier_allowed(
        self,
        tenant_id: str,
        risk_tier: str,
    ) -> bool:
        """Check if risk tier is allowed for tenant plan.

        Args:
            tenant_id: Tenant ID
            risk_tier: Risk tier (L0-L4)

        Returns:
            True if risk tier allowed, False otherwise
        """
        if self._policy._tenant_service:
            return self._policy._tenant_service.is_risk_tier_allowed(
                tenant_id, risk_tier
            )
        return True
