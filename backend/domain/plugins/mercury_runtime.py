"""Butler Mercury Runtime — Unified Plugin Bus V2.

Implements high-assurance registration for Providers, Routes, Tools, and Skills.
Supports Manifest-first validation and multi-lane execution boundaries.
"""

from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass
from typing import Any

import structlog

from domain.plugins.sandbox import DockerSandbox, SubprocessSandbox
from domain.skills.manifest import Capability, RiskTier, SkillManifest
from infrastructure.config import settings

logger = structlog.get_logger(__name__)


@dataclass
class MercuryPlugin:
    """A loaded and verified Mercury plugin."""

    manifest: SkillManifest
    instance: Any
    module_path: str
    risk_tier: RiskTier
    available: bool = True
    error: str | None = None

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def capabilities(self) -> list[Capability]:
        return self.manifest.capabilities


class MercuryRuntime:
    """
    The central runtime for all Butler extensions.

    Provides unified discovery and registration for:
    - AI Model Providers (ProviderCapability)
    - API Extensions (RouteCapability)
    - Agent Tools (ToolCapability)
    - Knowledge Bundles (SkillCapability)
    """

    def __init__(self):
        self._plugins: dict[str, MercuryPlugin] = {}
        self._by_capability: dict[Capability, list[str]] = {cap: [] for cap in Capability}
        self._is_loaded = False

        # Initialize sandbox backend
        if settings.PLUGINS_ISOLATION_BACKEND == "docker":
            self._sandbox = DockerSandbox(image=settings.PLUGINS_DOCKER_IMAGE)
        else:
            self._sandbox = SubprocessSandbox()

    async def spawn_sandbox(
        self, plugin_id: str, command: list[str], env: dict[str, str] = None
    ) -> Any:
        """Spawn a sandbox for a high-risk plugin."""
        if env is None:
            env = {}
        if not settings.PLUGINS_ISOLATION_ENABLED:
            logger.warning("sandbox_disabled_globally", plugin_id=plugin_id)
            return None

        plugin = self.get_plugin(plugin_id)
        if plugin and plugin.risk_tier == RiskTier.LOW:
            logger.info("sandbox_skipped_low_risk", plugin_id=plugin_id)
            return None

        return await self._sandbox.spawn(plugin_id, command, env)

    async def register_plugin(self, manifest: SkillManifest, module_path: str) -> MercuryPlugin:
        """Load and register a plugin into the runtime."""
        try:
            # Import instance
            mod = importlib.import_module(module_path)
            instance = getattr(mod, "plugin", None) or (
                getattr(mod, "Plugin", None)() if hasattr(mod, "Plugin") else None
            )

            plugin = MercuryPlugin(
                manifest=manifest,
                instance=instance,
                module_path=module_path,
                risk_tier=manifest.risk_class,
            )

            self._plugins[plugin.id] = plugin
            for cap in plugin.capabilities:
                self._by_capability[cap].append(plugin.id)

            logger.info(
                "plugin_registered",
                id=plugin.id,
                capabilities=[c.value for c in plugin.capabilities],
            )
            return plugin

        except Exception as e:
            logger.error("plugin_registration_failed", id=manifest.id, error=str(e))
            raise

    def get_plugins_by_capability(self, capability: Capability) -> list[MercuryPlugin]:
        """Retrieve all plugins supporting a specific capability."""
        ids = self._by_capability.get(capability, [])
        return [self._plugins[plugin_id] for plugin_id in ids if plugin_id in self._plugins]

    def get_plugin(self, plugin_id: str) -> MercuryPlugin | None:
        """Retrieve a specific plugin by ID."""
        return self._plugins.get(plugin_id)

    async def teardown(self):
        """Gracefully shutdown all plugins."""
        for plugin in self._plugins.values():
            if plugin.instance and hasattr(plugin.instance, "teardown"):
                try:
                    res = plugin.instance.teardown()
                    if asyncio.iscoroutine(res):
                        await res
                except Exception as e:
                    logger.warning("plugin_teardown_failed", id=plugin.id, error=str(e))

    def status(self) -> dict[str, Any]:
        """Runtime health and inventory status."""
        return {
            "total_plugins": len(self._plugins),
            "capabilities": {cap.value: len(ids) for cap, ids in self._by_capability.items()},
            "inventory": [
                {
                    "id": p.id,
                    "version": p.manifest.version,
                    "risk": p.risk_tier.name,
                    "available": p.available,
                }
                for p in self._plugins.values()
            ],
        }
