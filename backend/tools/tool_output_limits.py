"""Forwarding stub — re-exports from integrations.hermes.tools.tool_output_limits."""

from integrations.hermes.tools.tool_output_limits import *  # noqa: F401, F403
from integrations.hermes.tools.tool_output_limits import (
    get_max_bytes,
    get_max_line_length,
    get_max_lines,
)

__all__ = ["get_max_bytes", "get_max_line_length", "get_max_lines"]
