"""Forwarding stub — re-exports from integrations.hermes.tools.mcp_oauth."""

try:
    from integrations.hermes.tools.mcp_oauth import *  # noqa: F401, F403
    from integrations.hermes.tools.mcp_oauth import (
        OAuthNonInteractiveError,
        _get_token_dir,
        _safe_filename,
        remove_oauth_tokens,
    )

    __all__ = [
        "OAuthNonInteractiveError",
        "_get_token_dir",
        "_safe_filename",
        "remove_oauth_tokens",
    ]
except ImportError:
    pass
