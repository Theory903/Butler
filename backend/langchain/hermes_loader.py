"""
Safe loader for Hermes tool implementations.

Directly imports safe Hermes implementation modules without triggering
CLI, gateway, SessionDB, or memory-owner side effects.

Dynamically discovers tools from:
- backend/integrations/hermes/ (original hermes-agent codebase)
- backend/langchain/ (Butlerified tools)
"""

from __future__ import annotations

import importlib
import inspect
import logging
import os
from pathlib import Path
from typing import Any

from backend.langchain.hermes_errors import HermesImportError
from backend.langchain.hermes_registry import (
    ButlerHermesRegistry,
    HermesImplementationSpec,
)

logger = logging.getLogger(__name__)

# Base directories for tool discovery
HERMES_INTEGRATION_DIR = Path(__file__).parent.parent / "integrations" / "hermes"
LANGCHAIN_DIR = Path(__file__).parent

# Modules to skip (not tool modules)
SKIP_MODULES = {
    "__init__",
    "hermes_constants",
    "hermes_logging",
    "hermes_state",
    "mcp_serve",
    "mini_swe_runner",
    "model_tools",
    "rl_cli",
    "toolset_distributions",
    "toolsets",
    "trajectory_compressor",
    "utils",
    "cli_config",
    "hermes_already_has_routines",
}


def discover_hermes_modules() -> list[str]:
    """Dynamically discover Python modules from hermes integration directory.

    Returns:
        List of module paths that may contain tool implementations
    """
    modules = []

    # Scan backend/integrations/hermes/ for Python modules
    if HERMES_INTEGRATION_DIR.exists():
        for py_file in HERMES_INTEGRATION_DIR.glob("*.py"):
            module_name = py_file.stem
            if module_name not in SKIP_MODULES and not module_name.startswith("_"):
                modules.append(f"integrations.hermes.{module_name}")

    # Scan backend/langchain/ for Butlerified tool modules
    if LANGCHAIN_DIR.exists():
        for py_file in LANGCHAIN_DIR.glob("*.py"):
            module_name = py_file.stem
            if module_name.startswith("butler_") and not module_name.startswith("_"):
                modules.append(f"langchain.{module_name}")

    return modules


# Tool functions that can be directly imported (module -> function mapping)
# This is now optional - if not specified, all functions are auto-discovered
SAFE_HERMES_TOOL_FUNCTIONS: dict[str, list[str]] = {}


def extract_specs_from_module(module: Any, module_path: str) -> list[HermesImplementationSpec]:
    """Extract tool specifications from a Hermes module.

    Inspects the module for callable functions that match tool patterns.
    Filters out internal functions, type hints, and helper functions.

    Args:
        module: The imported module
        module_path: Module path for reference

    Returns:
        List of HermesImplementationSpec objects
    """
    specs: list[HermesImplementationSpec] = []

    # Get safe tool functions for this module
    safe_functions = SAFE_HERMES_TOOL_FUNCTIONS.get(module_path, [])

    # Internal function names to exclude
    EXCLUDE_FUNCTIONS = {
        # Type hints and typing module members
        "Optional",
        "Union",
        "List",
        "Dict",
        "Any",
        "Callable",
        # Internal helpers from hermes_time
        "get_config_path",
        "get_timezone",
        "_resolve_timezone_name",
        "_get_zoneinfo",
        "_cached_tz",
        "_cache_resolved",
        # Common internal patterns
        "_",
    }

    for name, obj in inspect.getmembers(module):
        # Skip non-callables
        if not callable(obj):
            continue

        # Skip if not in safe list (when specified)
        if safe_functions and name not in safe_functions:
            continue

        # Skip private/internal functions
        if name.startswith("_"):
            continue

        # Skip known internal functions
        if name in EXCLUDE_FUNCTIONS:
            continue

        # Skip classes (for now - handle separately if needed)
        if inspect.isclass(obj):
            continue

        # Skip type hints (they appear as callables in typing module)
        if hasattr(obj, "__origin__") or hasattr(obj, "__args__"):
            continue

        # Create spec
        doc = inspect.getdoc(obj) or ""
        
        # Skip functions without documentation (likely internal helpers)
        if not doc and not safe_functions:
            continue

        spec = HermesImplementationSpec(
            name=name,
            description=doc,
            implementation=obj,
            source_file=module_path,
            risk_tier=1,  # Default risk tier
            tags=("hermes",),
            supports_async=inspect.iscoroutinefunction(obj),
            requires_env=False,
            requires_filesystem=False,
            requires_network=False,
        )
        specs.append(spec)
        logger.debug(f"Extracted spec: {name} from {module_path}")

    return specs


def load_safe_hermes_tools(
    registry: ButlerHermesRegistry | None = None,
) -> list[HermesImplementationSpec]:
    """Load safe Hermes tool implementations directly.

    Rules:
    1. Dynamically discover modules from hermes integration and langchain directories
    2. Do not import CLI, gateway, TUI, SessionDB, or memory-owner modules
    3. Do not trigger import-time side effects that write files or read ~/.hermes
    4. No global Hermes config loading in production

    Args:
        registry: Butler-owned registry to register tools into.
                 If None, uses the global registry.

    Returns:
        List of loaded tool specifications
    """
    if registry is None:
        from backend.langchain.hermes_registry import get_butler_hermes_registry

        registry = get_butler_hermes_registry()

    all_specs: list[HermesImplementationSpec] = []

    # Dynamically discover modules
    module_paths = discover_hermes_modules()
    logger.info(f"Discovered {len(module_paths)} Hermes modules: {module_paths}")

    for module_path in module_paths:
        try:
            module = importlib.import_module(module_path)
            specs = extract_specs_from_module(module, module_path)

            for spec in specs:
                registry.register(spec)
                all_specs.append(spec)

            logger.info(f"Loaded {len(specs)} specs from {module_path}")

        except Exception as exc:
            logger.warning(f"Failed to load Hermes module {module_path}: {exc}")
            # Continue loading other modules even if one fails
            continue

    logger.info(f"Loaded {len(all_specs)} Hermes tools total")
    return all_specs


def register_manual_hermes_tool(
    name: str,
    implementation: Any,
    description: str,
    registry: ButlerHermesRegistry | None = None,
    **kwargs: Any,
) -> HermesImplementationSpec:
    """Manually register a Hermes tool implementation.

    Use this for tools that cannot be auto-discovered or need custom configuration.

    Args:
        name: Tool name
        implementation: Callable or class implementing the tool
        description: Tool description
        registry: Butler-owned registry. If None, uses global registry.
        **kwargs: Additional spec fields (risk_tier, tags, etc.)

    Returns:
        The registered specification
    """
    if registry is None:
        from backend.langchain.hermes_registry import get_butler_hermes_registry

        registry = get_butler_hermes_registry()

    spec = HermesImplementationSpec(
        name=name,
        description=description,
        implementation=implementation,
        **kwargs,
    )

    registry.register(spec)
    logger.info("Manually registered Hermes tool: %s", name)

    return spec
