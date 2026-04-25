"""
Agent Lifecycle Management - Agent State and Lifecycle

Manages agent lifecycle including creation, activation, deactivation, and termination.
Implements health monitoring and auto-recovery for agent instances.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class AgentStatus(StrEnum):
    """Agent lifecycle status."""

    CREATING = "creating"
    STARTING = "starting"
    ACTIVE = "active"
    IDLE = "idle"
    BUSY = "busy"
    SUSPENDED = "suspended"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    TERMINATED = "terminated"


@dataclass(frozen=True, slots=True)
class AgentInstance:
    """Agent instance metadata."""

    agent_id: str
    tenant_id: str
    agent_type: str
    status: AgentStatus
    created_at: datetime
    started_at: datetime | None
    last_heartbeat: datetime | None
    task_count: int
    metadata: dict[str, Any]


class AgentLifecycleManager:
    """
    Agent lifecycle management service.

    Features:
    - Agent creation and initialization
    - Status transitions
    - Health monitoring via heartbeats
    - Auto-recovery for failed agents
    - Multi-tenant isolation
    """

    def __init__(self) -> None:
        """Initialize agent lifecycle manager."""
        self._agents: dict[str, AgentInstance] = {}
        self._tenant_agents: dict[str, set[str]] = {}  # tenant_id -> agent_ids

    def create_agent(
        self,
        agent_id: str,
        tenant_id: str,
        agent_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentInstance:
        """
        Create a new agent instance.

        Args:
            agent_id: Unique agent identifier
            tenant_id: Tenant UUID
            agent_type: Type of agent
            metadata: Additional agent metadata

        Returns:
            Agent instance
        """
        instance = AgentInstance(
            agent_id=agent_id,
            tenant_id=tenant_id,
            agent_type=agent_type,
            status=AgentStatus.CREATING,
            created_at=datetime.now(UTC),
            started_at=None,
            last_heartbeat=None,
            task_count=0,
            metadata=metadata or {},
        )

        self._agents[agent_id] = instance

        if tenant_id not in self._tenant_agents:
            self._tenant_agents[tenant_id] = set()
        self._tenant_agents[tenant_id].add(agent_id)

        logger.info(
            "agent_created",
            agent_id=agent_id,
            tenant_id=tenant_id,
            agent_type=agent_type,
        )

        return instance

    async def start_agent(self, agent_id: str) -> AgentInstance | None:
        """
        Start an agent instance.

        Args:
            agent_id: Agent identifier

        Returns:
            Updated agent instance or None if not found
        """
        if agent_id not in self._agents:
            return None

        instance = self._agents[agent_id]

        updated = AgentInstance(
            agent_id=instance.agent_id,
            tenant_id=instance.tenant_id,
            agent_type=instance.agent_type,
            status=AgentStatus.STARTING,
            created_at=instance.created_at,
            started_at=datetime.now(UTC),
            last_heartbeat=datetime.now(UTC),
            task_count=instance.task_count,
            metadata=instance.metadata,
        )

        self._agents[agent_id] = updated

        logger.info(
            "agent_started",
            agent_id=agent_id,
        )

        return updated

    async def activate_agent(self, agent_id: str) -> AgentInstance | None:
        """
        Activate an agent (transition to ACTIVE status).

        Args:
            agent_id: Agent identifier

        Returns:
            Updated agent instance or None if not found
        """
        if agent_id not in self._agents:
            return None

        instance = self._agents[agent_id]

        updated = AgentInstance(
            agent_id=instance.agent_id,
            tenant_id=instance.tenant_id,
            agent_type=instance.agent_type,
            status=AgentStatus.ACTIVE,
            created_at=instance.created_at,
            started_at=instance.started_at,
            last_heartbeat=datetime.now(UTC),
            task_count=instance.task_count,
            metadata=instance.metadata,
        )

        self._agents[agent_id] = updated

        logger.info(
            "agent_activated",
            agent_id=agent_id,
        )

        return updated

    async def set_agent_busy(self, agent_id: str) -> AgentInstance | None:
        """
        Mark agent as busy (processing a task).

        Args:
            agent_id: Agent identifier

        Returns:
            Updated agent instance or None if not found
        """
        if agent_id not in self._agents:
            return None

        instance = self._agents[agent_id]

        updated = AgentInstance(
            agent_id=instance.agent_id,
            tenant_id=instance.tenant_id,
            agent_type=instance.agent_type,
            status=AgentStatus.BUSY,
            created_at=instance.created_at,
            started_at=instance.started_at,
            last_heartbeat=datetime.now(UTC),
            task_count=instance.task_count + 1,
            metadata=instance.metadata,
        )

        self._agents[agent_id] = updated

        logger.debug(
            "agent_set_busy",
            agent_id=agent_id,
        )

        return updated

    async def set_agent_idle(self, agent_id: str) -> AgentInstance | None:
        """
        Mark agent as idle (ready for new tasks).

        Args:
            agent_id: Agent identifier

        Returns:
            Updated agent instance or None if not found
        """
        if agent_id not in self._agents:
            return None

        instance = self._agents[agent_id]

        updated = AgentInstance(
            agent_id=instance.agent_id,
            tenant_id=instance.tenant_id,
            agent_type=instance.agent_type,
            status=AgentStatus.IDLE,
            created_at=instance.created_at,
            started_at=instance.started_at,
            last_heartbeat=datetime.now(UTC),
            task_count=instance.task_count,
            metadata=instance.metadata,
        )

        self._agents[agent_id] = updated

        logger.debug(
            "agent_set_idle",
            agent_id=agent_id,
        )

        return updated

    async def suspend_agent(self, agent_id: str) -> AgentInstance | None:
        """
        Suspend an agent (pause processing).

        Args:
            agent_id: Agent identifier

        Returns:
            Updated agent instance or None if not found
        """
        if agent_id not in self._agents:
            return None

        instance = self._agents[agent_id]

        updated = AgentInstance(
            agent_id=instance.agent_id,
            tenant_id=instance.tenant_id,
            agent_type=instance.agent_type,
            status=AgentStatus.SUSPENDED,
            created_at=instance.created_at,
            started_at=instance.started_at,
            last_heartbeat=datetime.now(UTC),
            task_count=instance.task_count,
            metadata=instance.metadata,
        )

        self._agents[agent_id] = updated

        logger.info(
            "agent_suspended",
            agent_id=agent_id,
        )

        return updated

    async def resume_agent(self, agent_id: str) -> AgentInstance | None:
        """
        Resume a suspended agent.

        Args:
            agent_id: Agent identifier

        Returns:
            Updated agent instance or None if not found
        """
        if agent_id not in self._agents:
            return None

        instance = self._agents[agent_id]

        if instance.status != AgentStatus.SUSPENDED:
            return instance

        updated = AgentInstance(
            agent_id=instance.agent_id,
            tenant_id=instance.tenant_id,
            agent_type=instance.agent_type,
            status=AgentStatus.ACTIVE,
            created_at=instance.created_at,
            started_at=instance.started_at,
            last_heartbeat=datetime.now(UTC),
            task_count=instance.task_count,
            metadata=instance.metadata,
        )

        self._agents[agent_id] = updated

        logger.info(
            "agent_resumed",
            agent_id=agent_id,
        )

        return updated

    async def stop_agent(self, agent_id: str) -> AgentInstance | None:
        """
        Stop an agent gracefully.

        Args:
            agent_id: Agent identifier

        Returns:
            Updated agent instance or None if not found
        """
        if agent_id not in self._agents:
            return None

        instance = self._agents[agent_id]

        updated = AgentInstance(
            agent_id=instance.agent_id,
            tenant_id=instance.tenant_id,
            agent_type=instance.agent_type,
            status=AgentStatus.STOPPING,
            created_at=instance.created_at,
            started_at=instance.started_at,
            last_heartbeat=instance.last_heartbeat,
            task_count=instance.task_count,
            metadata=instance.metadata,
        )

        self._agents[agent_id] = updated

        logger.info(
            "agent_stopping",
            agent_id=agent_id,
        )

        return updated

    async def terminate_agent(self, agent_id: str) -> AgentInstance | None:
        """
        Terminate an agent forcefully.

        Args:
            agent_id: Agent identifier

        Returns:
            Updated agent instance or None if not found
        """
        if agent_id not in self._agents:
            return None

        instance = self._agents[agent_id]

        updated = AgentInstance(
            agent_id=instance.agent_id,
            tenant_id=instance.tenant_id,
            agent_type=instance.agent_type,
            status=AgentStatus.TERMINATED,
            created_at=instance.created_at,
            started_at=instance.started_at,
            last_heartbeat=instance.last_heartbeat,
            task_count=instance.task_count,
            metadata=instance.metadata,
        )

        self._agents[agent_id] = updated

        # Remove from tenant agents
        if instance.tenant_id in self._tenant_agents:
            self._tenant_agents[instance.tenant_id].discard(agent_id)

        logger.info(
            "agent_terminated",
            agent_id=agent_id,
        )

        return updated

    def update_heartbeat(self, agent_id: str) -> None:
        """
        Update agent heartbeat timestamp.

        Args:
            agent_id: Agent identifier
        """
        if agent_id not in self._agents:
            return

        instance = self._agents[agent_id]

        self._agents[agent_id] = AgentInstance(
            agent_id=instance.agent_id,
            tenant_id=instance.tenant_id,
            agent_type=instance.agent_type,
            status=instance.status,
            created_at=instance.created_at,
            started_at=instance.started_at,
            last_heartbeat=datetime.now(UTC),
            task_count=instance.task_count,
            metadata=instance.metadata,
        )

    def get_agent(self, agent_id: str) -> AgentInstance | None:
        """
        Get agent instance.

        Args:
            agent_id: Agent identifier

        Returns:
            Agent instance or None
        """
        return self._agents.get(agent_id)

    def get_tenant_agents(self, tenant_id: str) -> list[AgentInstance]:
        """
        Get all agents for a tenant.

        Args:
            tenant_id: Tenant UUID

        Returns:
            List of agent instances
        """
        agent_ids = self._tenant_agents.get(tenant_id, set())
        return [self._agents[aid] for aid in agent_ids if aid in self._agents]

    def get_agents_by_status(self, status: AgentStatus) -> list[AgentInstance]:
        """
        Get all agents with a specific status.

        Args:
            status: Agent status

        Returns:
            List of agent instances
        """
        return [agent for agent in self._agents.values() if agent.status == status]

    def get_idle_agents(self) -> list[AgentInstance]:
        """Get all idle agents ready for tasks."""
        return self.get_agents_by_status(AgentStatus.IDLE)

    def get_active_agents(self) -> list[AgentInstance]:
        """Get all active agents."""
        return self.get_agents_by_status(AgentStatus.ACTIVE)

    async def check_agent_health(self, timeout_seconds: int = 60) -> list[str]:
        """
        Check health of all agents and return unhealthy agent IDs.

        Args:
            timeout_seconds: Heartbeat timeout threshold

        Returns:
            List of unhealthy agent IDs
        """
        unhealthy = []
        threshold = datetime.now(UTC) - timedelta(seconds=timeout_seconds)

        for agent_id, instance in self._agents.items():
            if instance.last_heartbeat and instance.last_heartbeat < threshold:
                if instance.status in [AgentStatus.ACTIVE, AgentStatus.BUSY, AgentStatus.IDLE]:
                    unhealthy.append(agent_id)

                    # Mark as failed
                    self._agents[agent_id] = AgentInstance(
                        agent_id=instance.agent_id,
                        tenant_id=instance.tenant_id,
                        agent_type=instance.agent_type,
                        status=AgentStatus.FAILED,
                        created_at=instance.created_at,
                        started_at=instance.started_at,
                        last_heartbeat=instance.last_heartbeat,
                        task_count=instance.task_count,
                        metadata=instance.metadata,
                    )

                    logger.warning(
                        "agent_marked_unhealthy",
                        agent_id=agent_id,
                        last_heartbeat=instance.last_heartbeat.isoformat(),
                    )

        return unhealthy

    def get_agent_stats(self) -> dict[str, Any]:
        """
        Get agent statistics.

        Returns:
            Agent statistics
        """
        status_counts: dict[str, int] = {}
        total_tasks = 0

        for agent in self._agents.values():
            status_counts[agent.status] = status_counts.get(agent.status, 0) + 1
            total_tasks += agent.task_count

        return {
            "total_agents": len(self._agents),
            "status_breakdown": status_counts,
            "total_tasks_processed": total_tasks,
            "tenant_count": len(self._tenant_agents),
        }
