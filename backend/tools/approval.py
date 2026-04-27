"""Forwarding stub — re-exports from the real hermes approval module."""

from integrations.hermes.tools.approval import *  # noqa: F401, F403
from integrations.hermes.tools.approval import (
    check_all_command_guards,
    get_current_session_key,
)

__all__ = ["check_all_command_guards", "get_current_session_key"]
