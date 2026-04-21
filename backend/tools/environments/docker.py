"""Shim that re-exports DockerEnvironment from hermes integration."""

from integrations.hermes.tools.environments.docker import DockerEnvironment

__all__ = ["DockerEnvironment"]