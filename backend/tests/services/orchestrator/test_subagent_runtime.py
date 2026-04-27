"""
Tests for Butler Sub-Agent Runtime System
"""

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from domain.policy.capability_flags import TrustLevel
from services.orchestrator.subagent_runtime import (
    BudgetEnforcer,
    BudgetExceededError,
    CircuitBreaker,
    CircuitBreakerOpenError,
    RuntimeClass,
    SubAgentExecutor,
    SubAgentFactory,
    SubAgentProfile,
    TrustBoundaryViolationError,
)


@pytest.fixture
def base_profile() -> SubAgentProfile:
    """Base test sub-agent profile fixture."""
    return SubAgentProfile(
        parent_agent_id="parent:test",
        session_id="session:test",
        runtime_class=RuntimeClass.IN_PROCESS,
        trust_level=TrustLevel.VERIFIED_USER,
        tool_permissions={"tool:read", "tool:write"},
        memory_scope="session:test",
        max_execution_time_ms=1000,
        max_memory_mb=64,
        max_tool_calls=10,
        max_tokens=10000,
    )


@pytest.fixture
def low_trust_profile() -> SubAgentProfile:
    """Low trust sub-agent profile fixture."""
    return SubAgentProfile(
        parent_agent_id="parent:test",
        session_id="session:test",
        runtime_class=RuntimeClass.SANDBOX,
        trust_level=TrustLevel.UNTRUSTED,
        tool_permissions={"tool:read"},
        memory_scope="session:test",
    )


class TestRuntimeClass:
    def test_isolation_level_order(self) -> None:
        """Verify runtime isolation levels are correctly ordered."""
        assert RuntimeClass.IN_PROCESS.isolation_level == 0
        assert RuntimeClass.PROCESS_POOL.isolation_level == 1
        assert RuntimeClass.SANDBOX.isolation_level == 2
        assert RuntimeClass.REMOTE_PEER.isolation_level == 3
        assert RuntimeClass.HUMAN_GATE.isolation_level == 4

        assert RuntimeClass.IN_PROCESS.isolation_level < RuntimeClass.SANDBOX.isolation_level


class TestSubAgentProfile:
    def test_profile_creation(self, base_profile: SubAgentProfile) -> None:
        """Test basic profile creation with defaults."""
        assert base_profile.agent_id.startswith("sub:")
        assert base_profile.created_at <= datetime.now(UTC)
        assert base_profile.expires_at is None

    def test_expiry_validation(self) -> None:
        """Test expiry time validation."""
        with pytest.raises(ValueError, match="expires_at must be after created_at"):
            SubAgentProfile(
                parent_agent_id="parent:test",
                session_id="session:test",
                runtime_class=RuntimeClass.IN_PROCESS,
                trust_level=TrustLevel.VERIFIED_USER,
                memory_scope="session:test",
                expires_at=datetime.now(UTC) - timedelta(hours=1),
            )

    def test_in_process_trust_requirement(self) -> None:
        """Test in-process runtime requires minimum trust level."""
        with pytest.raises(
            ValueError, match="in-process execution requires trust level >= VERIFIED_USER"
        ):
            SubAgentProfile(
                parent_agent_id="parent:test",
                session_id="session:test",
                runtime_class=RuntimeClass.IN_PROCESS,
                trust_level=TrustLevel.INTERNAL,
                memory_scope="session:test",
            )

    def test_state_modification_trust_requirement(self) -> None:
        """Test state modification requires minimum trust level."""
        with pytest.raises(ValueError, match="state modification requires trust level >= 50"):
            SubAgentProfile(
                parent_agent_id="parent:test",
                session_id="session:test",
                runtime_class=RuntimeClass.SANDBOX,
                trust_level=TrustLevel.UNTRUSTED,
                memory_scope="session:test",
                allow_state_modification=True,
            )


class TestBudgetEnforcer:
    def test_budget_tracking(self, base_profile: SubAgentProfile) -> None:
        """Test basic budget tracking functionality."""
        budget = BudgetEnforcer(base_profile)
        budget.start()

        time.sleep(0.001)
        budget.check()

        assert budget.usage.execution_time_ms > 0
        assert not budget.is_terminated

    def test_execution_time_exceeded(self, base_profile: SubAgentProfile) -> None:
        """Test execution time budget enforcement."""
        profile = SubAgentProfile(
            parent_agent_id=base_profile.parent_agent_id,
            session_id=base_profile.session_id,
            runtime_class=base_profile.runtime_class,
            trust_level=base_profile.trust_level,
            tool_permissions=base_profile.tool_permissions,
            memory_scope=base_profile.memory_scope,
            max_execution_time_ms=1,
        )
        budget = BudgetEnforcer(profile)
        budget.start()

        time.sleep(0.002)

        with pytest.raises(BudgetExceededError, match="execution time exceeded"):
            budget.check()

        assert budget.is_terminated

    def test_tool_call_limit(self, base_profile: SubAgentProfile) -> None:
        """Test tool call budget enforcement."""
        profile = SubAgentProfile(
            parent_agent_id=base_profile.parent_agent_id,
            session_id=base_profile.session_id,
            runtime_class=base_profile.runtime_class,
            trust_level=base_profile.trust_level,
            tool_permissions=base_profile.tool_permissions,
            memory_scope=base_profile.memory_scope,
            max_tool_calls=2,
        )
        budget = BudgetEnforcer(profile)
        budget.start()

        budget.record_tool_call()
        budget.record_tool_call()

        with pytest.raises(BudgetExceededError, match="tool calls exceeded"):
            budget.record_tool_call()

        assert budget.is_terminated

    def test_token_limit(self, base_profile: SubAgentProfile) -> None:
        """Test token usage budget enforcement."""
        profile = SubAgentProfile(
            parent_agent_id=base_profile.parent_agent_id,
            session_id=base_profile.session_id,
            runtime_class=base_profile.runtime_class,
            trust_level=base_profile.trust_level,
            tool_permissions=base_profile.tool_permissions,
            memory_scope=base_profile.memory_scope,
            max_tokens=100,
        )
        budget = BudgetEnforcer(profile)
        budget.start()

        budget.record_tokens(50)

        with pytest.raises(BudgetExceededError):
            budget.record_tokens(60)

        assert budget.is_terminated


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_circuit_closed_initially(self) -> None:
        """Test circuit breaker starts in closed state."""
        cb = CircuitBreaker(name="test_cb", failure_threshold=3)
        state = await cb.current_state()
        assert state == "CLOSED"
        assert await cb.allow_execution() is True

    @pytest.mark.asyncio
    async def test_circuit_opens_after_failures(self) -> None:
        """Test circuit opens after threshold failures."""
        cb = CircuitBreaker(name="test_cb", failure_threshold=3)

        await cb.record_failure()
        await cb.record_failure()
        state = await cb.current_state()
        assert state == "CLOSED"
        assert await cb.allow_execution() is True

        await cb.record_failure()
        state = await cb.current_state()
        assert state == "OPEN"
        assert await cb.allow_execution() is False

    @pytest.mark.asyncio
    async def test_circuit_resets_after_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test circuit resets after timeout period."""
        cb = CircuitBreaker(name="test_cb", failure_threshold=2, reset_timeout_ms=100)

        await cb.record_failure()
        await cb.record_failure()
        state = await cb.current_state()
        assert state == "OPEN"

        # Fast forward time
        current_time = time.perf_counter()
        monkeypatch.setattr(time, "perf_counter", lambda: current_time + 0.2)

        assert await cb.allow_execution() is True
        state = await cb.current_state()
        assert state == "HALF_OPEN"

    @pytest.mark.asyncio
    async def test_circuit_closes_after_success(self) -> None:
        """Test circuit closes after successful execution."""
        cb = CircuitBreaker(name="test_cb", failure_threshold=2)

        await cb.record_failure()
        await cb.record_failure()
        state = await cb.current_state()
        assert state == "OPEN"

        await cb.record_success()
        state = await cb.current_state()
        assert state == "CLOSED"
        assert cb._state.failure_count == 0


class TestSubAgentFactory:
    def test_child_agent_inheritance(self, base_profile: SubAgentProfile) -> None:
        """Test child agent inherits parent properties correctly."""
        child = SubAgentFactory.create_child(base_profile)

        assert child.parent_agent_id == base_profile.parent_agent_id
        assert child.session_id == base_profile.session_id
        assert child.runtime_class == base_profile.runtime_class
        assert child.trust_level == base_profile.trust_level
        assert child.tool_permissions == base_profile.tool_permissions
        assert child.memory_scope == base_profile.memory_scope

    def test_child_cannot_escalate_isolation(self, base_profile: SubAgentProfile) -> None:
        """Test child cannot use higher isolation runtime than parent."""
        with pytest.raises(TrustBoundaryViolationError, match="higher isolation runtime"):
            SubAgentFactory.create_child(
                base_profile,
                runtime_class=RuntimeClass.HUMAN_GATE,
            )

    def test_child_cannot_escalate_permissions(self, base_profile: SubAgentProfile) -> None:
        """Test child cannot receive permissions parent doesn't have."""
        with pytest.raises(
            TrustBoundaryViolationError, match="cannot grant permissions not held by parent"
        ):
            SubAgentFactory.create_child(
                base_profile,
                additional_permissions={"tool:read", "tool:delete"},
            )

    def test_child_cannot_exceed_budget(self, base_profile: SubAgentProfile) -> None:
        """Test child budget cannot exceed parent limits."""
        with pytest.raises(
            TrustBoundaryViolationError,
            match="budget override max_tool_calls=20 exceeds parent limit 10",
        ):
            SubAgentFactory.create_child(
                base_profile,
                budget_overrides={"max_tool_calls": 20},
            )

    def test_child_reduced_budget_allowed(self, base_profile: SubAgentProfile) -> None:
        """Test child can have reduced budget limits."""
        child = SubAgentFactory.create_child(
            base_profile,
            budget_overrides={"max_tool_calls": 5, "max_tokens": 5000},
        )

        assert child.max_tool_calls == 5
        assert child.max_tokens == 5000


class TestSubAgentExecutor:
    @pytest.mark.asyncio
    async def test_executor_execution(self, base_profile: SubAgentProfile) -> None:
        """Test basic executor functionality."""
        executor = SubAgentExecutor(base_profile)

        mock_task = AsyncMock(return_value="test_result")
        result = await executor.execute(mock_task, "arg1", kwarg1="value1")

        assert result == "test_result"
        mock_task.assert_called_once_with("arg1", kwarg1="value1")

    @pytest.mark.asyncio
    async def test_executor_circuit_breaker_open(self, base_profile: SubAgentProfile) -> None:
        """Test executor blocks execution when circuit breaker is open."""
        executor = SubAgentExecutor(base_profile)

        # Trigger circuit breaker
        for _ in range(5):
            await executor.circuit_breaker.record_failure()

        state = await executor.circuit_breaker.current_state()
        assert state == "OPEN"

        mock_task = AsyncMock()
        with pytest.raises(CircuitBreakerOpenError, match="Circuit breaker"):
            await executor.execute(mock_task)

        mock_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_executor_budget_enforcement(self, base_profile: SubAgentProfile) -> None:
        """Test executor enforces budget during execution."""
        profile = SubAgentProfile(
            parent_agent_id=base_profile.parent_agent_id,
            session_id=base_profile.session_id,
            runtime_class=base_profile.runtime_class,
            trust_level=base_profile.trust_level,
            tool_permissions=base_profile.tool_permissions,
            memory_scope=base_profile.memory_scope,
            max_execution_time_ms=1,
        )
        executor = SubAgentExecutor(profile)

        async def slow_task() -> str:
            time.sleep(0.002)
            return "slow_result"

        with pytest.raises(BudgetExceededError, match="execution time exceeded"):
            await executor.execute(slow_task)

    def test_executor_interrupt(self, base_profile: SubAgentProfile) -> None:
        """Test executor graceful interrupt."""
        executor = SubAgentExecutor(base_profile)
        executor.budget.start()

        assert not executor.budget.is_terminated
        executor.interrupt()
        assert executor.budget.is_terminated
