"""Capability Policy Model — Structured Capability/Risk Rules.

Defines policies as structured capability/risk rules instead of word lists.
The classifier determines what capability/risk applies, and the policy engine enforces the decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class DataScope(StrEnum):
    """Data scope classifications."""

    INTERNAL = "internal"
    USER_DATA = "user_data"
    EXTERNAL_MESSAGE = "external_message"
    SYSTEM_CONFIG = "system_config"
    FINANCIAL = "financial"
    HEALTH = "health"
    LOCATION = "location"
    CONTACT = "contact"


class RiskLevel(StrEnum):
    """Risk levels for policy enforcement."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CapabilityPolicy(BaseModel):
    """Structured policy for a specific capability.

    Represents policy as structured capability/risk rules, not word lists.
    """

    capability: str = Field(description="Capability identifier, e.g., email.send, file.delete")
    risk_level: RiskLevel = Field(description="Risk level: low, medium, high, critical")
    requires_approval: bool = Field(description="Whether human approval is required")
    requires_secret_access: bool = Field(description="Whether secret/credential access is required")
    requires_external_side_effect: bool = Field(
        description="Whether action affects external systems"
    )
    data_scope: DataScope = Field(description="Type of data being accessed/modified")
    max_retries: int = Field(default=1, ge=0, description="Maximum retry attempts")
    requires_sandbox: bool = Field(
        default=False, description="Whether sandboxed execution is required"
    )
    allowed_tenants: list[str] | None = Field(
        default=None, description="Tenant allowlist, None means all"
    )
    denied_tenants: list[str] = Field(default_factory=list, description="Tenant denylist")
    rate_limit_per_minute: int | None = Field(
        default=None, ge=0, description="Rate limit per minute"
    )
    audit_log_required: bool = Field(default=True, description="Whether audit logging is required")
    description: str = Field(default="", description="Human-readable description")


@dataclass
class PolicyDecision:
    """Result of policy enforcement decision."""

    allowed: bool
    capability: str
    risk_level: RiskLevel
    requires_approval: bool
    requires_sandbox: bool
    reason: str
    policy: CapabilityPolicy
    metadata: dict[str, Any]


class CapabilityPolicyEngine:
    """Enforces structured capability policies.

    The classifier determines what capability/risk applies.
    This engine enforces the resulting structured decision.
    """

    def __init__(self, policies: list[CapabilityPolicy] | None = None) -> None:
        """Initialize the policy engine with capability policies.

        Args:
            policies: List of capability policies. If None, uses default policies.
        """
        self._policies = policies or self._default_policies()
        self._policy_index = {p.capability: p for p in self._policies}

    def _default_policies(self) -> list[CapabilityPolicy]:
        """Default capability policies for common Butler capabilities."""
        return [
            # Communication capabilities
            CapabilityPolicy(
                capability="email.send",
                risk_level=RiskLevel.MEDIUM,
                requires_approval=False,
                requires_secret_access=False,
                requires_external_side_effect=True,
                data_scope=DataScope.EXTERNAL_MESSAGE,
                max_retries=3,
                audit_log_required=True,
                description="Send email messages to external recipients",
            ),
            CapabilityPolicy(
                capability="sms.send",
                risk_level=RiskLevel.MEDIUM,
                requires_approval=False,
                requires_secret_access=False,
                requires_external_side_effect=True,
                data_scope=DataScope.EXTERNAL_MESSAGE,
                max_retries=3,
                audit_log_required=True,
                description="Send SMS messages to external recipients",
            ),
            CapabilityPolicy(
                capability="chat.send",
                risk_level=RiskLevel.LOW,
                requires_approval=False,
                requires_secret_access=False,
                requires_external_side_effect=False,
                data_scope=DataScope.USER_DATA,
                max_retries=2,
                audit_log_required=True,
                description="Send chat messages within the system",
            ),
            # File operations
            CapabilityPolicy(
                capability="file.read",
                risk_level=RiskLevel.LOW,
                requires_approval=False,
                requires_secret_access=False,
                requires_external_side_effect=False,
                data_scope=DataScope.USER_DATA,
                max_retries=2,
                audit_log_required=True,
                description="Read file contents",
            ),
            CapabilityPolicy(
                capability="file.write",
                risk_level=RiskLevel.MEDIUM,
                requires_approval=False,
                requires_secret_access=False,
                requires_external_side_effect=False,
                data_scope=DataScope.USER_DATA,
                max_retries=3,
                audit_log_required=True,
                description="Write or modify file contents",
            ),
            CapabilityPolicy(
                capability="file.delete",
                risk_level=RiskLevel.CRITICAL,
                requires_approval=True,
                requires_secret_access=False,
                requires_external_side_effect=True,
                data_scope=DataScope.USER_DATA,
                max_retries=0,
                audit_log_required=True,
                description="Delete files permanently",
            ),
            # Search capabilities
            CapabilityPolicy(
                capability="search.web",
                risk_level=RiskLevel.LOW,
                requires_approval=False,
                requires_secret_access=False,
                requires_external_side_effect=True,
                data_scope=DataScope.EXTERNAL_MESSAGE,
                max_retries=2,
                audit_log_required=True,
                description="Search the web for information",
            ),
            CapabilityPolicy(
                capability="search.internal",
                risk_level=RiskLevel.LOW,
                requires_approval=False,
                requires_secret_access=False,
                requires_external_side_effect=False,
                data_scope=DataScope.INTERNAL,
                max_retries=2,
                audit_log_required=True,
                description="Search internal knowledge base",
            ),
            # Memory capabilities
            CapabilityPolicy(
                capability="memory.read",
                risk_level=RiskLevel.LOW,
                requires_approval=False,
                requires_secret_access=False,
                requires_external_side_effect=False,
                data_scope=DataScope.USER_DATA,
                max_retries=2,
                audit_log_required=True,
                description="Read user memory/knowledge",
            ),
            CapabilityPolicy(
                capability="memory.write",
                risk_level=RiskLevel.MEDIUM,
                requires_approval=False,
                requires_secret_access=False,
                requires_external_side_effect=False,
                data_scope=DataScope.USER_DATA,
                max_retries=3,
                audit_log_required=True,
                description="Write to user memory/knowledge",
            ),
            # Device/IoT capabilities
            CapabilityPolicy(
                capability="device.control",
                risk_level=RiskLevel.HIGH,
                requires_approval=True,
                requires_secret_access=False,
                requires_external_side_effect=True,
                data_scope=DataScope.SYSTEM_CONFIG,
                max_retries=1,
                requires_sandbox=True,
                audit_log_required=True,
                description="Control physical devices or IoT systems",
            ),
            CapabilityPolicy(
                capability="device.read",
                risk_level=RiskLevel.MEDIUM,
                requires_approval=False,
                requires_secret_access=False,
                requires_external_side_effect=True,
                data_scope=DataScope.SYSTEM_CONFIG,
                max_retries=2,
                audit_log_required=True,
                description="Read device status or sensor data",
            ),
            # Financial capabilities
            CapabilityPolicy(
                capability="payment.process",
                risk_level=RiskLevel.CRITICAL,
                requires_approval=True,
                requires_secret_access=True,
                requires_external_side_effect=True,
                data_scope=DataScope.FINANCIAL,
                max_retries=0,
                audit_log_required=True,
                description="Process financial payments or transfers",
            ),
            CapabilityPolicy(
                capability="payment.read",
                risk_level=RiskLevel.HIGH,
                requires_approval=True,
                requires_secret_access=True,
                requires_external_side_effect=False,
                data_scope=DataScope.FINANCIAL,
                max_retries=1,
                audit_log_required=True,
                description="Read financial transaction history",
            ),
            # System capabilities
            CapabilityPolicy(
                capability="system.config",
                risk_level=RiskLevel.CRITICAL,
                requires_approval=True,
                requires_secret_access=True,
                requires_external_side_effect=True,
                data_scope=DataScope.SYSTEM_CONFIG,
                max_retries=0,
                audit_log_required=True,
                description="Modify system configuration",
            ),
            CapabilityPolicy(
                capability="system.admin",
                risk_level=RiskLevel.CRITICAL,
                requires_approval=True,
                requires_secret_access=True,
                requires_external_side_effect=True,
                data_scope=DataScope.SYSTEM_CONFIG,
                max_retries=0,
                audit_log_required=True,
                description="Perform administrative operations",
            ),
            # General purpose
            CapabilityPolicy(
                capability="general.query",
                risk_level=RiskLevel.LOW,
                requires_approval=False,
                requires_secret_access=False,
                requires_external_side_effect=False,
                data_scope=DataScope.INTERNAL,
                max_retries=2,
                audit_log_required=False,
                description="General informational queries",
            ),
        ]

    def evaluate(
        self,
        capability: str,
        tenant_id: str,
        context: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        """Evaluate whether a capability execution is allowed.

        Args:
            capability: The capability being requested
            tenant_id: The tenant making the request
            context: Additional context for the decision

        Returns:
            PolicyDecision with allowance status and reasoning
        """
        policy = self._policy_index.get(capability)

        if policy is None:
            # Unknown capability - conservative deny
            logger.warning(
                "unknown_capability_requested",
                capability=capability,
                tenant_id=tenant_id,
            )
            return PolicyDecision(
                allowed=False,
                capability=capability,
                risk_level=RiskLevel.MEDIUM,
                requires_approval=True,
                requires_sandbox=True,
                reason="Unknown capability - conservative deny",
                policy=self._default_unknown_policy(),
                metadata={"unknown_capability": True},
            )

        # Check tenant denylist
        if tenant_id in policy.denied_tenants:
            logger.info(
                "capability_denied_tenant_denylist",
                capability=capability,
                tenant_id=tenant_id,
            )
            return PolicyDecision(
                allowed=False,
                capability=capability,
                risk_level=policy.risk_level,
                requires_approval=policy.requires_approval,
                requires_sandbox=policy.requires_sandbox,
                reason=f"Tenant {tenant_id} is denied for this capability",
                policy=policy,
                metadata={"denylist": True},
            )

        # Check tenant allowlist (if specified)
        if policy.allowed_tenants is not None and tenant_id not in policy.allowed_tenants:
            logger.info(
                "capability_denied_tenant_not_in_allowlist",
                capability=capability,
                tenant_id=tenant_id,
            )
            return PolicyDecision(
                allowed=False,
                capability=capability,
                risk_level=policy.risk_level,
                requires_approval=policy.requires_approval,
                requires_sandbox=policy.requires_sandbox,
                reason=f"Tenant {tenant_id} is not in allowlist for this capability",
                policy=policy,
                metadata={"allowlist": True},
            )

        # Capability is allowed (approval may still be required based on risk level)
        logger.info(
            "capability_allowed",
            capability=capability,
            tenant_id=tenant_id,
            risk_level=policy.risk_level.value,
            requires_approval=policy.requires_approval,
        )

        return PolicyDecision(
            allowed=True,
            capability=capability,
            risk_level=policy.risk_level,
            requires_approval=policy.requires_approval,
            requires_sandbox=policy.requires_sandbox,
            reason="Capability allowed by policy",
            policy=policy,
            metadata={},
        )

    def get_policy(self, capability: str) -> CapabilityPolicy | None:
        """Get the policy for a specific capability.

        Args:
            capability: The capability identifier

        Returns:
            CapabilityPolicy if found, None otherwise
        """
        return self._policy_index.get(capability)

    def add_policy(self, policy: CapabilityPolicy) -> None:
        """Add or update a capability policy.

        Args:
            policy: The policy to add or update
        """
        self._policy_index[policy.capability] = policy
        # Update policies list if not already present
        if not any(p.capability == policy.capability for p in self._policies):
            self._policies.append(policy)

        logger.info("policy_added", capability=policy.capability)

    def remove_policy(self, capability: str) -> bool:
        """Remove a capability policy.

        Args:
            capability: The capability identifier

        Returns:
            True if removed, False if not found
        """
        if capability in self._policy_index:
            del self._policy_index[capability]
            self._policies = [p for p in self._policies if p.capability != capability]
            logger.info("policy_removed", capability=capability)
            return True
        return False

    def _default_unknown_policy(self) -> CapabilityPolicy:
        """Default policy for unknown capabilities."""
        return CapabilityPolicy(
            capability="unknown",
            risk_level=RiskLevel.MEDIUM,
            requires_approval=True,
            requires_secret_access=False,
            requires_external_side_effect=False,
            data_scope=DataScope.INTERNAL,
            max_retries=0,
            requires_sandbox=True,
            audit_log_required=True,
            description="Unknown capability - conservative default",
        )
