"""
Locale Service - Locale Detection and Preference Management

Detects user locale from requests and manages user locale preferences.
Supports Accept-Language header parsing and user preference storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from services.i18n.translation_service import Locale

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LocalePreference:
    """User locale preference."""

    user_id: str
    locale: Locale
    detected_at: str | None  # ISO country code if detected
    manual_override: bool


class LocaleService:
    """
    Locale service for locale detection and preference management.

    Features:
    - Accept-Language header parsing
    - User preference storage
    - Locale detection from IP
    - Preference overrides
    """

    def __init__(self) -> None:
        """Initialize locale service."""
        self._user_preferences: dict[str, LocalePreference] = {}
        self._default_locale = Locale.EN_US

    def parse_accept_language(self, accept_language: str) -> Locale:
        """
        Parse Accept-Language header to determine locale.

        Args:
            accept_language: Accept-Language header value

        Returns:
            Detected locale
        """
        if not accept_language:
            return self._default_locale

        # Parse Accept-Language header (e.g., "en-US,en;q=0.9,es;q=0.8")
        locales = []

        for part in accept_language.split(","):
            part = part.strip()
            if not part:
                continue

            # Split language and quality
            if ";" in part:
                lang, q = part.split(";")
                lang = lang.strip()
                q = q.strip()
                if q.startswith("q="):
                    try:
                        quality = float(q[2:])
                    except ValueError:
                        quality = 1.0
                else:
                    quality = 1.0
            else:
                lang = part
                quality = 1.0

            # Convert to our Locale format
            normalized = self._normalize_locale(lang)
            if normalized:
                locales.append((normalized, quality))

        # Sort by quality
        locales.sort(key=lambda x: x[1], reverse=True)

        if locales:
            return locales[0][0]

        return self._default_locale

    def _normalize_locale(self, locale: str) -> Locale | None:
        """
        Normalize locale string to Locale enum.

        Args:
            locale: Locale string (e.g., "en-US", "en_US")

        Returns:
            Normalized Locale or None
        """
        # Replace hyphens with underscores
        normalized = locale.replace("-", "_").upper()

        try:
            return Locale(normalized)
        except ValueError:
            # Try to match language part only
            lang_code = normalized.split("_")[0]

            for locale_enum in Locale:
                if locale_enum.value.startswith(lang_code):
                    return locale_enum

            return None

    def detect_locale_from_ip(self, ip_address: str) -> Locale | None:
        """
        Detect locale from IP address (country-based).

        Args:
            ip_address: Client IP address

        Returns:
            Detected locale or None
        """
        # In production, this would use a GeoIP database
        # For now, return None and rely on Accept-Language
        logger.debug(
            "locale_detection_from_ip",
            ip_address=ip_address,
        )
        return None

    def set_user_preference(
        self,
        user_id: str,
        locale: Locale,
        manual_override: bool = True,
    ) -> LocalePreference:
        """
        Set user locale preference.

        Args:
            user_id: User identifier
            locale: Preferred locale
            manual_override: Whether this is a manual override

        Returns:
            Locale preference
        """
        preference = LocalePreference(
            user_id=user_id,
            locale=locale,
            detected_at=None,
            manual_override=manual_override,
        )

        self._user_preferences[user_id] = preference

        logger.info(
            "user_locale_preference_set",
            user_id=user_id,
            locale=locale,
            manual_override=manual_override,
        )

        return preference

    def get_user_preference(self, user_id: str) -> Locale | None:
        """
        Get user's preferred locale.

        Args:
            user_id: User identifier

        Returns:
            Preferred locale or None
        """
        preference = self._user_preferences.get(user_id)
        if preference:
            return preference.locale
        return None

    def resolve_locale(
        self,
        user_id: str | None = None,
        accept_language: str | None = None,
        ip_address: str | None = None,
    ) -> Locale:
        """
        Resolve locale using multiple sources in priority order.

        Priority:
        1. User preference (manual override)
        2. Accept-Language header
        3. IP-based detection
        4. Default locale

        Args:
            user_id: User identifier
            accept_language: Accept-Language header
            ip_address: Client IP address

        Returns:
            Resolved locale
        """
        # Check user preference
        if user_id:
            user_locale = self.get_user_preference(user_id)
            if user_locale:
                preference = self._user_preferences[user_id]
                if preference.manual_override:
                    return user_locale

        # Check Accept-Language header
        if accept_language:
            header_locale = self.parse_accept_language(accept_language)
            if header_locale != self._default_locale:
                return header_locale

        # Check IP-based detection
        if ip_address:
            ip_locale = self.detect_locale_from_ip(ip_address)
            if ip_locale:
                return ip_locale

        # Fall back to default
        return self._default_locale

    def set_default_locale(self, locale: Locale) -> None:
        """
        Set the default locale.

        Args:
            locale: Default locale
        """
        self._default_locale = locale
        logger.info(
            "default_locale_set",
            locale=locale,
        )

    def get_default_locale(self) -> Locale:
        """Get the default locale."""
        return self._default_locale

    def remove_user_preference(self, user_id: str) -> bool:
        """
        Remove user locale preference.

        Args:
            user_id: User identifier

        Returns:
            True if removed
        """
        if user_id in self._user_preferences:
            del self._user_preferences[user_id]
            logger.info(
                "user_locale_preference_removed",
                user_id=user_id,
            )
            return True
        return False

    def get_locale_stats(self) -> dict[str, Any]:
        """
        Get locale statistics.

        Returns:
            Locale statistics
        """
        total_users = len(self._user_preferences)

        locale_counts: dict[str, int] = {}
        for preference in self._user_preferences.values():
            locale_counts[preference.locale.value] = (
                locale_counts.get(preference.locale.value, 0) + 1
            )

        return {
            "total_users_with_preferences": total_users,
            "locale_distribution": locale_counts,
            "default_locale": self._default_locale,
        }
