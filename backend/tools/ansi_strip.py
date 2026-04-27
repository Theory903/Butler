"""Forwarding stub — re-exports from the real hermes ansi_strip module."""

from integrations.hermes.tools.ansi_strip import *  # noqa: F401, F403
from integrations.hermes.tools.ansi_strip import strip_ansi

__all__ = ["strip_ansi"]
