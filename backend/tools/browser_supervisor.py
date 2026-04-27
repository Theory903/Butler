"""Forwarding stub — re-exports from the real hermes browser_supervisor module."""

from integrations.hermes.tools.browser_supervisor import *  # noqa: F401, F403
from integrations.hermes.tools.browser_supervisor import (
    DEFAULT_DIALOG_POLICY,
    DEFAULT_DIALOG_TIMEOUT_S,
    SUPERVISOR_REGISTRY,
)

__all__ = [
    "DEFAULT_DIALOG_POLICY",
    "DEFAULT_DIALOG_TIMEOUT_S",
    "SUPERVISOR_REGISTRY",
]
