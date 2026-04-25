"""Butler Plugin Bus — Phase 11, SOLID edition.

Implements IPluginBus. Depends on IPluginLoader (D).
Each loader is responsible for discovering plugins from ONE source (S).
New plugin sources extend IPluginLoader without modifying the bus (O).
Any IPluginLoader implementation is substitutable (L).
IPlugin / IPluginLoader / IPluginBus are separate small interfaces (I).

Architecture:
    ButlerPluginBus         — orchestrates lifecycle, knows nothing about sources
        ├── HermesMemoryPluginLoader  — loads plugins/memory/*
        ├── HermesContextPluginLoader — loads plugins/context_engine/*
        └── [future: RemotePluginLoader, S3PluginLoader, ...]

Usage:
    bus = ButlerPluginBus([HermesMemoryPluginLoader(), HermesContextPluginLoader()])
    await bus.load_all()
    plugin = bus.get("vector_memory")

    # DI-friendly factory (production):
    bus = make_default_plugin_bus()
"""

from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from domain.contracts import IPluginLoader

logger = structlog.get_logger(__name__)

_HERMES_PLUGINS_ROOT = (
    Path(__file__).parent.parent.parent  # backend/
    / "integrations"
    / "hermes"
    / "plugins"
)


# ── Plugin value object ────────────────────────────────────────────────────────


@dataclass
class ButlerPlugin:
    """Concrete IPlugin — a loaded plugin with metadata.

    Satisfies IPlugin protocol (L).
    """

    name: str
    plugin_type: str  # "memory" | "context"
    module_path: str
    instance: Any  # duck-typed — any object with butler plugin methods
    _available: bool = field(default=True, repr=False)
    error: str | None = None

    def is_available(self) -> bool:  # IPlugin
        return self._available

    @property
    def available(self) -> bool:
        return self._available


# ── IPluginLoader implementations (O, D) ─────────────────────────────────────


class HermesMemoryPluginLoader:
    """Loads plugins from integrations/hermes/plugins/memory/.

    Single responsibility: ONE source, ONE plugin type (S).
    Extends IPluginLoader without modifying the bus (O).
    """

    async def load(self) -> list[ButlerPlugin]:  # IPluginLoader
        return await _load_from_dir(_HERMES_PLUGINS_ROOT / "memory", "memory")


class HermesContextPluginLoader:
    """Loads plugins from integrations/hermes/plugins/context_engine/."""

    async def load(self) -> list[ButlerPlugin]:  # IPluginLoader
        return await _load_from_dir(_HERMES_PLUGINS_ROOT / "context_engine", "context")


async def _load_from_dir(plugin_dir: Path, plugin_type: str) -> list[ButlerPlugin]:
    """Shared discovery logic — package dirs and single .py files."""
    plugins: list[ButlerPlugin] = []
    if not plugin_dir.exists():
        return plugins

    for item in sorted(plugin_dir.iterdir()):
        if item.name.startswith("_"):
            continue

        if item.is_dir() and (item / "__init__.py").exists():
            mod_path = _dir_to_module(item)
            plugin = await _import_plugin(item.name, mod_path, plugin_type)
        elif item.suffix == ".py":
            mod_path = _dir_to_module(item.parent) + "." + item.stem
            plugin = await _import_plugin(item.stem, mod_path, plugin_type)
        else:
            continue

        if plugin:
            plugins.append(plugin)

    return plugins


async def _import_plugin(name: str, mod_path: str, plugin_type: str) -> ButlerPlugin | None:
    """Import a module and wrap the plugin object. Failures are isolated."""
    try:
        mod = importlib.import_module(mod_path)
        # Discover plugin by convention: plugin singleton, Plugin class, or get_plugin factory
        instance = getattr(mod, "plugin", None) or (
            getattr(mod, "Plugin", None)() if hasattr(mod, "Plugin") else None
        )
        if hasattr(mod, "get_plugin") and instance is None:
            instance = mod.get_plugin()

        available = True
        if instance and hasattr(instance, "is_available"):
            try:
                available = bool(instance.is_available())
            except Exception:
                available = False

        return ButlerPlugin(
            name=name,
            plugin_type=plugin_type,
            module_path=mod_path,
            instance=instance,
            _available=available,
        )
    except Exception as exc:
        logger.warning("butler_plugin_load_failed", name=name, mod=mod_path, error=str(exc))
        return ButlerPlugin(
            name=name,
            plugin_type=plugin_type,
            module_path=mod_path,
            instance=None,
            _available=False,
            error=str(exc),
        )


def _dir_to_module(path: Path) -> str:
    rel = path.relative_to(_HERMES_PLUGINS_ROOT.parent)  # relative to integrations/hermes/
    return "integrations.hermes." + str(rel).replace("/", ".").replace("\\", ".")


# ── ButlerPluginBus (IPluginBus, DI-friendly) ─────────────────────────────────


class ButlerPluginBus:
    """Butler plugin lifecycle manager.

    Depends on IPluginLoader — has no direct knowledge of where plugins come from (D).
    Open for extension: add new loaders without touching this class (O).
    Implements IPluginBus (L).

    Constructor:
        loaders: list of IPluginLoader — injected, any source is valid.

    Singleton factory:
        bus = make_default_plugin_bus()   # production
        bus = ButlerPluginBus([MockLoader()])  # tests
    """

    def __init__(self, loaders: list[IPluginLoader]) -> None:
        self._loaders = loaders
        self._plugins: dict[str, ButlerPlugin] = {}
        self._loaded = False

    async def load_all(self) -> ButlerPluginBus:  # IPluginBus
        """Run all loaders and collect plugins. Idempotent."""
        if self._loaded:
            return self
        self._loaded = True

        for loader in self._loaders:
            try:
                plugins = await loader.load()
                for p in plugins:
                    self._plugins[p.name] = p
            except Exception as exc:
                logger.warning(
                    "butler_plugin_loader_failed", loader=type(loader).__name__, error=str(exc)
                )

        logger.info(
            "butler_plugins_loaded",
            total=len(self._plugins),
            available=len(self.available_plugins()),
        )
        return self

    def get(self, name: str) -> ButlerPlugin | None:  # IPluginBus
        return self._plugins.get(name)

    def all_plugins(self) -> list[ButlerPlugin]:  # IPluginBus
        return list(self._plugins.values())

    def plugins_of_type(self, plugin_type: str) -> list[ButlerPlugin]:  # IPluginBus
        return [p for p in self._plugins.values() if p.plugin_type == plugin_type]

    def available_plugins(self) -> list[ButlerPlugin]:
        return [p for p in self._plugins.values() if p.available]

    async def teardown_all(self) -> None:  # IPluginBus
        for p in self._plugins.values():
            if p.instance and hasattr(p.instance, "teardown"):
                try:
                    result = p.instance.teardown()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as exc:
                    logger.warning("butler_plugin_teardown_failed", name=p.name, error=str(exc))

    def register(
        self, name: str, instance: Any, plugin_type: str = "memory"
    ) -> ButlerPlugin:  # IPluginBus
        """Programmatic registration — for tests and service bootstrapping."""
        p = ButlerPlugin(
            name=name,
            plugin_type=plugin_type,
            module_path="programmatic",
            instance=instance,
            _available=True,
        )
        self._plugins[name] = p
        return p

    def status(self) -> dict:
        return {
            "total": len(self._plugins),
            "available": len(self.available_plugins()),
            "plugins": [
                {"name": p.name, "type": p.plugin_type, "available": p.available, "error": p.error}
                for p in self._plugins.values()
            ],
        }


# ── Default factory (production wiring) ──────────────────────────────────────


def make_default_plugin_bus() -> ButlerPluginBus:
    """Production factory: injects all Hermes plugin loaders.

    Tests inject their own loaders — this is never imported in tests.
    """
    return ButlerPluginBus(
        loaders=[
            HermesMemoryPluginLoader(),
            HermesContextPluginLoader(),
        ]
    )
