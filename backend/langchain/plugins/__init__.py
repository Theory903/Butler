"""Butler Plugins Package.

Phase E.2: Plugin SDK from openclaw.
Provides plugin lifecycle management, manifest validation, and hot-reload.
"""

from langchain.plugins.manager import ButlerPluginManager
from langchain.plugins.sdk import ButlerPluginSDK, PluginLifecycle, PluginManifest

__all__ = [
    "ButlerPluginSDK",
    "PluginManifest",
    "PluginLifecycle",
    "ButlerPluginManager",
]
