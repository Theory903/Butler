"""Shim that re-exports SSHEnvironment from hermes integration."""

from integrations.hermes.tools.environments.ssh import SSHEnvironment

__all__ = ["SSHEnvironment"]