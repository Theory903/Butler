"""
Canary Deployment - Canary Deployment Automation

Implements canary deployment automation for gradual rollouts.
Supports traffic splitting, automated rollbacks, and deployment metrics.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class DeploymentStatus(StrEnum):
    """Deployment status."""

    PENDING = "pending"
    DEPLOYING = "deploying"
    ACTIVE = "active"
    ROLLING_BACK = "rolling_back"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class RollbackTrigger(StrEnum):
    """Rollback trigger."""

    MANUAL = "manual"
    ERROR_RATE = "error_rate"
    LATENCY = "latency"
    CUSTOM_METRIC = "custom_metric"


@dataclass(frozen=True, slots=True)
class CanaryConfig:
    """Canary deployment configuration."""

    deployment_id: str
    service_name: str
    new_version: str
    old_version: str
    initial_traffic_percentage: int
    max_traffic_percentage: int
    ramp_up_duration_seconds: int
    auto_rollback_threshold: float  # Error rate threshold
    metrics_callback: Callable[[str], Awaitable[dict[str, float]]] | None


@dataclass(frozen=True, slots=True)
class CanaryState:
    """Canary deployment state."""

    deployment_id: str
    status: DeploymentStatus
    current_traffic_percentage: int
    started_at: datetime
    updated_at: datetime
    error_rate: float
    latency_ms: float


@dataclass(frozen=True, slots=True)
class RollbackEvent:
    """Rollback event."""

    event_id: str
    deployment_id: str
    trigger: RollbackTrigger
    reason: str
    triggered_at: datetime
    successful: bool


class CanaryDeployment:
    """
    Canary deployment automation service.

    Features:
    - Traffic splitting
    - Gradual ramp-up
    - Automated rollbacks
    - Deployment metrics
    """

    def __init__(self) -> None:
        """Initialize canary deployment service."""
        self._configs: dict[str, CanaryConfig] = {}
        self._states: dict[str, CanaryState] = {}
        self._rollbacks: list[RollbackEvent] = []
        self._deployment_tasks: dict[str, asyncio.Task] = {}
        self._traffic_splitter: Callable[[str, int], Awaitable[bool]] | None = None

    def set_traffic_splitter(
        self,
        splitter: Callable[[str, int], Awaitable[bool]],
    ) -> None:
        """
        Set traffic splitter callback.

        Args:
            splitter: Async function to split traffic
        """
        self._traffic_splitter = splitter

    async def start_deployment(
        self,
        config: CanaryConfig,
    ) -> CanaryState:
        """
        Start a canary deployment.

        Args:
            config: Canary configuration

        Returns:
            Canary state
        """
        now = datetime.now(UTC)

        # Initial state
        state = CanaryState(
            deployment_id=config.deployment_id,
            status=DeploymentStatus.DEPLOYING,
            current_traffic_percentage=config.initial_traffic_percentage,
            started_at=now,
            updated_at=now,
            error_rate=0.0,
            latency_ms=0.0,
        )

        self._configs[config.deployment_id] = config
        self._states[config.deployment_id] = state

        # Start deployment task
        task = asyncio.create_task(self._execute_deployment(config))
        self._deployment_tasks[config.deployment_id] = task

        logger.info(
            "canary_deployment_started",
            deployment_id=config.deployment_id,
            service_name=config.service_name,
            new_version=config.new_version,
        )

        return state

    async def _execute_deployment(
        self,
        config: CanaryConfig,
    ) -> None:
        """
        Execute canary deployment.

        Args:
            config: Canary configuration
        """
        try:
            # Calculate ramp-up steps
            steps = 10
            step_duration = config.ramp_up_duration_seconds / steps
            traffic_increment = (
                config.max_traffic_percentage - config.initial_traffic_percentage
            ) // steps

            current_percentage = config.initial_traffic_percentage

            for _step in range(steps):
                # Check if deployment was cancelled
                current_state = self._states.get(config.deployment_id)
                if not current_state or current_state.status == DeploymentStatus.ROLLING_BACK:
                    return

                # Update traffic split
                if self._traffic_splitter:
                    await self._traffic_splitter(config.deployment_id, current_percentage)

                # Update state
                updated_state = CanaryState(
                    deployment_id=config.deployment_id,
                    status=DeploymentStatus.ACTIVE,
                    current_traffic_percentage=current_percentage,
                    started_at=current_state.started_at,
                    updated_at=datetime.now(UTC),
                    error_rate=current_state.error_rate,
                    latency_ms=current_state.latency_ms,
                )

                self._states[config.deployment_id] = updated_state

                # Collect metrics
                if config.metrics_callback:
                    metrics = await config.metrics_callback(config.deployment_id)
                    error_rate = metrics.get("error_rate", 0.0)
                    latency = metrics.get("latency_ms", 0.0)

                    updated_state = CanaryState(
                        deployment_id=config.deployment_id,
                        status=DeploymentStatus.ACTIVE,
                        current_traffic_percentage=current_percentage,
                        started_at=current_state.started_at,
                        updated_at=datetime.now(UTC),
                        error_rate=error_rate,
                        latency_ms=latency,
                    )

                    self._states[config.deployment_id] = updated_state

                    # Check rollback condition
                    if error_rate > config.auto_rollback_threshold:
                        await self._trigger_rollback(
                            config.deployment_id,
                            RollbackTrigger.ERROR_RATE,
                            f"Error rate {error_rate} exceeds threshold {config.auto_rollback_threshold}",
                        )
                        return

                # Wait for next step
                await asyncio.sleep(step_duration)

                # Increase traffic
                current_percentage = min(
                    current_percentage + traffic_increment, config.max_traffic_percentage
                )

            # Deployment complete
            final_state = CanaryState(
                deployment_id=config.deployment_id,
                status=DeploymentStatus.COMPLETED,
                current_traffic_percentage=100,
                started_at=current_state.started_at,
                updated_at=datetime.now(UTC),
                error_rate=current_state.error_rate,
                latency_ms=current_state.latency_ms,
            )

            self._states[config.deployment_id] = final_state

            logger.info(
                "canary_deployment_completed",
                deployment_id=config.deployment_id,
            )

        except Exception as e:
            logger.error(
                "canary_deployment_failed",
                deployment_id=config.deployment_id,
                error=str(e),
            )

            current_state = self._states.get(config.deployment_id)
            started_at = current_state.started_at if current_state else datetime.now(UTC)

            failed_state = CanaryState(
                deployment_id=config.deployment_id,
                status=DeploymentStatus.FAILED,
                current_traffic_percentage=0,
                started_at=started_at,
                updated_at=datetime.now(UTC),
                error_rate=0.0,
                latency_ms=0.0,
            )

            self._states[config.deployment_id] = failed_state

    async def trigger_rollback(
        self,
        deployment_id: str,
        reason: str,
    ) -> RollbackEvent:
        """
        Trigger manual rollback.

        Args:
            deployment_id: Deployment identifier
            reason: Rollback reason

        Returns:
            Rollback event
        """
        return await self._trigger_rollback(
            deployment_id,
            RollbackTrigger.MANUAL,
            reason,
        )

    async def _trigger_rollback(
        self,
        deployment_id: str,
        trigger: RollbackTrigger,
        reason: str,
    ) -> RollbackEvent:
        """
        Internal rollback trigger.

        Args:
            deployment_id: Deployment identifier
            trigger: Rollback trigger
            reason: Rollback reason

        Returns:
            Rollback event
        """
        event_id = f"rollback-{datetime.now(UTC).timestamp()}"

        # Update state to rolling back
        current_state = self._states.get(deployment_id)

        if current_state:
            rollback_state = CanaryState(
                deployment_id=deployment_id,
                status=DeploymentStatus.ROLLING_BACK,
                current_traffic_percentage=0,
                started_at=current_state.started_at,
                updated_at=datetime.now(UTC),
                error_rate=current_state.error_rate,
                latency_ms=current_state.latency_ms,
            )

            self._states[deployment_id] = rollback_state

        # Execute rollback
        successful = True

        if self._traffic_splitter:
            successful = await self._traffic_splitter(deployment_id, 0)

        event = RollbackEvent(
            event_id=event_id,
            deployment_id=deployment_id,
            trigger=trigger,
            reason=reason,
            triggered_at=datetime.now(UTC),
            successful=successful,
        )

        self._rollbacks.append(event)

        # Update state to rolled back
        if current_state:
            rolled_back_state = CanaryState(
                deployment_id=deployment_id,
                status=DeploymentStatus.ROLLED_BACK if successful else DeploymentStatus.FAILED,
                current_traffic_percentage=0,
                started_at=current_state.started_at,
                updated_at=datetime.now(UTC),
                error_rate=current_state.error_rate,
                latency_ms=current_state.latency_ms,
            )

            self._states[deployment_id] = rolled_back_state

        logger.warning(
            "canary_rollback_triggered",
            deployment_id=deployment_id,
            trigger=trigger,
            reason=reason,
        )

        return event

    def get_state(self, deployment_id: str) -> CanaryState | None:
        """
        Get deployment state.

        Args:
            deployment_id: Deployment identifier

        Returns:
            Canary state or None
        """
        return self._states.get(deployment_id)

    def get_config(self, deployment_id: str) -> CanaryConfig | None:
        """
        Get deployment configuration.

        Args:
            deployment_id: Deployment identifier

        Returns:
            Canary configuration or None
        """
        return self._configs.get(deployment_id)

    def get_rollbacks(
        self,
        deployment_id: str | None = None,
        limit: int = 100,
    ) -> list[RollbackEvent]:
        """
        Get rollback events.

        Args:
            deployment_id: Filter by deployment
            limit: Maximum number of events

        Returns:
            List of rollback events
        """
        rollbacks = self._rollbacks

        if deployment_id:
            rollbacks = [r for r in rollbacks if r.deployment_id == deployment_id]

        return sorted(rollbacks, key=lambda r: r.triggered_at, reverse=True)[:limit]

    def cancel_deployment(self, deployment_id: str) -> bool:
        """
        Cancel a deployment.

        Args:
            deployment_id: Deployment identifier

        Returns:
            True if cancelled
        """
        if deployment_id in self._deployment_tasks:
            task = self._deployment_tasks[deployment_id]
            if not task.done():
                task.cancel()

            del self._deployment_tasks[deployment_id]

            logger.info(
                "canary_deployment_cancelled",
                deployment_id=deployment_id,
            )

            return True
        return False

    def get_deployment_stats(self) -> dict[str, Any]:
        """
        Get deployment statistics.

        Returns:
            Deployment statistics
        """
        total_deployments = len(self._configs)
        active_deployments = sum(
            1
            for s in self._states.values()
            if s.status in [DeploymentStatus.DEPLOYING, DeploymentStatus.ACTIVE]
        )
        completed_deployments = sum(
            1 for s in self._states.values() if s.status == DeploymentStatus.COMPLETED
        )
        failed_deployments = sum(
            1
            for s in self._states.values()
            if s.status in [DeploymentStatus.FAILED, DeploymentStatus.ROLLED_BACK]
        )

        status_counts: dict[str, int] = {}
        for state in self._states.values():
            status_counts[state.status] = status_counts.get(state.status, 0) + 1

        return {
            "total_deployments": total_deployments,
            "active_deployments": active_deployments,
            "completed_deployments": completed_deployments,
            "failed_deployments": failed_deployments,
            "total_rollbacks": len(self._rollbacks),
            "status_breakdown": status_counts,
        }
