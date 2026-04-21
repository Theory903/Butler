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

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Union, Any
from domain.policy.capability_flags import CapabilityArea, TrustLevel


class ProductTier(str, Enum):
    PERSONAL   = "personal"
    PRO        = "pro"
    ENTERPRISE = "enterprise"


# CapabilityFlag is aliased to CapabilityArea for backward compatibility
CapabilityFlag = CapabilityArea


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
    CapabilityArea.WEB_SEARCH,
    CapabilityArea.SEARCH_ENGINE,
    CapabilityArea.MESSAGING,
    CapabilityArea.MEMORY_OPS,
    CapabilityArea.GEN_AI_FACTORY,
})

_PRO_CAPS = _PERSONAL_CAPS | frozenset({
    CapabilityArea.SOCIAL_PRESENCE,
    CapabilityArea.CALENDAR_OPS,
    CapabilityArea.DATA_ANALYSIS,
    CapabilityArea.VISION_REASONING,
    CapabilityArea.AUDIO_FLOW,
    CapabilityArea.DELEGATION,
    CapabilityArea.PLATFORM_PLUGINS,
    CapabilityArea.SYSTEM_OPS,
    CapabilityArea.STREAMS_MGMT,
})

_ENTERPRISE_CAPS = _PRO_CAPS | frozenset({
    CapabilityArea.MEETING_ASSISTANT,
    CapabilityArea.IOT_CONTROL,
    CapabilityArea.FINANCE_GATEWAY,
    CapabilityArea.HEALTH_INTEGRATION,
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


def get_tier_config(tier: ProductTier) -> Optional[TierConfig]:
    return TIER_CONFIGS.get(tier)


def capabilities_for_tier(tier: ProductTier) -> list[str]:
    config = TIER_CONFIGS.get(tier)
    if config is None:
        return []
    return sorted(cap.value for cap in config.capabilities)
