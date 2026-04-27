"""Shared helpers for direct xAI HTTP integrations."""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


def hermes_xai_user_agent() -> str:
    """Return a stable Hermes-specific User-Agent for xAI HTTP calls."""
    try:
        from hermes_cli import __version__
    except Exception:
        __version__ = "unknown"
    return f"Hermes-Agent/{__version__}"
