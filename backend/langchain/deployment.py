"""Butler Deployment Infrastructure for LangChain Agents.

Provides deployment configuration, scaling, and health management.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class DeploymentStatus(str, Enum):
    """Deployment status."""

    PENDING = "pending"
    DEPLOYING = "deploying"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"
    SCALING = "scaling"


class HealthStatus(str, Enum):
    """Health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class DeploymentConfig:
    """Deployment configuration."""

    deployment_id: str
    agent_type: str
    instance_count: int = 1
    cpu_limit: str = "1000m"
    memory_limit: str = "1Gi"
    gpu_enabled: bool = False
    gpu_type: str = ""
    env_vars: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthCheck:
    """Health check definition."""

    check_id: str
    check_type: str  # "http", "tcp", "command"
    endpoint: str = ""
    interval_seconds: int = 30
    timeout_seconds: int = 5
    failure_threshold: int = 3
    success_threshold: int = 1


class ButlerDeploymentManager:
    """Manager for agent deployments.

    This manager:
    - Manages deployment lifecycle
    - Handles scaling operations
    - Provides deployment status
    - Supports rolling updates
    """

    def __init__(self):
        """Initialize the deployment manager."""
        self._deployments: dict[str, DeploymentConfig] = {}
        self._deployment_status: dict[str, DeploymentStatus] = {}
        self._health_checks: dict[str, HealthCheck] = {}

    def create_deployment(self, config: DeploymentConfig) -> str:
        """Create a new deployment.

        Args:
            config: Deployment configuration

        Returns:
            Deployment ID
        """
        self._deployments[config.deployment_id] = config
        self._deployment_status[config.deployment_id] = DeploymentStatus.PENDING
        logger.info("deployment_created", deployment_id=config.deployment_id)
        return config.deployment_id

    def deploy(self, deployment_id: str) -> bool:
        """Deploy an agent.

        Args:
            deployment_id: Deployment ID

        Returns:
            True if deployment started
        """
        if deployment_id not in self._deployments:
            return False

        self._deployment_status[deployment_id] = DeploymentStatus.DEPLOYING
        logger.info("deployment_started", deployment_id=deployment_id)

        # In production, this would trigger actual deployment
        self._deployment_status[deployment_id] = DeploymentStatus.RUNNING
        return True

    def stop_deployment(self, deployment_id: str) -> bool:
        """Stop a deployment.

        Args:
            deployment_id: Deployment ID

        Returns:
            True if stopped
        """
        if deployment_id not in self._deployments:
            return False

        self._deployment_status[deployment_id] = DeploymentStatus.STOPPED
        logger.info("deployment_stopped", deployment_id=deployment_id)
        return True

    def scale_deployment(self, deployment_id: str, instance_count: int) -> bool:
        """Scale a deployment.

        Args:
            deployment_id: Deployment ID
            instance_count: Target instance count

        Returns:
            True if scaling started
        """
        if deployment_id not in self._deployments:
            return False

        config = self._deployments[deployment_id]
        config.instance_count = instance_count
        self._deployment_status[deployment_id] = DeploymentStatus.SCALING

        logger.info("deployment_scaling", deployment_id=deployment_id, count=instance_count)

        # In production, this would trigger actual scaling
        self._deployment_status[deployment_id] = DeploymentStatus.RUNNING
        return True

    def get_deployment_status(self, deployment_id: str) -> DeploymentStatus | None:
        """Get deployment status.

        Args:
            deployment_id: Deployment ID

        Returns:
            Deployment status or None
        """
        return self._deployment_status.get(deployment_id)

    def get_deployment_config(self, deployment_id: str) -> DeploymentConfig | None:
        """Get deployment configuration.

        Args:
            deployment_id: Deployment ID

        Returns:
            Deployment config or None
        """
        return self._deployments.get(deployment_id)

    def get_all_deployments(self) -> dict[str, DeploymentConfig]:
        """Get all deployments.

        Returns:
            Dictionary of deployments
        """
        return self._deployments.copy()

    def delete_deployment(self, deployment_id: str) -> bool:
        """Delete a deployment.

        Args:
            deployment_id: Deployment ID

        Returns:
            True if deleted
        """
        if deployment_id in self._deployments:
            del self._deployments[deployment_id]
            del self._deployment_status[deployment_id]
            logger.info("deployment_deleted", deployment_id=deployment_id)
            return True

        return False


class ButlerHealthChecker:
    """Health checker for deployed agents.

    This checker:
    - Performs health checks
    - Aggregates health status
    - Provides health metrics
    - Supports custom check types
    """

    def __init__(self):
        """Initialize the health checker."""
        self._health_status: dict[str, HealthStatus] = {}
        self._health_checks: dict[str, HealthCheck] = {}
        self._check_results: dict[str, dict[str, Any]] = {}

    def register_health_check(self, check: HealthCheck) -> None:
        """Register a health check.

        Args:
            check: Health check definition
        """
        self._health_checks[check.check_id] = check
        logger.info("health_check_registered", check_id=check.check_id)

    def perform_check(self, check_id: str) -> dict[str, Any]:
        """Perform a health check.

        Args:
            check_id: Check ID

        Returns:
            Check result
        """
        check = self._health_checks.get(check_id)
        if not check:
            return {"status": "error", "message": "Check not found"}

        # In production, this would perform actual health check
        result = {
            "check_id": check_id,
            "status": "healthy",
            "timestamp": None,
            "latency_ms": 0,
        }

        self._check_results[check_id] = result
        self._health_status[check_id] = HealthStatus.HEALTHY

        return result

    def get_health_status(self, resource_id: str) -> HealthStatus:
        """Get health status for a resource.

        Args:
            resource_id: Resource ID

        Returns:
            Health status
        """
        return self._health_status.get(resource_id, HealthStatus.UNKNOWN)

    def get_all_health_status(self) -> dict[str, HealthStatus]:
        """Get all health statuses.

        Returns:
            Dictionary of health statuses
        """
        return self._health_status.copy()

    def aggregate_health(self) -> HealthStatus:
        """Aggregate overall health status.

        Returns:
            Overall health status
        """
        if not self._health_status:
            return HealthStatus.UNKNOWN

        statuses = list(self._health_status.values())

        if all(s == HealthStatus.HEALTHY for s in statuses):
            return HealthStatus.HEALTHY
        elif any(s == HealthStatus.UNHEALTHY for s in statuses):
            return HealthStatus.UNHEALTHY
        else:
            return HealthStatus.DEGRADED


class ButlerDeploymentOrchestrator:
    """Orchestrator for deployment operations.

    This orchestrator:
    - Coordinates deployments
    - Manages rolling updates
    - Handles canary deployments
    - Provides deployment rollback
    """

    def __init__(self, deployment_manager: ButlerDeploymentManager):
        """Initialize the orchestrator.

        Args:
            deployment_manager: Deployment manager
        """
        self._deployment_manager = deployment_manager
        self._rollback_points: dict[str, DeploymentConfig] = {}

    def rolling_update(
        self,
        deployment_id: str,
        new_config: DeploymentConfig,
        batch_size: int = 1,
    ) -> bool:
        """Perform a rolling update.

        Args:
            deployment_id: Deployment ID
            new_config: New configuration
            batch_size: Batch size for update

        Returns:
            True if update started
        """
        current_config = self._deployment_manager.get_deployment_config(deployment_id)
        if not current_config:
            return False

        # Save rollback point
        self._rollback_points[deployment_id] = current_config

        logger.info("rolling_update_started", deployment_id=deployment_id, batch_size=batch_size)

        # In production, this would perform actual rolling update
        self._deployment_manager._deployments[deployment_id] = new_config
        return True

    def canary_deployment(
        self,
        deployment_id: str,
        canary_config: DeploymentConfig,
        canary_percentage: float = 0.1,
    ) -> str:
        """Deploy a canary.

        Args:
            deployment_id: Original deployment ID
            canary_config: Canary configuration
            canary_percentage: Percentage of traffic to canary

        Returns:
            Canary deployment ID
        """
        canary_id = f"{deployment_id}-canary"
        canary_config.deployment_id = canary_id

        self._deployment_manager.create_deployment(canary_config)
        self._deployment_manager.deploy(canary_id)

        logger.info("canary_deployment_created", canary_id=canary_id, percentage=canary_percentage)
        return canary_id

    def rollback(self, deployment_id: str) -> bool:
        """Rollback a deployment.

        Args:
            deployment_id: Deployment ID

        Returns:
            True if rollback succeeded
        """
        rollback_config = self._rollback_points.get(deployment_id)
        if not rollback_config:
            return False

        self._deployment_manager._deployments[deployment_id] = rollback_config
        del self._rollback_points[deployment_id]

        logger.info("deployment_rolled_back", deployment_id=deployment_id)
        return True

    def promote_canary(self, canary_id: str) -> bool:
        """Promote a canary to full deployment.

        Args:
            canary_id: Canary deployment ID

        Returns:
            True if promoted
        """
        original_id = canary_id.replace("-canary", "")
        canary_config = self._deployment_manager.get_deployment_config(canary_id)

        if not canary_config:
            return False

        canary_config.deployment_id = original_id
        self._deployment_manager._deployments[original_id] = canary_config
        self._deployment_manager.delete_deployment(canary_id)

        logger.info("canary_promoted", canary_id=canary_id, original_id=original_id)
        return True


class ButlerDeploymentInfra:
    """Combined deployment infrastructure.

    This infra:
    - Combines deployment management
    - Integrates health checking
    - Provides orchestration
    - Supports monitoring
    """

    def __init__(self):
        """Initialize the deployment infra."""
        self._deployment_manager = ButlerDeploymentManager()
        self._health_checker = ButlerHealthChecker()
        self._orchestrator = ButlerDeploymentOrchestrator(self._deployment_manager)

    @property
    def deployment_manager(self) -> ButlerDeploymentManager:
        """Get the deployment manager."""
        return self._deployment_manager

    @property
    def health_checker(self) -> ButlerHealthChecker:
        """Get the health checker."""
        return self._health_checker

    @property
    def orchestrator(self) -> ButlerDeploymentOrchestrator:
        """Get the orchestrator."""
        return self._orchestrator

    def get_infra_status(self) -> dict[str, Any]:
        """Get infrastructure status.

        Returns:
            Infrastructure status
        """
        return {
            "deployments": len(self._deployment_manager.get_all_deployments()),
            "health_checks": len(self._health_checker._health_checks),
            "overall_health": self._health_checker.aggregate_health().value,
            "deployment_statuses": {
                dep_id: status.value
                for dep_id, status in self._deployment_manager._deployment_status.items()
            },
        }

    def setup_default_health_checks(self, deployment_id: str) -> None:
        """Setup default health checks for a deployment.

        Args:
            deployment_id: Deployment ID
        """
        http_check = HealthCheck(
            check_id=f"{deployment_id}-http",
            check_type="http",
            endpoint="/health",
        )
        self._health_checker.register_health_check(http_check)
