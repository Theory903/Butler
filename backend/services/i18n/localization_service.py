"""
Localization Service - Localized Error Messages and UI Strings

Integrates translation and locale services to provide localized responses.
Supports error message localization and UI string translation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from services.i18n.locale_service import LocaleService
from services.i18n.translation_service import Locale, TranslationService

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LocalizedError:
    """Localized error message."""

    key: str
    message: str
    locale: Locale
    params: dict[str, Any]


class LocalizationService:
    """
    Localization service for localized error messages and UI strings.

    Features:
    - Localized error messages
    - UI string translation
    - Parameter substitution
    - Locale-aware responses
    """

    def __init__(
        self,
        translation_service: TranslationService | None = None,
        locale_service: LocaleService | None = None,
    ) -> None:
        """Initialize localization service."""
        self._translation_service = translation_service or TranslationService()
        self._locale_service = locale_service or LocaleService()

    def localize_error(
        self,
        error_key: str,
        user_id: str | None = None,
        accept_language: str | None = None,
        ip_address: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> LocalizedError:
        """
        Localize an error message for the user.

        Args:
            error_key: Error message key
            user_id: User identifier
            accept_language: Accept-Language header
            ip_address: Client IP address
            params: Parameters for substitution

        Returns:
            Localized error
        """
        locale = self._locale_service.resolve_locale(
            user_id=user_id,
            accept_language=accept_language,
            ip_address=ip_address,
        )

        if params:
            message = self._translation_service.translate_with_params(
                key=error_key,
                params=params,
                locale=locale,
            )
        else:
            message = self._translation_service.translate(
                key=error_key,
                locale=locale,
            )

        return LocalizedError(
            key=error_key,
            message=message,
            locale=locale,
            params=params or {},
        )

    def localize_ui_string(
        self,
        key: str,
        user_id: str | None = None,
        accept_language: str | None = None,
        ip_address: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        """
        Localize a UI string.

        Args:
            key: UI string key
            user_id: User identifier
            accept_language: Accept-Language header
            ip_address: Client IP address
            params: Parameters for substitution

        Returns:
            Localized string
        """
        locale = self._locale_service.resolve_locale(
            user_id=user_id,
            accept_language=accept_language,
            ip_address=ip_address,
        )

        if params:
            return self._translation_service.translate_with_params(
                key=key,
                params=params,
                locale=locale,
            )
        return self._translation_service.translate(
            key=key,
            locale=locale,
        )

    def add_error_translation(
        self,
        error_key: str,
        locale: Locale,
        message: str,
    ) -> None:
        """
        Add an error translation.

        Args:
            error_key: Error message key
            locale: Target locale
            message: Localized error message
        """
        self._translation_service.add_translation(
            key=error_key,
            locale=locale,
            value=message,
            context="error",
        )

    def add_ui_translation(
        self,
        key: str,
        locale: Locale,
        value: str,
    ) -> None:
        """
        Add a UI string translation.

        Args:
            key: UI string key
            locale: Target locale
            value: Localized string
        """
        self._translation_service.add_translation(
            key=key,
            locale=locale,
            value=value,
            context="ui",
        )

    def set_user_locale_preference(
        self,
        user_id: str,
        locale: Locale,
    ) -> None:
        """
        Set user's locale preference.

        Args:
            user_id: User identifier
            locale: Preferred locale
        """
        self._locale_service.set_user_preference(
            user_id=user_id,
            locale=locale,
        )

    def get_user_locale(
        self,
        user_id: str,
    ) -> Locale | None:
        """
        Get user's preferred locale.

        Args:
            user_id: User identifier

        Returns:
            Preferred locale or None
        """
        return self._locale_service.get_user_preference(user_id)

    def get_translation_service(self) -> TranslationService:
        """Get the translation service."""
        return self._translation_service

    def get_locale_service(self) -> LocaleService:
        """Get the locale service."""
        return self._locale_service

    def get_localization_stats(self) -> dict[str, Any]:
        """
        Get localization statistics.

        Returns:
            Localization statistics
        """
        translation_stats = self._translation_service.get_translation_stats()
        locale_stats = self._locale_service.get_locale_stats()

        return {
            "translation": translation_stats,
            "locale": locale_stats,
        }
