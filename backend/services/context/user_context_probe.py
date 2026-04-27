"""User context probe with privacy and consent gating.

Collects normalized, consent-gated user/device context for runtime decisions.
Never passes raw IP or raw User-Agent to LLM.
All context signals classified by sensitivity (low/medium/high).
Consent required for geolocation and sensitive device context.

Privacy Rules:
- Raw IP never passed to LLM
- Raw User-Agent never passed to LLM
- Geolocation requires explicit consent
- Sensitive device capabilities require consent
- All context is normalized before use
- Consent state is tracked and enforced
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class SignalSensitivity(str, Enum):
    """Sensitivity level for context signals."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConsentState(str, Enum):
    """User consent state for context collection."""

    GRANTED = "granted"
    DENIED = "denied"
    NOT_ASKED = "not_asked"
    EXPIRED = "expired"


class DeviceCapability(BaseModel):
    """Normalized device capability."""

    name: str
    supported: bool
    sensitivity: SignalSensitivity = SignalSensitivity.LOW


class Geolocation(BaseModel):
    """Normalized geolocation (coarse only)."""

    city: str | None = None
    region: str | None = None
    country: str | None = None
    timezone: str | None = None
    is_approximate: bool = True
    sensitivity: SignalSensitivity = SignalSensitivity.MEDIUM


class UserContextSnapshot(BaseModel):
    """Normalized user context snapshot.

    Request context:
    - request_id: Unique identifier
    - timestamp: When snapshot was taken
    - user_agent: Normalized user agent (not raw)

    Network context:
    - ip_address_hashed: SHA-256 hash of IP (never raw IP)
    - connection_type: 4g/5g/wifi/etc
    - effective_type: slow-2g/2g/3g/4g

    Device context:
    - platform: ios/android/windows/mac/linux/etc
    - browser: chrome/safari/firefox/edge/etc
    - screen_size: normalized dimensions
    - capabilities: device features with sensitivity

    Client hints (preferred):
    - sec_ch_ua: Normalized browser hints
    - sec_ch_ua_platform: Platform hint
    - sec_ch_ua_mobile: Mobile indicator
    - sec_ch_ua_arch: CPU architecture

    Locale:
    - language: Primary language code
    - region: Region code
    - timezone: User timezone

    Capabilities:
    - capabilities: List of device capabilities

    Privacy:
    - geolocation: Coarse location (if consented)
    - consent_state: Consent tracking
    - trust_score: Trust level (0-100)
    """

    # Request context
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    user_agent: str | None = None

    # Network context
    ip_address_hashed: str | None = None
    connection_type: str | None = None
    effective_type: str | None = None

    # Device context
    platform: str | None = None
    browser: str | None = None
    screen_size: tuple[int, int] | None = None
    capabilities: list[DeviceCapability] = Field(default_factory=list)

    # Client hints (preferred)
    sec_ch_ua: str | None = None
    sec_ch_ua_platform: str | None = None
    sec_ch_ua_mobile: bool | None = None
    sec_ch_ua_arch: str | None = None

    # Locale
    language: str | None = None
    region: str | None = None
    timezone: str | None = None

    # Privacy
    geolocation: Geolocation | None = None
    consent_state: ConsentState = ConsentState.NOT_ASKED
    trust_score: int = Field(default=50, ge=0, le=100)

    model_config = {"frozen": True}


class UserContextProbe:
    """Collect and normalize user context with privacy gating.

    Rules:
    - Never pass raw IP to LLM
    - Never pass raw User-Agent to LLM
    - Geolocation requires consent
    - Sensitive capabilities require consent
    - All context is normalized
    """

    def __init__(self) -> None:
        self._consent_state: ConsentState = ConsentState.NOT_ASKED

    def collect(
        self,
        request_context: dict[str, Any],
        consent_granted: bool = False,
    ) -> UserContextSnapshot:
        """Collect and normalize user context."""
        self._consent_state = ConsentState.GRANTED if consent_granted else ConsentState.DENIED

        snapshot = UserContextSnapshot(
            user_agent=self._normalize_user_agent(request_context.get("user_agent")),
            ip_address_hashed=self._hash_ip(request_context.get("ip_address")),
            connection_type=request_context.get("connection_type"),
            effective_type=request_context.get("effective_type"),
            platform=self._normalize_platform(request_context),
            browser=self._normalize_browser(request_context),
            screen_size=self._normalize_screen_size(request_context),
            sec_ch_ua=request_context.get("sec_ch_ua"),
            sec_ch_ua_platform=request_context.get("sec_ch_ua_platform"),
            sec_ch_ua_mobile=request_context.get("sec_ch_ua_mobile"),
            sec_ch_ua_arch=request_context.get("sec_ch_ua_arch"),
            language=request_context.get("language"),
            region=request_context.get("region"),
            timezone=request_context.get("timezone"),
            geolocation=self._collect_geolocation(request_context) if consent_granted else None,
            consent_state=self._consent_state,
            trust_score=self._calculate_trust_score(request_context),
        )

        return snapshot

    def _normalize_user_agent(self, user_agent: str | None) -> str | None:
        """Normalize user agent string."""
        if not user_agent:
            return None
        # Normalize to lowercase and strip version numbers for privacy
        parts = user_agent.lower().split()
        normalized = []
        for part in parts:
            # Remove version numbers and build identifiers
            if not any(c.isdigit() for c in part):
                normalized.append(part)
        return " ".join(normalized) if normalized else "unknown"

    def _hash_ip(self, ip_address: str | None) -> str | None:
        """Hash IP address for privacy."""
        if not ip_address:
            return None
        import hashlib

        return hashlib.sha256(ip_address.encode()).hexdigest()[:16]

    def _normalize_platform(self, request_context: dict[str, Any]) -> str | None:
        """Normalize platform from request context."""
        # Prefer Client Hints
        if request_context.get("sec_ch_ua_platform"):
            return request_context["sec_ch_ua_platform"].lower()
        # Fallback to User-Agent parsing
        ua = request_context.get("user_agent", "").lower()
        if "windows" in ua:
            return "windows"
        if "mac" in ua or "darwin" in ua:
            return "macos"
        if "linux" in ua:
            return "linux"
        if "android" in ua:
            return "android"
        if "ios" in ua or "iphone" in ua or "ipad" in ua:
            return "ios"
        return "unknown"

    def _normalize_browser(self, request_context: dict[str, Any]) -> str | None:
        """Normalize browser from request context."""
        ua = request_context.get("user_agent", "").lower()
        if "chrome" in ua and "edg" not in ua:
            return "chrome"
        if "firefox" in ua:
            return "firefox"
        if "safari" in ua and "chrome" not in ua:
            return "safari"
        if "edge" in ua or "edg" in ua:
            return "edge"
        return "unknown"

    def _normalize_screen_size(self, request_context: dict[str, Any]) -> tuple[int, int] | None:
        """Normalize screen size."""
        width = request_context.get("screen_width")
        height = request_context.get("screen_height")
        if width and height:
            # Normalize to standard buckets
            width_bucket = (int(width) // 100) * 100
            height_bucket = (int(height) // 100) * 100
            return (width_bucket, height_bucket)
        return None

    def _collect_geolocation(self, request_context: dict[str, Any]) -> Geolocation | None:
        """Collect coarse geolocation (requires consent)."""
        if self._consent_state != ConsentState.GRANTED:
            return None

        # Use IP-based coarse location (never precise GPS)
        # This would integrate with a geolocation service
        return Geolocation(
            city=request_context.get("city"),
            region=request_context.get("region"),
            country=request_context.get("country"),
            timezone=request_context.get("timezone"),
            is_approximate=True,
            sensitivity=SignalSensitivity.MEDIUM,
        )

    def _calculate_trust_score(self, request_context: dict[str, Any]) -> int:
        """Calculate trust score for the request."""
        score = 50  # Base score

        # Increase score for authenticated users
        if request_context.get("authenticated"):
            score += 30

        # Increase score for known devices
        if request_context.get("device_trusted"):
            score += 15

        # Decrease score for suspicious patterns
        if request_context.get("suspicious_activity"):
            score -= 20

        # Clamp to 0-100
        return max(0, min(100, score))

    def get_llm_safe_context(self, snapshot: UserContextSnapshot) -> dict[str, Any]:
        """Get context safe to pass to LLM.

        Rules:
        - Never include raw IP
        - Never include raw User-Agent
        - Only include consented geolocation
        - Normalize all values
        """
        return {
            "platform": snapshot.platform,
            "browser": snapshot.browser,
            "language": snapshot.language,
            "timezone": snapshot.timezone,
            "screen_size": snapshot.screen_size,
            "geolocation": {
                "city": snapshot.geolocation.city,
                "country": snapshot.geolocation.country,
            }
            if snapshot.geolocation and snapshot.consent_state == ConsentState.GRANTED
            else None,
            "trust_level": "high"
            if snapshot.trust_score >= 80
            else "medium"
            if snapshot.trust_score >= 50
            else "low",
        }
