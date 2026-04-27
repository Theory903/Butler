"""Forwarding stub — re-exports from integrations.hermes.tools.mcp_oauth_manager."""

try:
    from integrations.hermes.tools.mcp_oauth_manager import *  # noqa: F401, F403
    from integrations.hermes.tools.mcp_oauth_manager import get_manager

    __all__ = ["get_manager"]
except ImportError:
    pass
