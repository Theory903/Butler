"""Shim that re-exports LocalEnvironment from hermes integration."""

from integrations.hermes.tools.environments.local import LocalEnvironment

__all__ = ["LocalEnvironment"]