"""
Integration tests for Agent Lifecycle Manager.

Tests agent creation, activation, and lifecycle transitions.
"""

import pytest

from services.agent.agent_lifecycle import AgentLifecycleManager, AgentStatus


class TestAgentLifecycleManager:
    """Test suite for AgentLifecycleManager."""

    @pytest.fixture
    def lifecycle_manager(self):
        """Create lifecycle manager instance."""
        return AgentLifecycleManager()

    def test_create_agent(self, lifecycle_manager):
        """Test agent creation."""
        agent = lifecycle_manager.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-123",
            agent_type="chat",
        )

        assert agent.agent_id == "agent-1"
        assert agent.tenant_id == "tenant-123"
        assert agent.agent_type == "chat"
        assert agent.status == AgentStatus.CREATING

    @pytest.mark.asyncio
    async def test_start_agent(self, lifecycle_manager):
        """Test agent start."""
        lifecycle_manager.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-123",
            agent_type="chat",
        )

        agent = await lifecycle_manager.start_agent("agent-1")

        assert agent.status == AgentStatus.STARTING
        assert agent.started_at is not None

    @pytest.mark.asyncio
    async def test_activate_agent(self, lifecycle_manager):
        """Test agent activation."""
        lifecycle_manager.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-123",
            agent_type="chat",
        )
        await lifecycle_manager.start_agent("agent-1")

        agent = await lifecycle_manager.activate_agent("agent-1")

        assert agent.status == AgentStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_set_agent_busy(self, lifecycle_manager):
        """Test setting agent to busy."""
        lifecycle_manager.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-123",
            agent_type="chat",
        )
        await lifecycle_manager.start_agent("agent-1")
        await lifecycle_manager.activate_agent("agent-1")

        agent = await lifecycle_manager.set_agent_busy("agent-1")

        assert agent.status == AgentStatus.BUSY
        assert agent.task_count == 1

    @pytest.mark.asyncio
    async def test_set_agent_idle(self, lifecycle_manager):
        """Test setting agent to idle."""
        lifecycle_manager.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-123",
            agent_type="chat",
        )
        await lifecycle_manager.start_agent("agent-1")
        await lifecycle_manager.activate_agent("agent-1")
        await lifecycle_manager.set_agent_busy("agent-1")

        agent = await lifecycle_manager.set_agent_idle("agent-1")

        assert agent.status == AgentStatus.IDLE

    @pytest.mark.asyncio
    async def test_suspend_agent(self, lifecycle_manager):
        """Test agent suspension."""
        lifecycle_manager.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-123",
            agent_type="chat",
        )
        await lifecycle_manager.start_agent("agent-1")
        await lifecycle_manager.activate_agent("agent-1")

        agent = await lifecycle_manager.suspend_agent("agent-1")

        assert agent.status == AgentStatus.SUSPENDED

    @pytest.mark.asyncio
    async def test_resume_agent(self, lifecycle_manager):
        """Test agent resume."""
        lifecycle_manager.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-123",
            agent_type="chat",
        )
        await lifecycle_manager.start_agent("agent-1")
        await lifecycle_manager.activate_agent("agent-1")
        await lifecycle_manager.suspend_agent("agent-1")

        agent = await lifecycle_manager.resume_agent("agent-1")

        assert agent.status == AgentStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_terminate_agent(self, lifecycle_manager):
        """Test agent termination."""
        lifecycle_manager.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-123",
            agent_type="chat",
        )

        agent = await lifecycle_manager.terminate_agent("agent-1")

        assert agent.status == AgentStatus.TERMINATED

    def test_update_heartbeat(self, lifecycle_manager):
        """Test heartbeat update."""
        lifecycle_manager.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-123",
            agent_type="chat",
        )

        lifecycle_manager.update_heartbeat("agent-1")

        agent = lifecycle_manager.get_agent("agent-1")
        assert agent.last_heartbeat is not None

    def test_get_tenant_agents(self, lifecycle_manager):
        """Test getting tenant agents."""
        lifecycle_manager.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-123",
            agent_type="chat",
        )
        lifecycle_manager.create_agent(
            agent_id="agent-2",
            tenant_id="tenant-123",
            agent_type="chat",
        )
        lifecycle_manager.create_agent(
            agent_id="agent-3",
            tenant_id="tenant-456",
            agent_type="chat",
        )

        agents = lifecycle_manager.get_tenant_agents("tenant-123")

        assert len(agents) == 2
        assert all(a.tenant_id == "tenant-123" for a in agents)

    def test_get_idle_agents(self, lifecycle_manager):
        """Test getting idle agents."""
        lifecycle_manager.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-123",
            agent_type="chat",
        )

        idle_agents = lifecycle_manager.get_idle_agents()

        assert len(idle_agents) == 0

    def test_get_agent_stats(self, lifecycle_manager):
        """Test getting agent statistics."""
        lifecycle_manager.create_agent(
            agent_id="agent-1",
            tenant_id="tenant-123",
            agent_type="chat",
        )
        lifecycle_manager.create_agent(
            agent_id="agent-2",
            tenant_id="tenant-123",
            agent_type="chat",
        )

        stats = lifecycle_manager.get_agent_stats()

        assert stats["total_agents"] == 2
