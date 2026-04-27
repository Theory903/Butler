"""Forwarding stub — re-exports from integrations.hermes.tools.patch_parser."""

from integrations.hermes.tools.patch_parser import *  # noqa: F401, F403
from integrations.hermes.tools.patch_parser import (
    apply_v4a_operations,
    parse_v4a_patch,
)

__all__ = ["apply_v4a_operations", "parse_v4a_patch"]
