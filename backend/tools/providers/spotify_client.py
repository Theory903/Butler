"""Forwarding stub — re-exports from integrations.hermes.tools.providers.spotify_client."""

try:
    from integrations.hermes.tools.providers.spotify_client import *  # noqa: F401, F403
    from integrations.hermes.tools.providers.spotify_client import (
        normalize_spotify_id,
        SpotifyAPIError,
        SpotifyAuthRequiredError,
        SpotifyClient,
        SpotifyError,
    )
except ImportError:
    pass

__all__ = [
    "normalize_spotify_id",
    "SpotifyAPIError",
    "SpotifyAuthRequiredError",
    "SpotifyClient",
    "SpotifyError",
]
