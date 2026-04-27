"""Forwarding stub — re-exports from the real hermes xai_http if available."""

try:
    from integrations.hermes.tools.xai_http import *  # noqa: F401, F403
    from integrations.hermes.tools.xai_http import hermes_xai_user_agent

    __all__ = ["hermes_xai_user_agent"]
except ImportError:
    pass
