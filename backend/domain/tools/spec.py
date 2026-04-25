"""ToolSpec - canonical tool specification with risk tiers and policy controls.

Phase T1: Updated to include all required fields for canonical tool integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class RiskTier(str, Enum):
    """Risk tier classification for tools.

    L0: safe read-only - no external calls, pure computation
    L1: personal data read / low-risk generated output
    L2: mutation / communication / scheduling / file write
    L3: code execution / browser automation / device control / sandbox / external side effect
    L4: financial / legal / destructive / credentialed action
    """

    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"


class ApprovalMode(str, Enum):
    """Approval mode for tool execution.

    none: No approval required (L0-L1 only)
    implicit: Implicit approval via tenant policy (L1-L2)
    explicit: Explicit human approval required (L2-L4)
    critical: Critical approval workflow (L4 only)
    """

    NONE = "none"
    IMPLICIT = "implicit"
    EXPLICIT = "explicit"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Canonical tool specification with comprehensive policy controls.

    Phase T1: Updated to include all required fields for canonical tool integration.

    Rule: No tool execution without ToolSpec validation.
    """

    # Identity
    name: str
    canonical_name: str
    description: str
    owner: str
    category: str
    version: str
    source_system: str

    # Policy
    risk_tier: RiskTier
    approval_mode: ApprovalMode
    required_permissions: frozenset[str]
    required_scopes: frozenset[str]

    # Execution
    input_schema: dict
    output_schema: dict
    timeout_seconds: int
    max_retries: int
    idempotent: bool
    side_effects: bool

    # Requirements
    sandbox_required: bool
    network_required: bool
    filesystem_required: bool
    credential_access_required: bool
    tenant_scope_required: bool

    # Safety
    audit_required: bool
    pii_possible: bool
    compensation_handler: str | None
    enabled: bool
    tags: frozenset[str] = field(default_factory=frozenset)

    def is_safe_to_auto_approve(self) -> bool:
        """Check if tool can be auto-approved without human review."""
        return self.approval_mode in {ApprovalMode.NONE, ApprovalMode.IMPLICIT} and self.risk_tier in {
            RiskTier.L0,
            RiskTier.L1,
        }

    def requires_human_approval(self) -> bool:
        """Check if tool requires human approval."""
        return self.approval_mode in {ApprovalMode.EXPLICIT, ApprovalMode.CRITICAL}

    def requires_critical_approval(self) -> bool:
        """Check if tool requires critical approval workflow."""
        return self.approval_mode == ApprovalMode.CRITICAL

    def is_deprecated(self) -> bool:
        """Check if tool is deprecated."""
        return not self.enabled

    def check_permissions(self, user_permissions: frozenset[str]) -> bool:
        """Check if user has required permissions."""
        return self.required_permissions.issubset(user_permissions)

    def check_scopes(self, user_scopes: frozenset[str]) -> bool:
        """Check if user has required scopes."""
        return self.required_scopes.issubset(user_scopes)

    @classmethod
    def create(
        cls,
        name: str,
        canonical_name: str,
        description: str,
        owner: str,
        category: str,
        version: str = "1.0.0",
        source_system: str = "canonical_service_tool",
        risk_tier: RiskTier = RiskTier.L1,
        approval_mode: ApprovalMode = ApprovalMode.NONE,
        required_permissions: frozenset[str] | None = None,
        required_scopes: frozenset[str] | None = None,
        input_schema: dict | None = None,
        output_schema: dict | None = None,
        timeout_seconds: int = 30,
        max_retries: int = 3,
        idempotent: bool = False,
        side_effects: bool = False,
        sandbox_required: bool = False,
        network_required: bool = False,
        filesystem_required: bool = False,
        credential_access_required: bool = False,
        tenant_scope_required: bool = True,
        audit_required: bool = True,
        pii_possible: bool = False,
        compensation_handler: str | None = None,
        enabled: bool = True,
        tags: frozenset[str] | None = None,
    ) -> ToolSpec:
        """Factory method to create a ToolSpec with sensible defaults.

        Args:
            name: Tool name (may differ from canonical_name)
            canonical_name: Canonical Butler tool name
            description: Human-readable description
            owner: Service owner (e.g., "tools", "memory", "ml")
            category: Tool category (e.g., "utility", "web", "file", "memory")
            version: Tool version
            source_system: Source system (e.g., "canonical_service_tool", "langchain_tool", "mcp_tool")
            risk_tier: Risk tier (L0-L4)
            approval_mode: Approval mode (none, implicit, explicit, critical)
            required_permissions: Permissions required to use this tool
            required_scopes: OAuth/tenant scopes required
            input_schema: JSON schema for input parameters
            output_schema: JSON schema for output
            timeout_seconds: Maximum execution time in seconds
            max_retries: Maximum retry attempts
            idempotent: Whether tool is idempotent
            side_effects: Whether tool has side effects
            sandbox_required: Whether tool must run in sandbox
            network_required: Whether tool requires network access
            filesystem_required: Whether tool requires filesystem access
            credential_access_required: Whether tool accesses credentials
            tenant_scope_required: Whether tool requires tenant scope
            audit_required: Whether tool execution must be audited
            pii_possible: Whether tool may handle PII
            compensation_handler: Compensation handler function name
            enabled: Whether tool is enabled
            tags: Tool tags for classification

        Returns:
            ToolSpec instance
        """
        return cls(
            name=name,
            canonical_name=canonical_name,
            description=description,
            owner=owner,
            category=category,
            version=version,
            source_system=source_system,
            risk_tier=risk_tier,
            approval_mode=approval_mode,
            required_permissions=required_permissions or frozenset(),
            required_scopes=required_scopes or frozenset(),
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            idempotent=idempotent,
            side_effects=side_effects,
            sandbox_required=sandbox_required,
            network_required=network_required,
            filesystem_required=filesystem_required,
            credential_access_required=credential_access_required,
            tenant_scope_required=tenant_scope_required,
            audit_required=audit_required,
            pii_possible=pii_possible,
            compensation_handler=compensation_handler,
            enabled=enabled,
            tags=tags or frozenset(),
        )

    @classmethod
    def l0_safe(
        cls,
        name: str,
        canonical_name: str | None = None,
        description: str = "",
        owner: str = "tools",
        category: str = "utility",
    ) -> ToolSpec:
        """Create L0 safe tool spec (no approval, no sandbox, pure computation)."""
        return cls.create(
            name=name,
            canonical_name=canonical_name or name,
            description=description,
            owner=owner,
            category=category,
            risk_tier=RiskTier.L0,
            approval_mode=ApprovalMode.NONE,
            sandbox_required=False,
            network_required=False,
            filesystem_required=False,
            side_effects=False,
            idempotent=True,
        )

    @classmethod
    def l1_readonly(
        cls,
        name: str,
        canonical_name: str | None = None,
        description: str = "",
        owner: str = "tools",
        category: str = "utility",
    ) -> ToolSpec:
        """Create L1 read-only tool spec (no approval, no sandbox, low risk)."""
        return cls.create(
            name=name,
            canonical_name=canonical_name or name,
            description=description,
            owner=owner,
            category=category,
            risk_tier=RiskTier.L1,
            approval_mode=ApprovalMode.NONE,
            sandbox_required=False,
            network_required=False,
            filesystem_required=False,
            side_effects=False,
            idempotent=True,
        )

    @classmethod
    def l2_write(
        cls,
        name: str,
        canonical_name: str | None = None,
        description: str = "",
        owner: str = "tools",
        category: str = "file",
        required_permissions: frozenset[str] | None = None,
        approval_mode: ApprovalMode = ApprovalMode.IMPLICIT,
    ) -> ToolSpec:
        """Create L2 write tool spec (implicit approval, mutation)."""
        return cls.create(
            name=name,
            canonical_name=canonical_name or name,
            description=description,
            owner=owner,
            category=category,
            risk_tier=RiskTier.L2,
            approval_mode=approval_mode,
            required_permissions=required_permissions,
            sandbox_required=False,
            network_required=False,
            filesystem_required=True,
            side_effects=True,
            idempotent=False,
        )

    @classmethod
    def l3_destructive(
        cls,
        name: str,
        canonical_name: str | None = None,
        description: str = "",
        owner: str = "tools",
        category: str = "code",
        required_permissions: frozenset[str] | None = None,
        sandbox_required: bool = True,
    ) -> ToolSpec:
        """Create L3 destructive tool spec (explicit approval, sandbox)."""
        return cls.create(
            name=name,
            canonical_name=canonical_name or name,
            description=description,
            owner=owner,
            category=category,
            risk_tier=RiskTier.L3,
            approval_mode=ApprovalMode.EXPLICIT,
            required_permissions=required_permissions,
            sandbox_required=sandbox_required,
            network_required=True,
            filesystem_required=True,
            side_effects=True,
            idempotent=False,
        )

    @classmethod
    def l4_critical(
        cls,
        name: str,
        canonical_name: str | None = None,
        description: str = "",
        owner: str = "tools",
        category: str = "financial",
        required_permissions: frozenset[str] | None = None,
        sandbox_required: bool = True,
    ) -> ToolSpec:
        """Create L4 critical tool spec (critical approval, sandbox)."""
        return cls.create(
            name=name,
            canonical_name=canonical_name or name,
            description=description,
            owner=owner,
            category=category,
            risk_tier=RiskTier.L4,
            approval_mode=ApprovalMode.CRITICAL,
            required_permissions=required_permissions,
            sandbox_required=sandbox_required,
            network_required=True,
            filesystem_required=True,
            side_effects=True,
            idempotent=False,
            credential_access_required=True,
            pii_possible=True,
        )
