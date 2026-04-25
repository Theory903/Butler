"""
Gateway Throughput Benchmarks - ≥10K RPS target.
Tests tool governance under load.
"""

import asyncio
import time
from collections.abc import Callable


class ThroughputBenchmark:
    """Benchmark gateway throughput with tool governance."""

    def __init__(
        self,
        target_rps: int = 10000,
        duration_seconds: int = 60,
        warmup_seconds: int = 5,
    ):
        self.target_rps = target_rps
        self.duration_seconds = duration_seconds
        self.warmup_seconds = warmup_seconds

    async def run(
        self,
        request_handler: Callable,
        num_concurrent: int = 100,
    ):
        results = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "p50_latency_ms": 0,
            "p95_latency_ms": 0,
            "p99_latency_ms": 0,
            "peak_rps": 0,
        }

        start_time = time.time()
        latencies = []

        async def make_request():
            req_start = time.time()
            try:
                await request_handler()
                latencies.append((time.time() - req_start) * 1000)
                results["successful_requests"] += 1
            except Exception:
                results["failed_requests"] += 1
            results["total_requests"] += 1

        tasks = []
        for _ in range(num_concurrent):
            task = asyncio.create_task(make_request())
            tasks.append(task)
            await asyncio.sleep(1.0 / num_concurrent)

        await asyncio.gather(*tasks, return_exceptions=True)

        elapsed = time.time() - start_time
        if latencies:
            sorted_latencies = sorted(latencies)
            results["p50_latency_ms"] = sorted_latencies[len(sorted_latencies) // 2]
            results["p95_latency_ms"] = sorted_latencies[int(len(sorted_latencies) * 0.95)]
            results["p99_latency_ms"] = sorted_latencies[int(len(sorted_latencies) * 0.99)]

        results["peak_rps"] = results["total_requests"] / elapsed
        results["target_achieved"] = results["peak_rps"] >= self.target_rps

        return results


async def benchmark_tools():
    """Benchmark tool execution with governance."""
    from services.tools.executor import ToolExecutor

    executor = ToolExecutor()

    benchmark = ThroughputBenchmark(target_rps=10000)

    async def handler():
        await executor.execute(
            tool_name="test_tool",
            args={"query": "test"},
        )

    return await benchmark.run(handler)
