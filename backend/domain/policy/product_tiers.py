"""Butler Product Tiers — Phase 7.

Defines the three-tier product hierarchy and per-tier capability gates.
Every capability check is a pure function — no DB, no HTTP, no Redis.

Tiers:
  PERSONAL     — individual user, 10K RPM, 1 device
  PRO          — power user, 100K RPM, 5 devices, full memory
  ENTERPRISE   — org accounts, 1M RPM, unlimited devices, RBAC, audit

Capability matrix:
  Each tier has a set of allowed capabilities. The gate is checked by
  ButlerToolPolicyGate.check_product_tier() before any tool call.

Industry profiles layer on top of tiers to add vertical-specific
capability unlocks (e.g. HIPAA mode for healthcare, FedRAMP for gov).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProductTier(str, Enum):
    PERSONAL   = "personal"
    PRO        = "pro"
    ENTERPRISE = "enterprise"


class CapabilityFlag(str, Enum):
    """Fine-grained capability flags checked during tool execution."""
    # Memory
    LONG_TERM_MEMORY       = "long_term_memory"
    MEMORY_SEARCH          = "memory_search"
    CROSS_SESSION_MEMORY   = "cross_session_memory"

    # Tools
    WEB_SEARCH             = "web_search"
    FILE_READ              = "file_read"
    FILE_WRITE             = "file_write"
    CODE_EXECUTION         = "code_execution"
    EXTERNAL_API_CALLS     = "external_api_calls"
    EMAIL_SEND             = "email_send"
    CALENDAR_WRITE         = "calendar_write"
    CRON_JOBS              = "cron_jobs"
    DEVICE_CONTROL         = "device_control"
    MULTI_MODAL            = "multi_modal"

    # ML
    LOCAL_LLM              = "local_llm"
    CLOUD_FRONTIER_LLM     = "cloud_frontier_llm"
    TRI_ATTENTION          = "tri_attention"
    CUSTOM_MODELS          = "custom_models"

    # Platform
    MULTI_DEVICE           = "multi_device"
    MULTI_USER             = "multi_user"
    RBAC                   = "rbac"
    AUDIT_FULL             = "audit_full"
    ADMIN_PLANE            = "admin_plane"
    SSO                    = "sso"
    DATA_EXPORT            = "data_export"
    API_ACCESS             = "api_access"
    WEBHOOKS               = "webhooks"
    MCP_BRIDGE             = "mcp_bridge"

    # Compliance
    HIPAA_MODE             = "hipaa_mode"
    FEDRAMP_MODE           = "fedramp_mode"
    SOC2_AUDIT             = "soc2_audit"


@dataclass(frozen=True)
class TierConfig:
    """Per-tier capability set and rate limits."""
    tier: ProductTier
    display_name: str
    rpm_limit: int                           # requests per minute
    max_devices: int                         # -1 = unlimited
    max_users: int                           # -1 = unlimited
    storage_gb: float
    capabilities: frozenset[CapabilityFlag]
    daily_llm_calls: int                     # -1 = unlimited
    description: str = ""


# ── Capability matrix ──────────────────────────────────────────────────────────

_PERSONAL_CAPS = frozenset({
    CapabilityFlag.WEB_SEARCH,
    CapabilityFlag.FILE_READ,
    CapabilityFlag.EMAIL_SEND,
    CapabilityFlag.LONG_TERM_MEMORY,
    CapabilityFlag.MEMORY_SEARCH,
    CapabilityFlag.CLOUD_FRONTIER_LLM,
    CapabilityFlag.MULTI_MODAL,
    CapabilityFlag.API_ACCESS,
})

_PRO_CAPS = _PERSONAL_CAPS | frozenset({
    CapabilityFlag.FILE_WRITE,
    CapabilityFlag.CODE_EXECUTION,
    CapabilityFlag.EXTERNAL_API_CALLS,
    CapabilityFlag.CALENDAR_WRITE,
    CapabilityFlag.CRON_JOBS,
    CapabilityFlag.CROSS_SESSION_MEMORY,
    CapabilityFlag.LOCAL_LLM,
    CapabilityFlag.TRI_ATTENTION,
    CapabilityFlag.MULTI_DEVICE,
    CapabilityFlag.DATA_EXPORT,
    CapabilityFlag.WEBHOOKS,
    CapabilityFlag.MCP_BRIDGE,
})

_ENTERPRISE_CAPS = _PRO_CAPS | frozenset({
    CapabilityFlag.DEVICE_CONTROL,
    CapabilityFlag.CUSTOM_MODELS,
    CapabilityFlag.MULTI_USER,
    CapabilityFlag.RBAC,
    CapabilityFlag.AUDIT_FULL,
    CapabilityFlag.ADMIN_PLANE,
    CapabilityFlag.SSO,
    CapabilityFlag.HIPAA_MODE,
    CapabilityFlag.FEDRAMP_MODE,
    CapabilityFlag.SOC2_AUDIT,
})

TIER_CONFIGS: dict[ProductTier, TierConfig] = {
    ProductTier.PERSONAL: TierConfig(
        tier=ProductTier.PERSONAL,
        display_name="Butler Personal",
        rpm_limit=10_000,
        max_devices=1,
        max_users=1,
        storage_gb=5.0,
        capabilities=_PERSONAL_CAPS,
        daily_llm_calls=100,
        description="Individual AI assistant with web search, memory, and email.",
    ),
    ProductTier.PRO: TierConfig(
        tier=ProductTier.PRO,
        display_name="Butler Pro",
        rpm_limit=100_000,
        max_devices=5,
        max_users=1,
        storage_gb=50.0,
        capabilities=_PRO_CAPS,
        daily_llm_calls=1_000,
        description="Power user everything pack: code execution, cron, MCP, local LLM.",
    ),
    ProductTier.ENTERPRISE: TierConfig(
        tier=ProductTier.ENTERPRISE,
        display_name="Butler Enterprise",
        rpm_limit=1_000_000,
        max_devices=-1,
        max_users=-1,
        storage_gb=1000.0,
        capabilities=_ENTERPRISE_CAPS,
        daily_llm_calls=-1,
        description="Organization-wide AI with RBAC, HIPAA, FedRAMP, and full audit.",
    ),
}


# ── Capability gate ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TierCheckResult:
    allowed: bool
    tier: ProductTier
    capability: CapabilityFlag
    reason: str = ""


def check_capability(
    tier: ProductTier,
    capability: CapabilityFlag,
) -> TierCheckResult:
    """Pure function — check if a tier has a capability.

    Usage:
        result = check_capability(ProductTier.PRO, CapabilityFlag.CODE_EXECUTION)
        if not result.allowed:
            raise ForbiddenProblem(detail=result.reason)
    """
    config = TIER_CONFIGS.get(tier)
    if config is None:
        return TierCheckResult(
            allowed=False,
            tier=tier,
            capability=capability,
            reason=f"Unknown tier: {tier}",
        )

    allowed = capability in config.capabilities
    reason = "" if allowed else (
        f"Capability '{capability.value}' requires Butler Pro or Enterprise. "
        f"Current tier: {tier.value}."
    )
    return TierCheckResult(allowed=allowed, tier=tier, capability=capability, reason=reason)


def get_tier_config(tier: ProductTier) -> TierConfig | None:
    return TIER_CONFIGS.get(tier)


def capabilities_for_tier(tier: ProductTier) -> list[str]:
    config = TIER_CONFIGS.get(tier)
    if config is None:
        return []
    return sorted(cap.value for cap in config.capabilities)
