"""Butler Plugin/Skill Manifest V1 Schema.

Based on OpenClaw manifest philosophy.
"""

from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, Field, validator


class Capability(enum.StrEnum):
    """Core capabilities a plugin can declare."""

    TOOL = "tool"
    SKILL = "skill"
    PROVIDER = "provider"
    ROUTE = "route"
    SPEECH = "speech"
    REALTIME = "realtime"
    MEDIA = "media"
    SEARCH = "search"
    DEVICE = "device"
    UI = "ui"


class RiskTier(int, enum.Enum):
    """Risk tiers derived from capabilities."""

    TIER_0 = 0  # Content-only (Skills/Bundles)
    TIER_1 = 1  # Standard Providers/Helpers
    TIER_2 = 2  # Extended Routes/Native Tools
    TIER_3 = 3  # Host Control/Device Integration


class SkillManifest(BaseModel):
    """
    Butler openclaw.plugin.json equivalent.

    Validated at Gate B of the trust pipeline.
    """

    id: str = Field(..., description="Unique package identifier (e.g. clawhub:web-fetcher)")
    name: str
    version: str
    description: str | None = None
    author: str | None = None

    # Capability & Entrypoints
    capabilities: list[Capability] = Field(default_factory=list)
    entrypoint: str = Field(..., description="Main module path for the plugin")

    # Config & Secrets
    config_schema: dict[str, Any] = Field(default_factory=dict, alias="configSchema")
    required_secrets: list[str] = Field(default_factory=list, alias="requiredSecrets")

    # Runtime & Compatibility
    min_gateway_version: str = Field(..., alias="minGatewayVersion")
    plugin_api_version: str = Field(..., alias="pluginApiVersion")

    # Permissions & Isolation
    declared_egress: list[str] = Field(default_factory=list, alias="declaredEgress")
    sandbox_profile: str | None = Field(None, alias="sandboxProfile")
    risk_class: RiskTier = Field(RiskTier.TIER_0, alias="riskClass")

    # UI & UX
    ui_hints: dict[str, Any] = Field(default_factory=dict, alias="uiHints")

    # Health checks
    health_checks: list[str] = Field(default_factory=list, alias="healthChecks")

    class Config:
        populate_by_name = True
        extra = "forbid"
        use_enum_values = True

    @validator("risk_class", pre=True, always=True)
    def calculate_risk_tier(cls, v, values):
        """Automatically elevate risk tier based on capabilities if not explicitly set."""
        caps = values.get("capabilities", [])

        # Risk escalation logic
        calculated = RiskTier.TIER_0
        if Capability.PROVIDER in caps:
            calculated = max(calculated, RiskTier.TIER_1)
        if Capability.ROUTE in caps or Capability.SPEECH in caps:
            calculated = max(calculated, RiskTier.TIER_2)
        if Capability.DEVICE in caps or Capability.TOOL in caps:
            calculated = max(calculated, RiskTier.TIER_3)

        return max(v, calculated) if v is not None else calculated
