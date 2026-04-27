"""Butler Plugin Manager.

Phase E.2: Plugin manager for lifecycle and hot-reload coordination.
"""

import logging
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ButlerPluginManager:
    """Manager for Butler plugins with hot-reload and coordination.

    This manager:
    - Coordinates plugin SDK instances
    - Manages plugin permissions and isolation
    - Provides plugin discovery and registration
    - Handles plugin dependencies
    """

    def __init__(self, plugin_sdk: Any | None = None):
        """Initialize the plugin manager.

        Args:
            plugin_sdk: ButlerPluginSDK instance
        """
        self._plugin_sdk = plugin_sdk
        self._active_plugins: dict[str, Any] = {}

    async def register_plugin(self, plugin_path: str) -> Any:
        """Register and load a plugin.

        Args:
            plugin_path: Path to plugin

        Returns:
            Loaded plugin
        """
        if not self._plugin_sdk:
            raise RuntimeError("Plugin SDK not configured")

        plugin = await self._plugin_sdk.load_plugin(plugin_path)
        self._active_plugins[plugin.plugin_id] = plugin
        return plugin

    async def unregister_plugin(self, plugin_id: str) -> None:
        """Unregister and unload a plugin.

        Args:
            plugin_id: Plugin identifier
        """
        if plugin_id in self._active_plugins:
            await self._plugin_sdk.unload_plugin(plugin_id)
            del self._active_plugins[plugin_id]

    async def hot_reload(self, plugin_id: str) -> Any:
        """Hot-reload a plugin.

        Args:
            plugin_id: Plugin identifier

        Returns:
            Reloaded plugin
        """
        if not self._plugin_sdk:
            raise RuntimeError("Plugin SDK not configured")

        plugin = await self._plugin_sdk.reload_plugin(plugin_id)
        self._active_plugins[plugin_id] = plugin
        return plugin

    def get_plugin(self, plugin_id: str) -> Any | None:
        """Get an active plugin.

        Args:
            plugin_id: Plugin identifier

        Returns:
            Plugin or None
        """
        return self._active_plugins.get(plugin_id)

    def list_plugins(self) -> list[Any]:
        """List all active plugins.

        Returns:
            List of plugins
        """
        return list(self._active_plugins.values())
