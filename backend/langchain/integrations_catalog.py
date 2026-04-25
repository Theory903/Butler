"""Butler Integrations Catalog for LangChain Agents.

Provides a catalog of available integrations and their configurations.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class IntegrationType(str, Enum):
    """Integration types."""

    TOOL = "tool"
    MEMORY = "memory"
    MODEL = "model"
    PROTOCOL = "protocol"
    MIDDLEWARE = "middleware"


class IntegrationStatus(str, Enum):
    """Integration status."""

    AVAILABLE = "available"
    INSTALLED = "installed"
    CONFIGURED = "configured"
    ERROR = "error"


@dataclass
class Integration:
    """An integration definition."""

    integration_id: str
    name: str
    integration_type: IntegrationType
    description: str = ""
    version: str = "1.0.0"
    author: str = "Butler"
    config_schema: dict[str, Any] = field(default_factory=dict)
    required_deps: list[str] = field(default_factory=list)
    optional_deps: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IntegrationConfig:
    """Configuration for an integration."""

    integration_id: str
    config: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    status: IntegrationStatus = IntegrationStatus.AVAILABLE


class ButlerIntegrationsCatalog:
    """Catalog of available integrations.

    This catalog:
    - Lists available integrations
    - Manages integration configurations
    - Provides integration discovery
    - Handles installation status
    """

    def __init__(self):
        """Initialize the integrations catalog."""
        self._integrations: dict[str, Integration] = {}
        self._configs: dict[str, IntegrationConfig] = {}
        self._load_builtin_integrations()

    def _load_builtin_integrations(self) -> None:
        """Load built-in integrations."""
        # Tool integrations
        self._integrations["hermes"] = Integration(
            integration_id="hermes",
            name="Hermes Tool Compiler",
            integration_type=IntegrationType.TOOL,
            description="Butler's tool compilation system",
            version="1.0.0",
            author="Butler",
            required_deps=["domain.tools.hermes_compiler"],
        )

        self._integrations["openai"] = Integration(
            integration_id="openai",
            name="OpenAI Models",
            integration_type=IntegrationType.MODEL,
            description="OpenAI GPT models",
            version="1.0.0",
            author="OpenAI",
            required_deps=["openai"],
        )

        self._integrations["anthropic"] = Integration(
            integration_id="anthropic",
            name="Anthropic Models",
            integration_type=IntegrationType.MODEL,
            description="Anthropic Claude models",
            version="1.0.0",
            author="Anthropic",
            required_deps=["anthropic"],
        )

        # Memory integrations
        self._integrations["redis_memory"] = Integration(
            integration_id="redis_memory",
            name="Redis Hot Memory",
            integration_type=IntegrationType.MEMORY,
            description="Redis-based hot memory tier",
            version="1.0.0",
            author="Butler",
            required_deps=["redis"],
        )

        self._integrations["qdrant_memory"] = Integration(
            integration_id="qdrant_memory",
            name="Qdrant Warm Memory",
            integration_type=IntegrationType.MEMORY,
            description="Qdrant-based warm memory tier",
            version="1.0.0",
            author="Butler",
            required_deps=["qdrant"],
        )

        # Protocol integrations
        self._integrations["mcp"] = Integration(
            integration_id="mcp",
            name="Model Context Protocol",
            integration_type=IntegrationType.PROTOCOL,
            description="MCP for tool discovery and resource access",
            version="1.0.0",
            author="Anthropic",
        )

        self._integrations["a2a"] = Integration(
            integration_id="a2a",
            name="Agent-to-Agent Protocol",
            integration_type=IntegrationType.PROTOCOL,
            description="A2A for agent communication",
            version="1.0.0",
            author="Butler",
        )

        # Middleware integrations
        self._integrations["guardrails"] = Integration(
            integration_id="guardrails",
            name="Guardrails Middleware",
            integration_type=IntegrationType.MIDDLEWARE,
            description="Safety guardrails for agent outputs",
            version="1.0.0",
            author="Butler",
        )

        self._integrations["caching"] = Integration(
            integration_id="caching",
            name="Caching Middleware",
            integration_type=IntegrationType.MIDDLEWARE,
            description="SWR caching for model responses",
            version="1.0.0",
            author="Butler",
            optional_deps=["redis"],
        )

        logger.info("builtin_integrations_loaded", count=len(self._integrations))

    def register_integration(self, integration: Integration) -> None:
        """Register a custom integration.

        Args:
            integration: Integration definition
        """
        self._integrations[integration.integration_id] = integration
        logger.info("integration_registered", integration_id=integration.integration_id)

    def get_integration(self, integration_id: str) -> Integration | None:
        """Get an integration by ID.

        Args:
            integration_id: Integration ID

        Returns:
            Integration or None
        """
        return self._integrations.get(integration_id)

    def list_integrations(
        self,
        integration_type: IntegrationType | None = None,
        status: IntegrationStatus | None = None,
    ) -> list[Integration]:
        """List integrations with optional filters.

        Args:
            integration_type: Optional type filter
            status: Optional status filter

        Returns:
            List of integrations
        """
        integrations = list(self._integrations.values())

        if integration_type:
            integrations = [i for i in integrations if i.integration_type == integration_type]

        if status:
            integrations = [
                i for i in integrations
                if self._configs.get(i.integration_id, IntegrationConfig(integration_id=i.integration_id)).status == status
            ]

        return integrations

    def configure_integration(
        self,
        integration_id: str,
        config: dict[str, Any],
        enabled: bool = True,
    ) -> bool:
        """Configure an integration.

        Args:
            integration_id: Integration ID
            config: Configuration
            enabled: Whether integration is enabled

        Returns:
            True if configured
        """
        if integration_id not in self._integrations:
            return False

        self._configs[integration_id] = IntegrationConfig(
            integration_id=integration_id,
            config=config,
            enabled=enabled,
            status=IntegrationStatus.CONFIGURED,
        )

        logger.info("integration_configured", integration_id=integration_id)
        return True

    def get_config(self, integration_id: str) -> IntegrationConfig | None:
        """Get integration configuration.

        Args:
            integration_id: Integration ID

        Returns:
            Integration config or None
        """
        return self._configs.get(integration_id)

    def enable_integration(self, integration_id: str) -> bool:
        """Enable an integration.

        Args:
            integration_id: Integration ID

        Returns:
            True if enabled
        """
        config = self._configs.get(integration_id)
        if config:
            config.enabled = True
            logger.info("integration_enabled", integration_id=integration_id)
            return True
        return False

    def disable_integration(self, integration_id: str) -> bool:
        """Disable an integration.

        Args:
            integration_id: Integration ID

        Returns:
            True if disabled
        """
        config = self._configs.get(integration_id)
        if config:
            config.enabled = False
            logger.info("integration_disabled", integration_id=integration_id)
            return True
        return False

    def check_dependencies(self, integration_id: str) -> dict[str, bool]:
        """Check if integration dependencies are available.

        Args:
            integration_id: Integration ID

        Returns:
            Dictionary of dependency to availability
        """
        integration = self._integrations.get(integration_id)
        if not integration:
            return {}

        deps = {}
        for dep in integration.required_deps:
            try:
                __import__(dep)
                deps[dep] = True
            except ImportError:
                deps[dep] = False

        return deps

    def get_installation_status(self, integration_id: str) -> IntegrationStatus:
        """Get installation status for an integration.

        Args:
            integration_id: Integration ID

        Returns:
            Installation status
        """
        deps = self.check_dependencies(integration_id)
        all_available = all(deps.values())

        if not all_available:
            return IntegrationStatus.AVAILABLE

        config = self._configs.get(integration_id)
        if config and config.enabled:
            return IntegrationStatus.CONFIGURED

        return IntegrationStatus.INSTALLED

    def get_catalog_summary(self) -> dict[str, Any]:
        """Get catalog summary.

        Returns:
            Catalog summary
        """
        return {
            "total_integrations": len(self._integrations),
            "by_type": {
                itype.value: len([i for i in self._integrations.values() if i.integration_type == itype])
                for itype in IntegrationType
            },
            "configured": len([c for c in self._configs.values() if c.status == IntegrationStatus.CONFIGURED]),
            "enabled": len([c for c in self._configs.values() if c.enabled]),
        }
