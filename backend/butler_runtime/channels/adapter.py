"""Butler-Hermes Gateway Adapter.

Adapter interface for Hermes gateway platforms to work with Butler's channel system.
"""

import logging

from services.communication.channel_registry import Channel

logger = logging.getLogger(__name__)


class ButlerHermesGatewayAdapter:
    """Adapter for Hermes gateway platforms to Butler channels.

    This adapter allows Hermes gateway implementations to integrate
    with Butler's unified channel registry system.
    """

    def __init__(self) -> None:
        """Initialize gateway adapter."""
        self._platform_mappings: dict[str, Channel] = {
            "discord": Channel.DISCORD,
            "telegram": Channel.TELEGRAM,
            "slack": Channel.SLACK,
            "whatsapp": Channel.WHATSAPP,
            "signal": Channel.SIGNAL,
            "matrix": Channel.MATRIX,
            "teams": Channel.TEAMS,
        }

    def map_hermes_platform_to_butler_channel(self, platform: str) -> Channel | None:
        """Map a Hermes platform name to Butler Channel enum.

        Args:
            platform: Hermes platform name (e.g., "discord", "telegram")

        Returns:
            Butler Channel enum or None if no mapping exists
        """
        return self._platform_mappings.get(platform.lower())

    def register_hermes_platform(
        self,
        platform: str,
        butler_channel: Channel,
    ) -> None:
        """Register a custom Hermes platform to Butler channel mapping.

        Args:
            platform: Hermes platform name
            butler_channel: Butler Channel enum
        """
        self._platform_mappings[platform.lower()] = butler_channel
        logger.debug(f"Registered platform mapping: {platform} -> {butler_channel}")

    def get_supported_platforms(self) -> list[str]:
        """Get list of supported Hermes platforms.

        Returns:
            List of platform names
        """
        return list(self._platform_mappings.keys())

    def get_butler_channel_for_platform(self, platform: str) -> Channel | None:
        """Get Butler Channel for a Hermes platform.

        Args:
            platform: Hermes platform name

        Returns:
            Butler Channel enum or None
        """
        return self._platform_mappings.get(platform.lower())

    def is_platform_supported(self, platform: str) -> bool:
        """Check if a Hermes platform is supported.

        Args:
            platform: Hermes platform name

        Returns:
            True if platform is supported
        """
        return platform.lower() in self._platform_mappings
