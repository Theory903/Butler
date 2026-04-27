"""Integrations Catalog.

Phase K: Integrations catalog for managing external service integrations.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class Integration:
    """An external integration."""

    integration_id: str
    name: str
    type: str  # database, storage, auth, monitoring, etc.
    provider: str
    config: dict[str, Any] = field(default_factory=dict)
    is_enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class IntegrationsCatalog:
    """Catalog for managing Butler integrations.

    This catalog:
    - Manages external service integrations
    - Provides integration discovery
    - Tracks integration status
    - Supports integration health checks
    """

    def __init__(self):
        """Initialize the integrations catalog."""
        self._integrations: dict[str, Integration] = {}

    def register_integration(self, integration: Integration) -> None:
        """Register an integration.

        Args:
            integration: Integration to register
        """
        self._integrations[integration.integration_id] = integration
        logger.info("integration_registered", integration_id=integration.integration_id)

    def unregister_integration(self, integration_id: str) -> None:
        """Unregister an integration.

        Args:
            integration_id: Integration identifier
        """
        if integration_id in self._integrations:
            del self._integrations[integration_id]
            logger.info("integration_unregistered", integration_id=integration_id)

    def get_integration(self, integration_id: str) -> Integration | None:
        """Get an integration.

        Args:
            integration_id: Integration identifier

        Returns:
            Integration or None
        """
        return self._integrations.get(integration_id)

    def list_integrations(
        self,
        integration_type: str | None = None,
        provider: str | None = None,
        enabled_only: bool = False,
    ) -> list[Integration]:
        """List integrations with optional filters.

        Args:
            integration_type: Optional type filter
            provider: Optional provider filter
            enabled_only: Only return enabled integrations

        Returns:
            List of integrations
        """
        integrations = list(self._integrations.values())

        if integration_type:
            integrations = [i for i in integrations if i.type == integration_type]

        if provider:
            integrations = [i for i in integrations if i.provider == provider]

        if enabled_only:
            integrations = [i for i in integrations if i.is_enabled]

        return integrations

    def enable_integration(self, integration_id: str) -> None:
        """Enable an integration.

        Args:
            integration_id: Integration identifier
        """
        integration = self._integrations.get(integration_id)
        if integration:
            integration.is_enabled = True
            logger.info("integration_enabled", integration_id=integration_id)

    def disable_integration(self, integration_id: str) -> None:
        """Disable an integration.

        Args:
            integration_id: Integration identifier
        """
        integration = self._integrations.get(integration_id)
        if integration:
            integration.is_enabled = False
            logger.info("integration_disabled", integration_id=integration_id)

    def update_config(self, integration_id: str, config: dict[str, Any]) -> None:
        """Update integration configuration.

        Args:
            integration_id: Integration identifier
            config: New configuration
        """
        integration = self._integrations.get(integration_id)
        if integration:
            integration.config = config
            logger.info("integration_config_updated", integration_id=integration_id)


# Default integrations
DEFAULT_INTEGRATIONS = [
    Integration(
        integration_id="postgres-primary",
        name="PostgreSQL Primary",
        type="database",
        provider="postgresql",
        config={"host": "localhost", "port": 5432, "database": "butler"},
    ),
    Integration(
        integration_id="redis-cache",
        name="Redis Cache",
        type="cache",
        provider="redis",
        config={"host": "localhost", "port": 6379, "db": 0},
    ),
    Integration(
        integration_id="otel-collector",
        name="OpenTelemetry Collector",
        type="monitoring",
        provider="opentelemetry",
        config={"endpoint": "http://localhost:4317"},
    ),
]


def load_default_integrations(catalog: IntegrationsCatalog) -> None:
    """Load default integrations into catalog.

    Args:
        catalog: Integrations catalog
    """
    for integration in DEFAULT_INTEGRATIONS:
        catalog.register_integration(integration)
    logger.info("default_integrations_loaded", count=len(DEFAULT_INTEGRATIONS))
