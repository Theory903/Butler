"""Forwarding stub — re-exports from the real hermes openrouter_client module."""

from integrations.hermes.tools.openrouter_client import *  # noqa: F401, F403
from integrations.hermes.tools.openrouter_client import (
    check_api_key,
    get_async_client,
)

__all__ = ["check_api_key", "get_async_client"]
