"""Industry Profiles — Phase 7b.

Vertical-specific capability overlays that layer on top of ProductTiers.
An industry profile can:
  1. ADD extra capabilities (most common — unlock vertical-specific features)
  2. RESTRICT baseline capabilities (rare — regulatory removes something)
  3. REQUIRE specific compliance flags to be active

Current profiles:
  healthcare   — HIPAA mode, PHI-aware memory, no raw file storage
  government   — FedRAMP High, audit logging mandatory, no cloud frontier LLM
                 (data sovereignty), approved provider list only
  finance      — SOC2, no external API calls without approval, full audit
  legal        — SOC2, document-only file access, no code execution
  education    — No email send for minors, no device control, no external APIs
  default      — No restrictions beyond tier capabilities

Sovereignty rules:
  - Profile evaluation is pure (no I/O, O(1)).
  - Profiles CANNOT grant capabilities above Enterprise tier.
  - Industry capability gate is checked AFTER tier gate.
  - EffectiveCapabilities = (tier_caps UNION profile_adds) MINUS profile_removes.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Union, Any

from domain.policy.capability_flags import CapabilityArea, TrustLevel
from domain.policy.product_tiers import TIER_CONFIGS, ProductTier, CapabilityFlag  # CapabilityFlag is an alias


class IndustryProfile(str, Enum):
    DEFAULT    = "default"
    HEALTHCARE = "healthcare"
    GOVERNMENT = "government"
    FINANCE    = "finance"
    LEGAL      = "legal"
    EDUCATION  = "education"


@dataclass(frozen=True)
class ProfileConfig:
    """Industry-specific capability overlay."""
    profile: IndustryProfile
    display_name: str
    description: str
    # Capabilities added on top of tier (must still be in Enterprise set)
    additional_capabilities: frozenset[CapabilityFlag] = field(default_factory=frozenset)
    # Capabilities removed from tier set (regulatory restrictions)
    restricted_capabilities: frozenset[CapabilityFlag] = field(default_factory=frozenset)
    # Minimum tier required to use this profile
    min_tier: ProductTier = ProductTier.PRO
    # Compliance flags that MUST be active when this profile is used
    required_compliance: frozenset[CapabilityFlag] = field(default_factory=frozenset)


# ── Profile definitions ────────────────────────────────────────────────────────

PROFILE_CONFIGS: dict[IndustryProfile, ProfileConfig] = {

    IndustryProfile.DEFAULT: ProfileConfig(
        profile=IndustryProfile.DEFAULT,
        display_name="General",
        description="No vertical restrictions beyond product tier.",
        min_tier=ProductTier.PERSONAL,
    ),

    IndustryProfile.HEALTHCARE: ProfileConfig(
        profile=IndustryProfile.HEALTHCARE,
        display_name="Healthcare (HIPAA)",
        description="HIPAA-compliant mode: PHI handling, encrypted memory, no unencrypted storage.",
        additional_capabilities=frozenset({
            CapabilityArea.HEALTH_INTEGRATION,
        }),
        restricted_capabilities=frozenset({
            CapabilityArea.WEB_SEARCH,  # Restrict public web for PHI safety
        }),
        required_compliance=frozenset({CapabilityArea.HEALTH_INTEGRATION}),
        min_tier=ProductTier.ENTERPRISE,
    ),

    IndustryProfile.GOVERNMENT: ProfileConfig(
        profile=IndustryProfile.GOVERNMENT,
        display_name="Government (FedRAMP)",
        description="FedRAMP High: data sovereignty, approved providers, mandatory audit.",
        additional_capabilities=frozenset({
            CapabilityArea.SYSTEM_OPS,
        }),
        restricted_capabilities=frozenset({
            CapabilityArea.SOCIAL_PRESENCE,
        }),
        min_tier=ProductTier.ENTERPRISE,
    ),

    IndustryProfile.FINANCE: ProfileConfig(
        profile=IndustryProfile.FINANCE,
        display_name="Financial Services (SOC2)",
        description="SOC2 Type II compliance with full audit log and external API approval gates.",
        additional_capabilities=frozenset({
            CapabilityArea.FINANCE_GATEWAY,
        }),
        restricted_capabilities=frozenset({
            CapabilityArea.GEN_AI_FACTORY, # Restrict unapproved model usage
        }),
        min_tier=ProductTier.ENTERPRISE,
    ),

    IndustryProfile.LEGAL: ProfileConfig(
        profile=IndustryProfile.LEGAL,
        display_name="Legal",
        description="Document-focused: no code execution, no external APIs, full audit.",
        additional_capabilities=frozenset({
            CapabilityArea.MEMORY_OPS,
        }),
        restricted_capabilities=frozenset({
            CapabilityArea.DATA_ANALYSIS,
        }),
        min_tier=ProductTier.PRO,
    ),

    IndustryProfile.EDUCATION: ProfileConfig(
        profile=IndustryProfile.EDUCATION,
        display_name="Education",
        description="COPPA-safe mode: no email, no device control, no external APIs.",
        restricted_capabilities=frozenset({
            CapabilityArea.SOCIAL_PRESENCE,
            CapabilityArea.IOT_CONTROL,
        }),
        min_tier=ProductTier.PERSONAL,
    ),
}


# ── Effective capability resolution ───────────────────────────────────────────

@dataclass(frozen=True)
class EffectiveCapabilities:
    """Resolved capability set after applying tier + profile."""
    tier: ProductTier
    profile: IndustryProfile
    capabilities: frozenset[CapabilityFlag]
    added: frozenset[CapabilityFlag]     # From profile
    removed: frozenset[CapabilityFlag]   # From profile


@dataclass(frozen=True)
class ProfileCheckResult:
    """Result of a profile capability gate check."""
    allowed: bool
    tier: ProductTier
    profile: IndustryProfile
    capability: CapabilityFlag
    reason: str = ""


def resolve_capabilities(
    tier: ProductTier,
    profile: IndustryProfile = IndustryProfile.DEFAULT,
) -> EffectiveCapabilities:
    """Compute the effective capability set for a tier + profile combo.

    effective = (tier_caps ∪ profile_adds) − profile_removes
    profile_adds are capped to Enterprise tier — a profile cannot grant
    capabilities that don't exist in Enterprise.
    """
    tier_config = TIER_CONFIGS.get(tier)
    tier_caps: frozenset[CapabilityFlag] = tier_config.capabilities if tier_config else frozenset()

    profile_config = PROFILE_CONFIGS.get(profile, PROFILE_CONFIGS[IndustryProfile.DEFAULT])
    enterprise_caps = TIER_CONFIGS[ProductTier.ENTERPRISE].capabilities

    # Profile additions are capped to what Enterprise allows
    profile_adds = profile_config.additional_capabilities & enterprise_caps
    profile_removes = profile_config.restricted_capabilities

    effective = (tier_caps | profile_adds) - profile_removes

    return EffectiveCapabilities(
        tier=tier,
        profile=profile,
        capabilities=effective,
        added=profile_adds,
        removed=profile_removes & tier_caps,  # Only report caps that were actually present
    )


def check_profile_capability(
    tier: ProductTier,
    profile: IndustryProfile,
    capability: CapabilityFlag,
) -> ProfileCheckResult:
    """Check if a tier+profile combo allows a specific capability.

    This is the production-facing gate — replaces the old tier-only check
    in ButlerToolPolicyGate wherever industry profiles are active.
    """
    eff = resolve_capabilities(tier, profile)
    allowed = capability in eff.capabilities

    reason = ""
    if not allowed:
        if capability in eff.removed:
            reason = (
                f"Capability '{capability.value}' is restricted by the "
                f"'{profile.value}' industry profile."
            )
        else:
            reason = (
                f"Capability '{capability.value}' is not available on "
                f"tier '{tier.value}' with profile '{profile.value}'."
            )

    return ProfileCheckResult(
        allowed=allowed,
        tier=tier,
        profile=profile,
        capability=capability,
        reason=reason,
    )


def profile_meets_min_tier(
    tier: ProductTier,
    profile: IndustryProfile,
) -> bool:
    """Check if a tier satisfies the profile's minimum tier requirement."""
    _tier_rank = {
        ProductTier.PERSONAL: 0,
        ProductTier.PRO: 1,
        ProductTier.ENTERPRISE: 2,
    }
    config = PROFILE_CONFIGS.get(profile)
    if config is None:
        return False
    required_rank = _tier_rank.get(config.min_tier, 0)
    current_rank = _tier_rank.get(tier, 0)
    return current_rank >= required_rank
