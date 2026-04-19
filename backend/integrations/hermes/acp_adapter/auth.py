"""ACP auth helpers — detect the currently configured Hermes provider."""

from __future__ import annotations

import importlib
from typing import Optional


def detect_provider() -> Optional[str]:
    """Resolve the active Hermes runtime provider, or None if unavailable."""
    try:
        runtime_provider_module = importlib.import_module(
            "backend.integrations.hermes.hermes_cli.runtime_provider"
        )
        resolve_runtime_provider = getattr(runtime_provider_module, "resolve_runtime_provider")
        runtime = resolve_runtime_provider()
        api_key = runtime.get("api_key")
        provider = runtime.get("provider")
        if isinstance(api_key, str) and api_key.strip() and isinstance(provider, str) and provider.strip():
            return provider.strip().lower()
    except Exception:
        return None
    return None


def has_provider() -> bool:
    """Return True if Hermes can resolve any runtime provider credentials."""
    return detect_provider() is not None
