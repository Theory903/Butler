"""Hermes Platform Registry.

Registry for Hermes gateway platforms that can be integrated with Butler channels.
"""

import logging
from typing import Any

from .adapter import ButlerHermesGatewayAdapter

import structlog

logger = structlog.get_logger(__name__)


class HermesPlatformSpec:
    """Specification for a Hermes gateway platform."""

    def __init__(
        self,
        name: str,
        category: str,
        description: str,
        enabled: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize platform specification.

        Args:
            name: Platform name (e.g., "discord", "telegram")
            category: Platform category (e.g., "chat", "voice", "social")
            description: Platform description
            enabled: Whether platform is enabled
            metadata: Optional metadata
        """
        self.name = name
        self.category = category
        self.description = description
        self.enabled = enabled
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "enabled": self.enabled,
            "metadata": self.metadata,
        }


class HermesPlatformRegistry:
    """Registry for Hermes gateway platforms.

    Manages platform specifications and their Butler channel mappings.
    """

    def __init__(self, adapter: ButlerHermesGatewayAdapter | None = None) -> None:
        """Initialize platform registry.

        Args:
            adapter: Optional gateway adapter (creates new if not provided)
        """
        self._adapter = adapter or ButlerHermesGatewayAdapter()
        self._platforms: dict[str, HermesPlatformSpec] = {}
        self._categories: dict[str, list[str]] = {}

    def register(self, spec: HermesPlatformSpec) -> None:
        """Register a platform.

        Args:
            spec: Platform specification
        """
        self._platforms[spec.name] = spec

        # Add to category
        if spec.category not in self._categories:
            self._categories[spec.category] = []
        if spec.name not in self._categories[spec.category]:
            self._categories[spec.category].append(spec.name)

        logger.debug(f"Registered platform: {spec.name} (category: {spec.category})")

    def get(self, name: str) -> HermesPlatformSpec | None:
        """Get a platform by name.

        Args:
            name: Platform name

        Returns:
            Platform specification or None if not found
        """
        return self._platforms.get(name)

    def get_all(self) -> dict[str, HermesPlatformSpec]:
        """Get all registered platforms.

        Returns:
            Dictionary of all platform specifications
        """
        return self._platforms.copy()

    def get_by_category(self, category: str) -> list[HermesPlatformSpec]:
        """Get all platforms in a category.

        Args:
            category: Platform category

        Returns:
            List of platform specifications
        """
        return [
            self._platforms[name]
            for name in self._categories.get(category, [])
            if name in self._platforms
        ]

    def get_enabled(self) -> dict[str, HermesPlatformSpec]:
        """Get all enabled platforms.

        Returns:
            Dictionary of enabled platform specifications
        """
        return {name: spec for name, spec in self._platforms.items() if spec.enabled}

    def get_butler_channel(self, platform: str) -> Any | None:
        """Get Butler Channel for a Hermes platform.

        Args:
            platform: Hermes platform name

        Returns:
            Butler Channel enum or None
        """
        return self._adapter.get_butler_channel_for_platform(platform)

    def enable(self, name: str) -> bool:
        """Enable a platform.

        Args:
            name: Platform name

        Returns:
            True if platform was enabled, False if not found
        """
        if name in self._platforms:
            self._platforms[name].enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        """Disable a platform.

        Args:
            name: Platform name

        Returns:
            True if platform was disabled, False if not found
        """
        if name in self._platforms:
            self._platforms[name].enabled = False
            return True
        return False

    def unregister(self, name: str) -> bool:
        """Unregister a platform.

        Args:
            name: Platform name

        Returns:
            True if platform was unregistered, False if not found
        """
        if name in self._platforms:
            spec = self._platforms[name]
            del self._platforms[name]

            # Remove from category
            if spec.category in self._categories:
                self._categories[spec.category] = [
                    n for n in self._categories[spec.category] if n != name
                ]

            return True
        return False

    def __len__(self) -> int:
        """Return number of registered platforms."""
        return len(self._platforms)

    def __contains__(self, name: str) -> bool:
        """Check if platform is registered."""
        return name in self._platforms

    def __repr__(self) -> str:
        return f"HermesPlatformRegistry(platforms={len(self._platforms)}, categories={len(self._categories)})"
