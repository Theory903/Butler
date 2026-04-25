"""
API Version Manager - API Version Management

Manages API versions, deprecation policies, and sunset procedures.
Supports version lifecycle management and migration guidance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ApiStatus(StrEnum):
    """API version status."""

    ALPHA = "alpha"
    BETA = "beta"
    STABLE = "stable"
    DEPRECATED = "deprecated"
    SUNSET = "sunset"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class ApiVersion:
    """API version metadata."""

    version: str
    status: ApiStatus
    released_at: datetime
    deprecated_at: datetime | None
    sunset_at: datetime | None
    retired_at: datetime | None
    migration_guide: str | None
    breaking_changes: list[str]
    features: list[str]


class ApiVersionManager:
    """
    API version manager for version lifecycle management.

    Features:
    - Version lifecycle management
    - Deprecation policies
    - Sunset procedures
    - Migration guidance
    """

    def __init__(self) -> None:
        """Initialize API version manager."""
        self._versions: dict[str, ApiVersion] = {}
        self._default_version = "v1"
        self._deprecation_notice_days = 90
        self._sunset_notice_days = 180

    def register_version(
        self,
        version: str,
        status: ApiStatus = ApiStatus.STABLE,
        features: list[str] | None = None,
        breaking_changes: list[str] | None = None,
        migration_guide: str | None = None,
    ) -> ApiVersion:
        """
        Register a new API version.

        Args:
            version: Version identifier (e.g., "v1", "v2")
            status: Version status
            features: List of new features
            breaking_changes: List of breaking changes
            migration_guide: URL to migration guide

        Returns:
            API version metadata
        """
        api_version = ApiVersion(
            version=version,
            status=status,
            released_at=datetime.now(UTC),
            deprecated_at=None,
            sunset_at=None,
            retired_at=None,
            migration_guide=migration_guide,
            breaking_changes=breaking_changes or [],
            features=features or [],
        )

        self._versions[version] = api_version

        logger.info(
            "api_version_registered",
            version=version,
            status=status,
        )

        return api_version

    def deprecate_version(
        self,
        version: str,
        sunset_days: int | None = None,
    ) -> ApiVersion | None:
        """
        Deprecate an API version.

        Args:
            version: Version identifier
            sunset_days: Days until sunset (uses default if None)

        Returns:
            Updated API version or None if not found
        """
        if version not in self._versions:
            logger.error(
                "api_version_not_found",
                version=version,
            )
            return None

        current = self._versions[version]
        sunset_days = sunset_days or self._sunset_notice_days
        sunset_at = datetime.now(UTC) + timedelta(days=sunset_days)

        deprecated_version = ApiVersion(
            version=current.version,
            status=ApiStatus.DEPRECATED,
            released_at=current.released_at,
            deprecated_at=datetime.now(UTC),
            sunset_at=sunset_at,
            retired_at=None,
            migration_guide=current.migration_guide,
            breaking_changes=current.breaking_changes,
            features=current.features,
        )

        self._versions[version] = deprecated_version

        logger.warning(
            "api_version_deprecated",
            version=version,
            sunset_at=sunset_at.isoformat(),
        )

        return deprecated_version

    def sunset_version(self, version: str) -> ApiVersion | None:
        """
        Sunset an API version (mark for retirement).

        Args:
            version: Version identifier

        Returns:
            Updated API version or None if not found
        """
        if version not in self._versions:
            logger.error(
                "api_version_not_found",
                version=version,
            )
            return None

        current = self._versions[version]

        sunset_version = ApiVersion(
            version=current.version,
            status=ApiStatus.SUNSET,
            released_at=current.released_at,
            deprecated_at=current.deprecated_at,
            sunset_at=current.sunset_at,
            retired_at=None,
            migration_guide=current.migration_guide,
            breaking_changes=current.breaking_changes,
            features=current.features,
        )

        self._versions[version] = sunset_version

        logger.warning(
            "api_version_sunset",
            version=version,
        )

        return sunset_version

    def retire_version(self, version: str) -> ApiVersion | None:
        """
        Retire an API version (no longer accessible).

        Args:
            version: Version identifier

        Returns:
            Updated API version or None if not found
        """
        if version not in self._versions:
            logger.error(
                "api_version_not_found",
                version=version,
            )
            return None

        current = self._versions[version]

        retired_version = ApiVersion(
            version=current.version,
            status=ApiStatus.RETIRED,
            released_at=current.released_at,
            deprecated_at=current.deprecated_at,
            sunset_at=current.sunset_at,
            retired_at=datetime.now(UTC),
            migration_guide=current.migration_guide,
            breaking_changes=current.breaking_changes,
            features=current.features,
        )

        self._versions[version] = retired_version

        logger.info(
            "api_version_retired",
            version=version,
        )

        return retired_version

    def get_version(self, version: str) -> ApiVersion | None:
        """
        Get API version metadata.

        Args:
            version: Version identifier

        Returns:
            API version or None
        """
        return self._versions.get(version)

    def list_versions(
        self,
        status: ApiStatus | None = None,
    ) -> list[ApiVersion]:
        """
        List API versions with optional filter.

        Args:
            status: Filter by status

        Returns:
            List of API versions
        """
        versions = list(self._versions.values())

        if status:
            versions = [v for v in versions if v.status == status]

        return sorted(versions, key=lambda v: v.released_at, reverse=True)

    def get_active_versions(self) -> list[ApiVersion]:
        """Get all active (non-deprecated, non-sunset, non-retired) versions."""
        return self.list_versions(
            status=None,
        )

    def get_latest_version(self) -> ApiVersion | None:
        """Get the latest stable version."""
        stable_versions = self.list_versions(status=ApiStatus.STABLE)
        if stable_versions:
            return stable_versions[0]
        return None

    def set_default_version(self, version: str) -> bool:
        """
        Set the default API version.

        Args:
            version: Version identifier

        Returns:
            True if successful
        """
        if version not in self._versions:
            logger.error(
                "api_version_not_found",
                version=version,
            )
            return False

        self._default_version = version

        logger.info(
            "default_api_version_set",
            version=version,
        )

        return True

    def get_default_version(self) -> str:
        """Get the default API version."""
        return self._default_version

    def set_deprecation_notice_days(self, days: int) -> None:
        """
        Set deprecation notice period.

        Args:
            days: Notice period in days
        """
        self._deprecation_notice_days = days
        logger.info(
            "deprecation_notice_updated",
            days=days,
        )

    def set_sunset_notice_days(self, days: int) -> None:
        """
        Set sunset notice period.

        Args:
            days: Notice period in days
        """
        self._sunset_notice_days = days
        logger.info(
            "sunset_notice_updated",
            days=days,
        )

    def check_version_compatibility(
        self,
        client_version: str,
        server_version: str | None = None,
    ) -> dict[str, Any]:
        """
        Check compatibility between client and server versions.

        Args:
            client_version: Client API version
            server_version: Server API version (uses default if None)

        Returns:
            Compatibility information
        """
        server_version = server_version or self._default_version

        client_meta = self.get_version(client_version)
        server_meta = self.get_version(server_version)

        if not client_meta or not server_meta:
            return {
                "compatible": False,
                "reason": "version_not_found",
                "client_version": client_version,
                "server_version": server_version,
            }

        # Check if client version is retired
        if client_meta.status == ApiStatus.RETIRED:
            return {
                "compatible": False,
                "reason": "client_version_retired",
                "client_version": client_version,
                "server_version": server_version,
                "sunset_date": client_meta.sunset_at.isoformat() if client_meta.sunset_at else None,
            }

        # Check if client version is sunset
        if client_meta.status == ApiStatus.SUNSET:
            return {
                "compatible": False,
                "reason": "client_version_sunset",
                "client_version": client_version,
                "server_version": server_version,
                "sunset_date": client_meta.sunset_at.isoformat() if client_meta.sunset_at else None,
            }

        # Check if client version is deprecated
        if client_meta.status == ApiStatus.DEPRECATED:
            return {
                "compatible": True,
                "warning": "client_version_deprecated",
                "client_version": client_version,
                "server_version": server_version,
                "sunset_date": client_meta.sunset_at.isoformat() if client_meta.sunset_at else None,
                "migration_guide": client_meta.migration_guide,
            }

        return {
            "compatible": True,
            "client_version": client_version,
            "server_version": server_version,
        }

    def get_version_stats(self) -> dict[str, Any]:
        """
        Get version statistics.

        Returns:
            Version statistics
        """
        total_versions = len(self._versions)

        status_counts: dict[str, int] = {}
        for version in self._versions.values():
            status_counts[version.status] = status_counts.get(version.status, 0) + 1

        return {
            "total_versions": total_versions,
            "default_version": self._default_version,
            "status_breakdown": status_counts,
            "deprecation_notice_days": self._deprecation_notice_days,
            "sunset_notice_days": self._sunset_notice_days,
        }
