"""Forwarding stub — re-exports from integrations.hermes.tools.file_operations."""

from integrations.hermes.tools.file_operations import *  # noqa: F401, F403
from integrations.hermes.tools.file_operations import (
    PatchResult,
    ShellFileOperations,
    normalize_read_pagination,
    normalize_search_pagination,
)

__all__ = [
    "PatchResult",
    "ShellFileOperations",
    "normalize_read_pagination",
    "normalize_search_pagination",
]
