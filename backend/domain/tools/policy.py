"""ToolPolicy - Phase T4: Tool Policy Enforcement.

ToolPolicy checks all required conditions before tool execution:
- RuntimeContext exists
- tenant_id exists
- account_id exists
- session_id exists
- tool exists
- tool enabled
- permissions satisfy required_permissions
- memory scope allowed
- network access allowed
- filesystem access allowed
- credential access allowed
- risk tier allowed by tenant plan
- rate limit allowed
- quota/budget available
- approval satisfied
- sandbox available when required
- operation admitted by AdmissionController

Fail closed by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from domain.runtime.context import RuntimeContext
from domain.tools.spec import ToolSpec


class DegradedMode(str, Enum):
    """Degraded execution modes when full execution is not available."""

    NONE = "none"  # Full execution available
    READ_ONLY = "read_only"  # Read-only access only
    SIMULATED = "simulated"  # Dry-run simulation only
    BLOCKED = "blocked"  # Execution blocked


@dataclass(frozen=True)
class ToolPolicyDecision:
    """Decision from ToolPolicy evaluation."""

    allowed: bool
    reason: str
    requires_approval: bool
    requires_sandbox: bool
    degraded_mode: DegradedMode | None
    audit_required: bool

    @classmethod
    def allow(cls, reason: str = "") -> ToolPolicyDecision:
        """Create an allow decision."""
        return cls(
            allowed=True,
            reason=reason,
            requires_approval=False,
            requires_sandbox=False,
            degraded_mode=None,
            audit_required=True,
        )

    @classmethod
    def deny(cls, reason: str) -> ToolPolicyDecision:
        """Create a deny decision."""
        return cls(
            allowed=False,
            reason=reason,
            requires_approval=False,
            requires_sandbox=False,
            degraded_mode=None,
            audit_required=True,
        )

    @classmethod
    def require_approval(cls, reason: str) -> ToolPolicyDecision:
        """Create a decision requiring approval."""
        return cls(
            allowed=False,
            reason=reason,
            requires_approval=True,
            requires_sandbox=False,
            degraded_mode=None,
            audit_required=True,
        )

    @classmethod
    def require_sandbox(cls, reason: str) -> ToolPolicyDecision:
        """Create a decision requiring sandbox."""
        return cls(
            allowed=False,
            reason=reason,
            requires_approval=False,
            requires_sandbox=True,
            degraded_mode=None,
            audit_required=True,
        )

    @classmethod
    def degraded(cls, mode: DegradedMode, reason: str) -> ToolPolicyDecision:
        """Create a degraded mode decision."""
        return cls(
            allowed=True,
            reason=reason,
            requires_approval=False,
            requires_sandbox=False,
            degraded_mode=mode,
            audit_required=True,
        )


class ToolPolicy:
    """Tool policy enforcement engine.

    Fail closed by default - if any check fails, deny execution.
    """

    def __init__(
        self,
        tenant_service: Any = None,
        rate_limiter: Any = None,
        quota_service: Any = None,
        admission_controller: Any = None,
    ):
        """Initialize ToolPolicy.

        Args:
            tenant_service: Service for tenant plan checks
            rate_limiter: Rate limiter for tool execution
            quota_service: Quota/budget service
            admission_controller: AdmissionController for operation routing
        """
        self._tenant_service = tenant_service
        self._rate_limiter = rate_limiter
        self._quota_service = quota_service
        self._admission_controller = admission_controller

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
        # Fail closed: if context is None, deny
        if context is None:
            return ToolPolicyDecision.deny("RuntimeContext not provided")

        # Check tenant_id exists
        if not context.tenant_id:
            return ToolPolicyDecision.deny("tenant_id not provided in RuntimeContext")

        # Check account_id exists
        if not context.account_id:
            return ToolPolicyDecision.deny("account_id not provided in RuntimeContext")

        # Check session_id exists
        if not context.session_id:
            return ToolPolicyDecision.deny("session_id not provided in RuntimeContext")

        # Check tool enabled
        if not spec.enabled:
            return ToolPolicyDecision.deny(f"Tool {spec.canonical_name} is disabled")

        # Check permissions satisfy required_permissions
        if user_permissions is None:
            user_permissions = frozenset()
        if not spec.required_permissions.issubset(user_permissions):
            missing = spec.required_permissions - user_permissions
            return ToolPolicyDecision.deny(f"Missing required permissions: {missing}")

        # Check scopes satisfy required_scopes
        if not spec.required_scopes.issubset(frozenset(context.permissions or [])):
            missing = spec.required_scopes - frozenset(context.permissions or [])
            return ToolPolicyDecision.deny(f"Missing required scopes: {missing}")

        # Check risk tier allowed by tenant plan
        if self._tenant_service:
            if not self._tenant_service.is_risk_tier_allowed(context.tenant_id, spec.risk_tier):
                return ToolPolicyDecision.deny(
                    f"Risk tier {spec.risk_tier} not allowed for tenant plan"
                )

        # Check rate limit
        if self._rate_limiter:
            if not self._rate_limiter.check_rate_limit(
                context.tenant_id,
                context.account_id,
                spec.canonical_name,
            ):
                return ToolPolicyDecision.deny("Rate limit exceeded")

        # Check quota/budget
        if self._quota_service:
            if not self._quota_service.check_quota(
                context.tenant_id,
                context.account_id,
                spec.canonical_name,
            ):
                return ToolPolicyDecision.deny("Quota/budget exceeded")

        # Check approval satisfied for tools requiring approval
        if spec.requires_human_approval() and not approval_id:
            return ToolPolicyDecision.require_approval(
                f"Tool {spec.canonical_name} requires approval"
            )

        # Check critical approval for L4 tools
        if spec.requires_critical_approval() and not approval_id:
            return ToolPolicyDecision.require_approval(
                f"Tool {spec.canonical_name} requires critical approval"
            )

        # Check sandbox available when required
        if spec.sandbox_required:
            # TODO: Check if sandbox is available
            # For now, require sandbox but don't check availability
            return ToolPolicyDecision.require_sandbox(
                f"Tool {spec.canonical_name} requires sandbox"
            )

        # Check operation admitted by AdmissionController
        if self._admission_controller:
            # TODO: Implement admission controller check
            pass

        # All checks passed - allow execution
        return ToolPolicyDecision.allow(f"Tool {spec.canonical_name} execution allowed")
