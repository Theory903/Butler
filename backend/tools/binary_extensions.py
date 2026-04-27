"""Forwarding stub — re-exports from the real hermes binary_extensions module."""

from integrations.hermes.tools.binary_extensions import *  # noqa: F401, F403
from integrations.hermes.tools.binary_extensions import (
    BINARY_EXTENSIONS,
    has_binary_extension,
)

__all__ = ["BINARY_EXTENSIONS", "has_binary_extension"]
