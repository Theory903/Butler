"""Forwarding stub — re-exports from the real hermes tool_backend_helpers module."""

from integrations.hermes.tools.tool_backend_helpers import *  # noqa: F401, F403
from integrations.hermes.tools.tool_backend_helpers import (
    coerce_modal_mode,
    fal_key_is_configured,
    has_direct_modal_credentials,
    managed_nous_tools_enabled,
    normalize_browser_cloud_provider,
    prefers_gateway,
    resolve_modal_backend_state,
    resolve_openai_audio_api_key,
)

__all__ = [
    "coerce_modal_mode",
    "has_direct_modal_credentials",
    "managed_nous_tools_enabled",
    "fal_key_is_configured",
    "prefers_gateway",
    "normalize_browser_cloud_provider",
    "resolve_modal_backend_state",
    "resolve_openai_audio_api_key",
]
