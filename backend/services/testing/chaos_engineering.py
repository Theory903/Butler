"""
Chaos Engineering - Chaos Engineering Tools

Implements chaos engineering tools for system resilience testing.
Supports fault injection, failure simulation, and resilience metrics.
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


class FaultType(StrEnum):
    """Fault type."""

    LATENCY = "latency"
    ERROR = "error"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    CORRUPTION = "corruption"


@dataclass(frozen=True, slots=True)
class FaultConfig:
    """Fault configuration."""

    fault_id: str
    fault_type: FaultType
    target_service: str
    probability: float  # 0.0 to 1.0
    parameters: dict[str, Any]
    enabled: bool


@dataclass(frozen=True, slots=True)
class FaultExecution:
    """Fault execution record."""

    execution_id: str
    fault_id: str
    triggered_at: datetime
    successful: bool
    impact: str | None


class ChaosEngineer:
    """
    Chaos engineering service.

    Features:
    - Fault injection
    - Failure simulation
    - Resilience testing
    - Impact monitoring
    """

    def __init__(self) -> None:
        """Initialize chaos engineer."""
        self._faults: dict[str, FaultConfig] = {}
        self._executions: list[FaultExecution] = []
        self._fault_callback: Callable[[FaultConfig], Awaitable[bool]] | None = None

    def set_fault_callback(
        self,
        callback: Callable[[FaultConfig], Awaitable[bool]],
    ) -> None:
        """
        Set callback for fault injection.

        Args:
            callback: Async function to inject fault
        """
        self._fault_callback = callback

    def add_fault(
        self,
        fault_id: str,
        fault_type: FaultType,
        target_service: str,
        probability: float,
        parameters: dict[str, Any],
    ) -> FaultConfig:
        """
        Add a fault configuration.

        Args:
            fault_id: Fault identifier
            fault_type: Fault type
            target_service: Target service
            probability: Fault probability (0.0 to 1.0)
            parameters: Fault parameters

        Returns:
            Fault configuration
        """
        fault = FaultConfig(
            fault_id=fault_id,
            fault_type=fault_type,
            target_service=target_service,
            probability=probability,
            parameters=parameters,
            enabled=True,
        )

        self._faults[fault_id] = fault

        logger.info(
            "fault_added",
            fault_id=fault_id,
            fault_type=fault_type,
            target_service=target_service,
            probability=probability,
        )

        return fault

    async def inject_fault(
        self,
        fault_id: str,
    ) -> FaultExecution:
        """
        Inject a fault.

        Args:
            fault_id: Fault identifier

        Returns:
            Fault execution record
        """
        fault = self._faults.get(fault_id)

        if not fault:
            raise ValueError(f"Fault not found: {fault_id}")

        if not fault.enabled:
            raise ValueError(f"Fault not enabled: {fault_id}")

        execution_id = f"exec-{datetime.now(UTC).timestamp()}"

        try:
            if self._fault_callback:
                success = await self._fault_callback(fault)
            else:
                # Simulate fault injection
                await asyncio.sleep(0.1)
                success = True

            execution = FaultExecution(
                execution_id=execution_id,
                fault_id=fault_id,
                triggered_at=datetime.now(UTC),
                successful=success,
                impact="fault_injected" if success else "injection_failed",
            )

            self._executions.append(execution)

            logger.info(
                "fault_injected",
                execution_id=execution_id,
                fault_id=fault_id,
            )

            return execution

        except Exception as e:
            execution = FaultExecution(
                execution_id=execution_id,
                fault_id=fault_id,
                triggered_at=datetime.now(UTC),
                successful=False,
                impact=str(e),
            )

            self._executions.append(execution)

            logger.error(
                "fault_injection_failed",
                execution_id=execution_id,
                fault_id=fault_id,
                error=str(e),
            )

            return execution

    async def inject_random_faults(
        self,
        target_service: str | None = None,
        count: int = 1,
    ) -> list[FaultExecution]:
        """
        Inject random faults.

        Args:
            target_service: Target service filter
            count: Number of faults to inject

        Returns:
            List of fault execution records
        """
        import random

        # Filter faults
        faults = list(self._faults.values())

        if target_service:
            faults = [f for f in faults if f.target_service == target_service]

        faults = [f for f in faults if f.enabled]

        # Select random faults based on probability
        selected_faults = []
        for fault in faults:
            if random.random() < fault.probability:
                selected_faults.append(fault)

        # Limit to count
        selected_faults = selected_faults[:count]

        # Inject faults
        executions = []
        for fault in selected_faults:
            execution = await self.inject_fault(fault.fault_id)
            executions.append(execution)

        return executions

    async def simulate_latency(
        self,
        target_service: str,
        delay_ms: int,
        probability: float = 1.0,
    ) -> FaultExecution:
        """
        Simulate latency.

        Args:
            target_service: Target service
            delay_ms: Delay in milliseconds
            probability: Probability of applying latency

        Returns:
            Fault execution record
        """
        fault_id = f"latency-{target_service}-{datetime.now(UTC).timestamp()}"

        self.add_fault(
            fault_id=fault_id,
            fault_type=FaultType.LATENCY,
            target_service=target_service,
            probability=probability,
            parameters={"delay_ms": delay_ms},
        )

        execution = await self.inject_fault(fault_id)

        # Remove temporary fault
        self.remove_fault(fault_id)

        return execution

    async def simulate_error(
        self,
        target_service: str,
        error_code: int,
        probability: float = 1.0,
    ) -> FaultExecution:
        """
        Simulate error response.

        Args:
            target_service: Target service
            error_code: HTTP error code
            probability: Probability of returning error

        Returns:
            Fault execution record
        """
        fault_id = f"error-{target_service}-{datetime.now(UTC).timestamp()}"

        self.add_fault(
            fault_id=fault_id,
            fault_type=FaultType.ERROR,
            target_service=target_service,
            probability=probability,
            parameters={"error_code": error_code},
        )

        execution = await self.inject_fault(fault_id)

        # Remove temporary fault
        self.remove_fault(fault_id)

        return execution

    def disable_fault(self, fault_id: str) -> bool:
        """
        Disable a fault.

        Args:
            fault_id: Fault identifier

        Returns:
            True if disabled
        """
        if fault_id in self._faults:
            fault = self._faults[fault_id]
            disabled_fault = FaultConfig(
                fault_id=fault.fault_id,
                fault_type=fault.fault_type,
                target_service=fault.target_service,
                probability=fault.probability,
                parameters=fault.parameters,
                enabled=False,
            )

            self._faults[fault_id] = disabled_fault

            logger.info(
                "fault_disabled",
                fault_id=fault_id,
            )

            return True
        return False

    def enable_fault(self, fault_id: str) -> bool:
        """
        Enable a fault.

        Args:
            fault_id: Fault identifier

        Returns:
            True if enabled
        """
        if fault_id in self._faults:
            fault = self._faults[fault_id]
            enabled_fault = FaultConfig(
                fault_id=fault.fault_id,
                fault_type=fault.fault_type,
                target_service=fault.target_service,
                probability=fault.probability,
                parameters=fault.parameters,
                enabled=True,
            )

            self._faults[fault_id] = enabled_fault

            logger.info(
                "fault_enabled",
                fault_id=fault_id,
            )

            return True
        return False

    def remove_fault(self, fault_id: str) -> bool:
        """
        Remove a fault.

        Args:
            fault_id: Fault identifier

        Returns:
            True if removed
        """
        if fault_id in self._faults:
            del self._faults[fault_id]

            logger.info(
                "fault_removed",
                fault_id=fault_id,
            )

            return True
        return False

    def get_faults(
        self,
        target_service: str | None = None,
        enabled: bool | None = None,
    ) -> list[FaultConfig]:
        """
        Get fault configurations.

        Args:
            target_service: Filter by target service
            enabled: Filter by enabled status

        Returns:
            List of fault configurations
        """
        faults = list(self._faults.values())

        if target_service:
            faults = [f for f in faults if f.target_service == target_service]

        if enabled is not None:
            faults = [f for f in faults if f.enabled == enabled]

        return faults

    def get_executions(
        self,
        fault_id: str | None = None,
        limit: int = 100,
    ) -> list[FaultExecution]:
        """
        Get fault execution records.

        Args:
            fault_id: Filter by fault ID
            limit: Maximum number of records

        Returns:
            List of fault execution records
        """
        executions = self._executions

        if fault_id:
            executions = [e for e in executions if e.fault_id == fault_id]

        return sorted(executions, key=lambda e: e.triggered_at, reverse=True)[:limit]

    def get_chaos_stats(self) -> dict[str, Any]:
        """
        Get chaos engineering statistics.

        Returns:
            Chaos statistics
        """
        total_faults = len(self._faults)
        enabled_faults = sum(1 for f in self._faults.values() if f.enabled)
        total_executions = len(self._executions)
        successful_executions = sum(1 for e in self._executions if e.successful)

        fault_type_counts: dict[str, int] = {}
        for fault in self._faults.values():
            fault_type_counts[fault.fault_type] = fault_type_counts.get(fault.fault_type, 0) + 1

        return {
            "total_faults": total_faults,
            "enabled_faults": enabled_faults,
            "total_executions": total_executions,
            "successful_executions": successful_executions,
            "failed_executions": total_executions - successful_executions,
            "fault_type_breakdown": fault_type_counts,
        }
