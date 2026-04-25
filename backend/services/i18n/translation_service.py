"""
Translation Service - Internationalization (i18n)

Provides translation and localization support for multi-language support.
Supports locale detection, translation management, and localized strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class Locale(StrEnum):
    """Supported locales."""

    EN_US = "en_US"
    EN_GB = "en_GB"
    ES_ES = "es_ES"
    FR_FR = "fr_FR"
    DE_DE = "de_DE"
    JA_JP = "ja_JP"
    ZH_CN = "zh_CN"
    PT_BR = "pt_BR"
    RU_RU = "ru_RU"


@dataclass(frozen=True, slots=True)
class TranslationEntry:
    """Translation entry for a key."""

    key: str
    locale: Locale
    value: str
    context: str | None


class TranslationService:
    """
    Translation service for i18n support.

    Features:
    - Multi-language support
    - Translation key management
    - Fallback to default locale
    - Context-aware translations
    """

    def __init__(
        self,
        default_locale: Locale = Locale.EN_US,
    ) -> None:
        """Initialize translation service."""
        self._default_locale = default_locale
        self._translations: dict[str, dict[Locale, TranslationEntry]] = {}

        # Initialize with common translations
        self._initialize_common_translations()

    def _initialize_common_translations(self) -> None:
        """Initialize common translation keys."""
        common_translations = {
            "error.unauthorized": {
                Locale.EN_US: "Unauthorized access",
                Locale.ES_ES: "Acceso no autorizado",
                Locale.FR_FR: "Accès non autorisé",
                Locale.DE_DE: "Unbefugter Zugriff",
                Locale.JA_JP: "不正アクセス",
                Locale.ZH_CN: "未经授权的访问",
                Locale.PT_BR: "Acesso não autorizado",
                Locale.RU_RU: "Несанкционированный доступ",
            },
            "error.forbidden": {
                Locale.EN_US: "Access forbidden",
                Locale.ES_ES: "Acceso prohibido",
                Locale.FR_FR: "Accès interdit",
                Locale.DE_DE: "Zugriff verboten",
                Locale.JA_JP: "アクセス禁止",
                Locale.ZH_CN: "访问被禁止",
                Locale.PT_BR: "Acesso proibido",
                Locale.RU_RU: "Доступ запрещен",
            },
            "error.not_found": {
                Locale.EN_US: "Resource not found",
                Locale.ES_ES: "Recurso no encontrado",
                Locale.FR_FR: "Ressource non trouvée",
                Locale.DE_DE: "Ressource nicht gefunden",
                Locale.JA_JP: "リソースが見つかりません",
                Locale.ZH_CN: "未找到资源",
                Locale.PT_BR: "Recurso não encontrado",
                Locale.RU_RU: "Ресурс не найден",
            },
            "error.internal": {
                Locale.EN_US: "Internal server error",
                Locale.ES_ES: "Error interno del servidor",
                Locale.FR_FR: "Erreur interne du serveur",
                Locale.DE_DE: "Interner Serverfehler",
                Locale.JA_JP: "内部サーバーエラー",
                Locale.ZH_CN: "内部服务器错误",
                Locale.PT_BR: "Erro interno do servidor",
                Locale.RU_RU: "Внутренняя ошибка сервера",
            },
            "success.operation": {
                Locale.EN_US: "Operation successful",
                Locale.ES_ES: "Operación exitosa",
                Locale.FR_FR: "Opération réussie",
                Locale.DE_DE: "Vorgang erfolgreich",
                Locale.JA_JP: "操作成功",
                Locale.ZH_CN: "操作成功",
                Locale.PT_BR: "Operação bem-sucedida",
                Locale.RU_RU: "Операция успешна",
            },
        }

        for key, translations in common_translations.items():
            for locale, value in translations.items():
                entry = TranslationEntry(
                    key=key,
                    locale=locale,
                    value=value,
                    context=None,
                )

                if key not in self._translations:
                    self._translations[key] = {}

                self._translations[key][locale] = entry

    def add_translation(
        self,
        key: str,
        locale: Locale,
        value: str,
        context: str | None = None,
    ) -> TranslationEntry:
        """
        Add a translation entry.

        Args:
            key: Translation key
            locale: Target locale
            value: Translated string
            context: Optional context

        Returns:
            Translation entry
        """
        entry = TranslationEntry(
            key=key,
            locale=locale,
            value=value,
            context=context,
        )

        if key not in self._translations:
            self._translations[key] = {}

        self._translations[key][locale] = entry

        logger.debug(
            "translation_added",
            key=key,
            locale=locale,
        )

        return entry

    def translate(
        self,
        key: str,
        locale: Locale | None = None,
        fallback: str | None = None,
    ) -> str:
        """
        Translate a key to the specified locale.

        Args:
            key: Translation key
            locale: Target locale (uses default if None)
            fallback: Fallback string if translation not found

        Returns:
            Translated string
        """
        locale = locale or self._default_locale

        if key not in self._translations:
            logger.warning(
                "translation_key_not_found",
                key=key,
                locale=locale,
            )
            return fallback or key

        if locale not in self._translations[key]:
            # Try default locale
            if self._default_locale in self._translations[key]:
                logger.debug(
                    "translation_fallback_to_default",
                    key=key,
                    requested_locale=locale,
                    default_locale=self._default_locale,
                )
                return self._translations[key][self._default_locale].value

            logger.warning(
                "translation_locale_not_found",
                key=key,
                locale=locale,
            )
            return fallback or key

        return self._translations[key][locale].value

    def translate_with_params(
        self,
        key: str,
        params: dict[str, Any],
        locale: Locale | None = None,
        fallback: str | None = None,
    ) -> str:
        """
        Translate a key with parameter substitution.

        Args:
            key: Translation key
            params: Parameters for substitution
            locale: Target locale
            fallback: Fallback string

        Returns:
            Translated string with parameters substituted
        """
        template = self.translate(key, locale, fallback)

        try:
            return template.format(**params)
        except (KeyError, ValueError) as e:
            logger.error(
                "translation_parameter_substitution_failed",
                key=key,
                params=params,
                error=str(e),
            )
            return template

    def get_available_locales(self) -> list[Locale]:
        """Get list of available locales."""
        return list(Locale)

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

    def get_translation_stats(self) -> dict[str, Any]:
        """
        Get translation statistics.

        Returns:
            Translation statistics
        """
        total_keys = len(self._translations)
        total_entries = sum(len(locales) for locales in self._translations.values())

        locale_counts: dict[str, int] = {}
        for locales in self._translations.values():
            for locale in locales:
                locale_counts[locale] = locale_counts.get(locale, 0) + 1

        return {
            "total_translation_keys": total_keys,
            "total_translation_entries": total_entries,
            "locale_coverage": locale_counts,
            "default_locale": self._default_locale,
        }
