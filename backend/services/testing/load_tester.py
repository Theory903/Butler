"""
Load Tester - Load Testing Framework

Implements load testing framework for API performance testing.
Supports concurrent requests, ramp-up patterns, and performance metrics.
"""

from __future__ import annotations

import asyncio
import statistics
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class RampUpStrategy(StrEnum):
    """Ramp-up strategy."""

    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    STEP = "step"
    INSTANT = "instant"


@dataclass(frozen=True, slots=True)
class LoadTestConfig:
    """Load test configuration."""

    test_id: str
    target_url: str
    method: str
    headers: dict[str, str]
    body: Any | None
    target_rps: int  # Requests per second
    duration_seconds: int
    ramp_up_strategy: RampUpStrategy
    ramp_up_duration: int


@dataclass(frozen=True, slots=True)
class TestResult:
    """Test result."""

    request_id: str
    status_code: int | None
    response_time_ms: float
    success: bool
    error: str | None
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class LoadTestSummary:
    """Load test summary."""

    test_id: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_response_time_ms: float
    p50_response_time_ms: float
    p95_response_time_ms: float
    p99_response_time_ms: float
    min_response_time_ms: float
    max_response_time_ms: float
    actual_rps: float
    duration_seconds: float
    started_at: datetime
    completed_at: datetime


class LoadTester:
    """
    Load testing framework.

    Features:
    - Concurrent request execution
    - Ramp-up strategies
    - Performance metrics
    - Real-time monitoring
    """

    def __init__(self) -> None:
        """Initialize load tester."""
        self._results: list[TestResult] = []
        self._request_callback: (
            Callable[[str, str, dict[str, str], Any | None], Awaitable[TestResult]] | None
        ) = None

    def set_request_callback(
        self,
        callback: Callable[[str, str, dict[str, str], Any | None], Awaitable[TestResult]],
    ) -> None:
        """
        Set callback for executing requests.

        Args:
            callback: Async function to execute a request
        """
        self._request_callback = callback

    async def execute_test(
        self,
        config: LoadTestConfig,
    ) -> LoadTestSummary:
        """
        Execute a load test.

        Args:
            config: Load test configuration

        Returns:
            Load test summary
        """
        if not self._request_callback:
            raise ValueError("Request callback not configured")

        callback = self._request_callback
        assert callback is not None

        started_at = datetime.now(UTC)

        # Calculate ramp-up schedule
        schedule = self._calculate_ramp_schedule(config)

        # Execute requests according to schedule
        tasks = []

        for second, rps in enumerate(schedule):
            if second >= config.duration_seconds:
                break

            for _ in range(rps):
                task = asyncio.create_task(self._execute_request(config, second, callback))
                tasks.append(task)

            # Wait for the second
            await asyncio.sleep(1)

        # Wait for all tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)

        completed_at = datetime.now(UTC)

        # Calculate summary
        summary = self._calculate_summary(config.test_id, started_at, completed_at)

        logger.info(
            "load_test_completed",
            test_id=config.test_id,
            total_requests=summary.total_requests,
            success_rate=summary.successful_requests / summary.total_requests
            if summary.total_requests > 0
            else 0,
            avg_response_time_ms=summary.avg_response_time_ms,
        )

        return summary

    def _calculate_ramp_schedule(self, config: LoadTestConfig) -> list[int]:
        """
        Calculate ramp-up schedule.

        Args:
            config: Load test configuration

        Returns:
            List of RPS for each second
        """
        schedule = []

        if config.ramp_up_strategy == RampUpStrategy.INSTANT:
            # Instant ramp-up
            schedule = [config.target_rps] * config.duration_seconds

        elif config.ramp_up_strategy == RampUpStrategy.LINEAR:
            # Linear ramp-up
            for second in range(config.duration_seconds):
                if second < config.ramp_up_duration:
                    rps = int(config.target_rps * (second + 1) / config.ramp_up_duration)
                else:
                    rps = config.target_rps
                schedule.append(rps)

        elif config.ramp_up_strategy == RampUpStrategy.EXPONENTIAL:
            # Exponential ramp-up
            for second in range(config.duration_seconds):
                if second < config.ramp_up_duration:
                    progress = (second + 1) / config.ramp_up_duration
                    rps = int(config.target_rps * (progress**2))
                else:
                    rps = config.target_rps
                schedule.append(rps)

        elif config.ramp_up_strategy == RampUpStrategy.STEP:
            # Step ramp-up
            steps = 5
            step_size = config.target_rps // steps
            for second in range(config.duration_seconds):
                if second < config.ramp_up_duration:
                    step = min((second + 1) // (config.ramp_up_duration // steps), steps)
                    rps = step_size * (step + 1)
                else:
                    rps = config.target_rps
                schedule.append(rps)

        return schedule

    async def _execute_request(
        self,
        config: LoadTestConfig,
        second: int,
        callback: Callable[[str, str, dict[str, str], Any | None], Awaitable[TestResult]],
    ) -> TestResult:
        """
        Execute a single request.

        Args:
            config: Load test configuration
            second: Second in test
            callback: Request callback

        Returns:
            Test result
        """
        request_id = f"req-{datetime.now(UTC).timestamp()}-{second}"

        try:
            result = await callback(
                config.target_url,
                config.method,
                config.headers,
                config.body,
            )

            self._results.append(result)

            return result

        except Exception as e:
            error_result = TestResult(
                request_id=request_id,
                status_code=None,
                response_time_ms=0,
                success=False,
                error=str(e),
                timestamp=datetime.now(UTC),
            )

            self._results.append(error_result)

            return error_result

    def _calculate_summary(
        self,
        test_id: str,
        started_at: datetime,
        completed_at: datetime,
    ) -> LoadTestSummary:
        """
        Calculate load test summary.

        Args:
            test_id: Test identifier
            started_at: Test start time
            completed_at: Test completion time

        Returns:
            Load test summary
        """
        total_requests = len(self._results)
        successful_requests = sum(1 for r in self._results if r.success)
        failed_requests = total_requests - successful_requests

        response_times = [r.response_time_ms for r in self._results if r.success]

        if response_times:
            avg_response_time = statistics.mean(response_times)
            sorted_times = sorted(response_times)
            p50 = sorted_times[len(sorted_times) // 2]
            p95 = sorted_times[int(len(sorted_times) * 0.95)]
            p99 = sorted_times[int(len(sorted_times) * 0.99)]
            min_response_time = min(response_times)
            max_response_time = max(response_times)
        else:
            avg_response_time = 0
            p50 = 0
            p95 = 0
            p99 = 0
            min_response_time = 0
            max_response_time = 0

        duration_seconds = (completed_at - started_at).total_seconds()
        actual_rps = total_requests / duration_seconds if duration_seconds > 0 else 0

        return LoadTestSummary(
            test_id=test_id,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            avg_response_time_ms=avg_response_time,
            p50_response_time_ms=p50,
            p95_response_time_ms=p95,
            p99_response_time_ms=p99,
            min_response_time_ms=min_response_time,
            max_response_time_ms=max_response_time,
            actual_rps=actual_rps,
            duration_seconds=duration_seconds,
            started_at=started_at,
            completed_at=completed_at,
        )

    def get_results(
        self,
        test_id: str | None = None,
        success: bool | None = None,
        limit: int = 100,
    ) -> list[TestResult]:
        """
        Get test results.

        Args:
            test_id: Filter by test ID
            success: Filter by success status
            limit: Maximum number of results

        Returns:
            List of test results
        """
        results = self._results

        if success is not None:
            results = [r for r in results if r.success == success]

        return sorted(results, key=lambda r: r.timestamp, reverse=True)[:limit]

    def clear_results(self) -> None:
        """Clear all test results."""
        self._results.clear()
        logger.info("test_results_cleared")
