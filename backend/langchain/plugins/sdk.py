"""Butler Plugin SDK.

Phase E.2: Plugin SDK from openclaw using standard library importlib.
Provides plugin lifecycle, manifest validation, and hot-reload.
"""

import hashlib
import importlib
import importlib.util
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class PluginState(str, Enum):
    """Plugin lifecycle states."""

    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    ACTIVE = "active"
    ERROR = "error"
    UNLOADING = "unloading"


@dataclass
class PluginManifest:
    """Plugin manifest with validation."""

    name: str
    version: str
    description: str
    author: str
    entry_point: str
    permissions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    api_version: str = "1.0"
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> bool:
        """Validate manifest fields."""
        if not self.name or not self.version:
            return False
        if not self.entry_point:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        """Convert manifest to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "entry_point": self.entry_point,
            "permissions": self.permissions,
            "dependencies": self.dependencies,
            "api_version": self.api_version,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PluginManifest":
        """Create manifest from dictionary."""
        return cls(**data)

    def compute_hash(self) -> str:
        """Compute hash of manifest for integrity check."""
        manifest_str = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(manifest_str.encode()).hexdigest()


@dataclass
class Plugin:
    """A loaded plugin instance."""

    plugin_id: str
    manifest: PluginManifest
    state: PluginState = PluginState.UNLOADED
    module: Any | None = None
    error: str | None = None
    loaded_at: float = 0
    hot_reload_count: int = 0

    async def initialize(self) -> None:
        """Initialize the plugin."""
        if hasattr(self.module, "initialize"):
            await self.module.initialize()
        self.state = PluginState.ACTIVE
        logger.info("plugin_initialized", plugin_id=self.plugin_id)

    async def shutdown(self) -> None:
        """Shutdown the plugin."""
        if hasattr(self.module, "shutdown"):
            await self.module.shutdown()
        self.state = PluginState.LOADED
        logger.info("plugin_shutdown", plugin_id=self.plugin_id)


class ButlerPluginSDK:
    """Plugin SDK for Butler with lifecycle management and hot-reload.

    This SDK:
    - Manages plugin loading/unloading using standard library importlib
    - Validates plugin manifests
    - Supports hot-reload for development
    - Provides plugin isolation
    """

    def __init__(self, plugin_dir: str | None = None):
        """Initialize the plugin SDK.

        Args:
            plugin_dir: Directory containing plugins
        """
        self._plugin_dir = Path(plugin_dir) if plugin_dir else Path("plugins")
        self._plugins: dict[str, Plugin] = {}
        self._manifest_cache: dict[str, PluginManifest] = {}

    async def load_plugin(self, plugin_path: str) -> Plugin:
        """Load a plugin from path using importlib.

        Args:
            plugin_path: Path to plugin directory or manifest file

        Returns:
            Loaded plugin instance
        """
        plugin_path = Path(plugin_path)
        manifest_path = plugin_path / "manifest.json" if plugin_path.is_dir() else plugin_path

        # Load and validate manifest
        manifest = self._load_manifest(manifest_path)
        if not manifest.validate():
            raise ValueError(f"Invalid manifest: {manifest_path}")

        plugin_id = f"{manifest.name}:{manifest.version}"
        plugin = Plugin(plugin_id=plugin_id, manifest=manifest, state=PluginState.LOADING)

        # Load plugin module using importlib.util
        try:
            entry_point = (
                plugin_path / manifest.entry_point
                if plugin_path.is_dir()
                else plugin_path.parent / manifest.entry_point
            )
            spec = importlib.util.spec_from_file_location(manifest.name, str(entry_point))
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                plugin.module = module
                plugin.loaded_at = time.time()
                plugin.state = PluginState.LOADED
            else:
                raise ImportError(f"Failed to load plugin from {entry_point}")
        except Exception as e:
            plugin.state = PluginState.ERROR
            plugin.error = str(e)
            logger.exception("plugin_load_failed", plugin_id=plugin_id)

        self._plugins[plugin_id] = plugin
        await plugin.initialize()

        logger.info("plugin_loaded", plugin_id=plugin_id)
        return plugin

    def _load_manifest(self, manifest_path: Path) -> PluginManifest:
        """Load plugin manifest from file.

        Args:
            manifest_path: Path to manifest file

        Returns:
            Plugin manifest
        """
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")

        with open(manifest_path) as f:
            data = json.load(f)

        manifest = PluginManifest.from_dict(data)
        self._manifest_cache[manifest.name] = manifest
        return manifest

    async def unload_plugin(self, plugin_id: str) -> None:
        """Unload a plugin.

        Args:
            plugin_id: Plugin identifier
        """
        plugin = self._plugins.get(plugin_id)
        if not plugin:
            logger.warning("plugin_not_found", plugin_id=plugin_id)
            return

        await plugin.shutdown()
        del self._plugins[plugin_id]
        logger.info("plugin_unloaded", plugin_id=plugin_id)

    async def reload_plugin(self, plugin_id: str) -> Plugin:
        """Hot-reload a plugin.

        Args:
            plugin_id: Plugin identifier

        Returns:
            Reloaded plugin instance
        """
        plugin = self._plugins.get(plugin_id)
        if not plugin:
            logger.warning("plugin_not_found", plugin_id=plugin_id)
            raise ValueError(f"Plugin not found: {plugin_id}")

        # Unload first
        await plugin.shutdown()

        # Reload module using importlib.reload
        if plugin.module:
            importlib.reload(plugin.module)

        plugin.hot_reload_count += 1
        plugin.state = PluginState.LOADED
        await plugin.initialize()

        logger.info("plugin_reloaded", plugin_id=plugin_id, reload_count=plugin.hot_reload_count)
        return plugin

    def get_plugin(self, plugin_id: str) -> Plugin | None:
        """Get a plugin by ID.

        Args:
            plugin_id: Plugin identifier

        Returns:
            Plugin instance or None
        """
        return self._plugins.get(plugin_id)

    def list_plugins(self, state: PluginState | None = None) -> list[Plugin]:
        """List plugins, optionally filtered by state.

        Args:
            state: Optional state filter

        Returns:
            List of plugins
        """
        plugins = list(self._plugins.values())
        if state:
            plugins = [p for p in plugins if p.state == state]
        return plugins

    async def discover_plugins(self) -> list[Path]:
        """Discover plugin directories.

        Returns:
            List of plugin directory paths
        """
        if not self._plugin_dir.exists():
            return []

        plugin_dirs = []
        for item in self._plugin_dir.iterdir():
            if item.is_dir() and (item / "manifest.json").exists():
                plugin_dirs.append(item)

        logger.info("plugins_discovered", count=len(plugin_dirs))
        return plugin_dirs

    async def load_all_plugins(self) -> list[Plugin]:
        """Load all discovered plugins.

        Returns:
            List of loaded plugins
        """
        plugin_dirs = await self.discover_plugins()
        loaded_plugins = []

        for plugin_dir in plugin_dirs:
            try:
                plugin = await self.load_plugin(str(plugin_dir))
                loaded_plugins.append(plugin)
            except Exception:
                logger.exception("plugin_load_failed", plugin_dir=str(plugin_dir))

        logger.info("all_plugins_loaded", count=len(loaded_plugins))
        return loaded_plugins
