"""Local context resolver for deterministic answers without LLM.

Answers simple context-aware questions from available context without invoking LLM.
This is the foundation for the deterministic fast path.

Supported intents:
- current_time
- current_date
- timezone
- coarse_location
- device_summary
- browser_summary
- locale_summary
- network_summary

Rules:
- If confidence >= threshold, answer deterministically.
- If confidence is low, answer with uncertainty.
- If permission is required, ask for permission.
- Never invoke LLM for questions answerable from local context.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class LocalIntent(str, Enum):
    """Local intent that can be answered without LLM."""

    CURRENT_TIME = "current_time"
    CURRENT_DATE = "current_date"
    TIMEZONE = "timezone"
    COARSE_LOCATION = "coarse_location"
    DEVICE_SUMMARY = "device_summary"
    BROWSER_SUMMARY = "browser_summary"
    LOCALE_SUMMARY = "locale_summary"
    NETWORK_SUMMARY = "network_summary"


class LocalAnswer(BaseModel):
    """Deterministic answer from local context."""

    intent: str
    answer: str
    confidence: float  # 0.0 to 1.0
    requires_llm: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class LocalContextResolver:
    """Resolve simple context queries deterministically without LLM.

    Critical example:
    Input: "what is the time"
    Given: client_runtime_context.timezone = "Asia/Kolkata"
    Expected: No LLM call. Return current time in Asia/Kolkata.
    """

    CONFIDENCE_THRESHOLD = 0.7

    def __init__(self) -> None:
        self._timezone: str | None = None
        self._locale: str | None = None
        self._device_info: dict[str, Any] = {}
        self._network_info: dict[str, Any] = {}
        self._location_info: dict[str, Any] = {}

    def set_timezone(self, timezone_str: str | None) -> None:
        """Set the timezone for time/date queries."""
        self._timezone = timezone_str

    def set_locale(self, locale_str: str | None) -> None:
        """Set the locale for locale queries."""
        self._locale = locale_str

    def set_device_info(self, device_info: dict[str, Any]) -> None:
        """Set device/browser context."""
        self._device_info = device_info

    def set_network_info(self, network_info: dict[str, Any]) -> None:
        """Set network context."""
        self._network_info = network_info

    def set_location_info(self, location_info: dict[str, Any]) -> None:
        """Set location context (coarse only)."""
        self._location_info = location_info

    def classify_intent(self, query: str) -> LocalIntent | None:
        """Classify if query can be answered locally."""
        query_lower = query.lower().strip()

        # Time/date queries
        if any(
            kw in query_lower for kw in ["what time", "current time", "time now", "what's the time"]
        ):
            return LocalIntent.CURRENT_TIME
        if any(kw in query_lower for kw in ["what date", "current date", "today", "what day"]):
            return LocalIntent.CURRENT_DATE
        if "timezone" in query_lower:
            return LocalIntent.TIMEZONE

        # Location queries
        if any(kw in query_lower for kw in ["where am i", "my location", "current location"]):
            return LocalIntent.COARSE_LOCATION

        # Device queries
        if any(kw in query_lower for kw in ["what device", "what browser", "what platform"]):
            return LocalIntent.DEVICE_SUMMARY

        # Locale queries
        if any(kw in query_lower for kw in ["what language", "my locale", "what locale"]):
            return LocalIntent.LOCALE_SUMMARY

        # Network queries
        if any(kw in query_lower for kw in ["internet speed", "network", "connection"]):
            return LocalIntent.NETWORK_SUMMARY

        return None

    def can_answer(self, query: str) -> bool:
        """Check if query can be answered deterministically."""
        intent = self.classify_intent(query)
        if intent is None:
            return False

        # Check if we have sufficient context for this intent
        if intent == LocalIntent.CURRENT_TIME and self._timezone:
            return True
        if intent == LocalIntent.CURRENT_DATE and self._timezone:
            return True
        if intent == LocalIntent.TIMEZONE and self._timezone:
            return True
        if intent == LocalIntent.COARSE_LOCATION and self._location_info:
            return True
        if intent == LocalIntent.DEVICE_SUMMARY and self._device_info:
            return True
        if intent == LocalIntent.LOCALE_SUMMARY and self._locale:
            return True
        if intent == LocalIntent.NETWORK_SUMMARY and self._network_info:
            return True

        return False

    def resolve(self, query: str) -> LocalAnswer:
        """Resolve query deterministically if possible."""
        intent = self.classify_intent(query)

        if intent is None:
            return LocalAnswer(
                intent="unknown",
                answer="",
                confidence=0.0,
                requires_llm=True,
            )

        if intent == LocalIntent.CURRENT_TIME:
            return self._resolve_current_time()
        if intent == LocalIntent.CURRENT_DATE:
            return self._resolve_current_date()
        if intent == LocalIntent.TIMEZONE:
            return self._resolve_timezone()
        if intent == LocalIntent.COARSE_LOCATION:
            return self._resolve_location()
        if intent == LocalIntent.DEVICE_SUMMARY:
            return self._resolve_device()
        if intent == LocalIntent.LOCALE_SUMMARY:
            return self._resolve_locale()
        if intent == LocalIntent.NETWORK_SUMMARY:
            return self._resolve_network()

        return LocalAnswer(
            intent=intent,
            answer="",
            confidence=0.0,
            requires_llm=True,
        )

    def _resolve_current_time(self) -> LocalAnswer:
        """Resolve current time deterministically."""
        if not self._timezone:
            return LocalAnswer(
                intent=LocalIntent.CURRENT_TIME,
                answer="",
                confidence=0.0,
                requires_llm=True,
                metadata={"reason": "timezone_not_set"},
            )

        try:
            import zoneinfo

            tz = zoneinfo.ZoneInfo(self._timezone)
            now = datetime.now(tz)
            answer = f"The current time is {now.strftime('%I:%M %p')} on {now.strftime('%A, %B %d, %Y')} in {self._timezone}."
            return LocalAnswer(
                intent=LocalIntent.CURRENT_TIME,
                answer=answer,
                confidence=1.0,
                requires_llm=False,
                metadata={
                    "timezone": self._timezone,
                    "iso": now.isoformat(),
                    "unix_ms": int(now.timestamp() * 1000),
                },
            )
        except Exception:
            # Fallback to UTC if timezone is invalid
            now = datetime.now(UTC)
            answer = f"The current time is {now.strftime('%I:%M %p')} UTC."
            return LocalAnswer(
                intent=LocalIntent.CURRENT_TIME,
                answer=answer,
                confidence=0.8,
                requires_llm=False,
                metadata={"timezone": "UTC", "fallback": True},
            )

    def _resolve_current_date(self) -> LocalAnswer:
        """Resolve current date deterministically."""
        if not self._timezone:
            return LocalAnswer(
                intent=LocalIntent.CURRENT_DATE,
                answer="",
                confidence=0.0,
                requires_llm=True,
                metadata={"reason": "timezone_not_set"},
            )

        try:
            import zoneinfo

            tz = zoneinfo.ZoneInfo(self._timezone)
            now = datetime.now(tz)
            answer = f"Today is {now.strftime('%A, %B %d, %Y')} in {self._timezone}."
            return LocalAnswer(
                intent=LocalIntent.CURRENT_DATE,
                answer=answer,
                confidence=1.0,
                requires_llm=False,
                metadata={"timezone": self._timezone, "date": now.strftime("%Y-%m-%d")},
            )
        except Exception:
            now = datetime.now(UTC)
            answer = f"Today is {now.strftime('%A, %B %d, %Y')} UTC."
            return LocalAnswer(
                intent=LocalIntent.CURRENT_DATE,
                answer=answer,
                confidence=0.8,
                requires_llm=False,
                metadata={"timezone": "UTC", "fallback": True},
            )

    def _resolve_timezone(self) -> LocalAnswer:
        """Resolve timezone query."""
        if not self._timezone:
            return LocalAnswer(
                intent=LocalIntent.TIMEZONE,
                answer="",
                confidence=0.0,
                requires_llm=True,
                metadata={"reason": "timezone_not_set"},
            )

        return LocalAnswer(
            intent=LocalIntent.TIMEZONE,
            answer=f"Your timezone is {self._timezone}.",
            confidence=1.0,
            requires_llm=False,
            metadata={"timezone": self._timezone},
        )

    def _resolve_location(self) -> LocalAnswer:
        """Resolve coarse location."""
        if not self._location_info:
            return LocalAnswer(
                intent=LocalIntent.COARSE_LOCATION,
                answer="",
                confidence=0.0,
                requires_llm=True,
                metadata={"reason": "location_not_set"},
            )

        city = self._location_info.get("city")
        country = self._location_info.get("country")
        region = self._location_info.get("region")

        parts = [p for p in [city, region, country] if p]
        if parts:
            answer = f"You appear to be in {', '.join(parts)}."
            confidence = 0.7  # IP-derived location is approximate
        else:
            answer = "Location information not available."
            confidence = 0.0
            return LocalAnswer(
                intent=LocalIntent.COARSE_LOCATION,
                answer=answer,
                confidence=confidence,
                requires_llm=True,
            )

        return LocalAnswer(
            intent=LocalIntent.COARSE_LOCATION,
            answer=answer,
            confidence=confidence,
            requires_llm=False,
            metadata=self._location_info,
        )

    def _resolve_device(self) -> LocalAnswer:
        """Resolve device/browser summary."""
        if not self._device_info:
            return LocalAnswer(
                intent=LocalIntent.DEVICE_SUMMARY,
                answer="",
                confidence=0.0,
                requires_llm=True,
                metadata={"reason": "device_info_not_set"},
            )

        platform = self._device_info.get("platform", "unknown")
        browser = self._device_info.get("browser", "unknown")
        answer = f"You're using {browser} on {platform}."
        return LocalAnswer(
            intent=LocalIntent.DEVICE_SUMMARY,
            answer=answer,
            confidence=0.9,
            requires_llm=False,
            metadata=self._device_info,
        )

    def _resolve_locale(self) -> LocalAnswer:
        """Resolve locale summary."""
        if not self._locale:
            return LocalAnswer(
                intent=LocalIntent.LOCALE_SUMMARY,
                answer="",
                confidence=0.0,
                requires_llm=True,
                metadata={"reason": "locale_not_set"},
            )

        answer = f"Your locale is {self._locale}."
        return LocalAnswer(
            intent=LocalIntent.LOCALE_SUMMARY,
            answer=answer,
            confidence=1.0,
            requires_llm=False,
            metadata={"locale": self._locale},
        )

    def _resolve_network(self) -> LocalAnswer:
        """Resolve network summary."""
        if not self._network_info:
            return LocalAnswer(
                intent=LocalIntent.NETWORK_SUMMARY,
                answer="",
                confidence=0.0,
                requires_llm=True,
                metadata={"reason": "network_info_not_set"},
            )

        effective_type = self._network_info.get("effective_type")
        if effective_type:
            answer = f"Your connection type is {effective_type}."
            confidence = 0.8
        else:
            answer = "Network information not available."
            confidence = 0.0
            return LocalAnswer(
                intent=LocalIntent.NETWORK_SUMMARY,
                answer=answer,
                confidence=confidence,
                requires_llm=True,
            )

        return LocalAnswer(
            intent=LocalIntent.NETWORK_SUMMARY,
            answer=answer,
            confidence=confidence,
            requires_llm=False,
            metadata=self._network_info,
        )
