from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True, slots=True)
class ShadowExecutionResult:
    shadow_model: str
    success: bool
    primary_status: str | None = None
    shadow_status: str | None = None
    mismatch: bool = False
    error: str | None = None
    latency_ms: float = 0.0


class MLAdmin:
    """Administrative controls for the Butler ML platform.

    Responsibilities:
    - runtime feature flags
    - lightweight platform counters
    - safe concurrent access from async callers
    """

    _DEFAULT_FLAGS: dict[str, Any] = {
        "enable_t2_escalation": True,
        "enable_t3_escalation": True,
        "shadow_mode_enabled": False,
        "rerank_ml_weight": 0.7,
        "rerank_signal_weight": 0.3,
    }

    _DEFAULT_METRICS: dict[str, int] = {
        "requests_total": 0,
        "shadow_mismatch_count": 0,
        "errors_total": 0,
        "shadow_requests_total": 0,
        "shadow_failures_total": 0,
    }

    def __init__(
        self,
        *,
        initial_flags: Mapping[str, Any] | None = None,
        initial_metrics: Mapping[str, int] | None = None,
    ) -> None:
        self._lock = asyncio.Lock()
        self._started_at = time.monotonic()

        self._flags: dict[str, Any] = dict(self._DEFAULT_FLAGS)
        if initial_flags:
            self._flags.update(dict(initial_flags))

        self._metrics: dict[str, int] = dict(self._DEFAULT_METRICS)
        if initial_metrics:
            for key, value in initial_metrics.items():
                self._metrics[key] = int(value)

    async def get_flag(self, name: str, default: Any = None) -> Any:
        async with self._lock:
            return self._flags.get(name, default)

    async def get_flags(self) -> dict[str, Any]:
        async with self._lock:
            return dict(self._flags)

    async def set_flag(self, name: str, value: Any) -> None:
        async with self._lock:
            old_value = self._flags.get(name)
            self._flags[name] = value

        logger.info(
            "admin_flag_changed",
            extra={"name": name, "old": old_value, "new": value},
        )

    async def update_metrics(self, category: str, increment: int = 1) -> None:
        async with self._lock:
            self._metrics[category] = int(self._metrics.get(category, 0)) + int(increment)

    async def set_metric(self, category: str, value: int) -> None:
        async with self._lock:
            self._metrics[category] = int(value)

    async def get_stats(self) -> dict[str, Any]:
        async with self._lock:
            flags = dict(self._flags)
            metrics = dict(self._metrics)

        uptime_seconds = max(0.0, time.monotonic() - self._started_at)
        return {
            "flags": flags,
            "metrics": metrics,
            "uptime_seconds": round(uptime_seconds, 3),
            "uptime_status": HealthStatus.HEALTHY.value,
        }


class HealthProbe:
    """Observability probes for the ML platform."""

    def __init__(self, registry: Any) -> None:
        self._registry = registry

    async def check_readiness(self) -> dict[str, Any]:
        """Check whether the ML platform is ready to serve traffic."""
        results: dict[str, str] = {}

        try:
            entries = self._registry.list_entries()
            results["registry"] = "ok" if entries else "empty"
        except Exception as exc:
            logger.exception("health_probe_registry_failed")
            return {
                "status": HealthStatus.UNHEALTHY.value,
                "probes": {"registry": f"fail:{exc}"},
            }

        try:
            t2_models = self._registry.get_active_by_tier(2)
            results["t2_backends"] = "available" if t2_models else "empty"
        except Exception as exc:
            results["t2_backends"] = f"fail:{exc}"

        try:
            t3_models = self._registry.get_active_by_tier(3)
            results["t3_backends"] = "available" if t3_models else "empty"
        except Exception as exc:
            results["t3_backends"] = f"fail:{exc}"

        status = self._derive_status(results)

        return {
            "status": status.value,
            "probes": results,
        }

    def _derive_status(self, results: Mapping[str, str]) -> HealthStatus:
        values = list(results.values())

        if any(value.startswith("fail") for value in values):
            return HealthStatus.UNHEALTHY

        if any(value == "empty" for value in values):
            return HealthStatus.DEGRADED

        return HealthStatus.HEALTHY


class ShadowManager:
    """Manage asynchronous shadow inference execution.

    Design goals:
    - retain references to background tasks
    - record failures explicitly
    - support graceful shutdown/drain
    """

    def __init__(self, runtime: Any, admin: MLAdmin | None = None) -> None:
        self._runtime = runtime
        self._admin = admin
        self._tasks: set[asyncio.Task[None]] = set()
        self._lock = asyncio.Lock()

    async def execute_shadow(
        self,
        primary_result: Any,
        shadow_model: str,
        request_data: dict[str, Any],
    ) -> None:
        """Schedule a shadow request and return immediately."""
        if not shadow_model:
            return

        if self._admin is not None:
            await self._admin.update_metrics("shadow_requests_total", 1)

        task = asyncio.create_task(
            self._run_shadow(
                primary_result=primary_result, shadow_model=shadow_model, request_data=request_data
            ),
            name=f"shadow:{shadow_model}",
        )

        async with self._lock:
            self._tasks.add(task)

        task.add_done_callback(self._on_task_done)

    async def shutdown(self) -> None:
        """Wait for in-flight shadow tasks to finish."""
        async with self._lock:
            tasks = list(self._tasks)

        if not tasks:
            return

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.warning("shadow_shutdown_task_failed", extra={"error": str(result)})

    async def _run_shadow(
        self,
        *,
        primary_result: Any,
        shadow_model: str,
        request_data: dict[str, Any],
    ) -> None:
        started_at = time.monotonic()

        try:
            shadow_result = await self._runtime.execute_inference(shadow_model, request_data)
            latency_ms = (time.monotonic() - started_at) * 1000.0

            comparison = self._compare_results(
                primary_result=primary_result,
                shadow_result=shadow_result,
                shadow_model=shadow_model,
                latency_ms=latency_ms,
            )

            if comparison.mismatch and self._admin is not None:
                await self._admin.update_metrics("shadow_mismatch_count", 1)

            logger.debug(
                "shadow_execution_complete",
                extra={
                    "model": comparison.shadow_model,
                    "success": comparison.success,
                    "mismatch": comparison.mismatch,
                    "latency_ms": round(comparison.latency_ms, 2),
                    "primary_status": comparison.primary_status,
                    "shadow_status": comparison.shadow_status,
                },
            )

        except Exception as exc:
            if self._admin is not None:
                await self._admin.update_metrics("shadow_failures_total", 1)
                await self._admin.update_metrics("errors_total", 1)

            logger.warning(
                "shadow_execution_failed",
                extra={"model": shadow_model, "error": str(exc)},
            )

    def _compare_results(
        self,
        *,
        primary_result: Any,
        shadow_result: Any,
        shadow_model: str,
        latency_ms: float,
    ) -> ShadowExecutionResult:
        primary_status = self._extract_status(primary_result)
        shadow_status = self._extract_status(shadow_result)

        primary_content = self._extract_content(primary_result)
        shadow_content = self._extract_content(shadow_result)

        mismatch = (primary_status != shadow_status) or (primary_content != shadow_content)

        return ShadowExecutionResult(
            shadow_model=shadow_model,
            success=shadow_status == "success",
            primary_status=primary_status,
            shadow_status=shadow_status,
            mismatch=mismatch,
            latency_ms=latency_ms,
        )

    def _extract_status(self, result: Any) -> str | None:
        if isinstance(result, Mapping):
            value = result.get("status")
            return str(value) if value is not None else None
        return getattr(result, "status", None)

    def _extract_content(self, result: Any) -> str | None:
        if isinstance(result, Mapping):
            value = result.get("content")
            return str(value) if value is not None else None
        value = getattr(result, "content", None)
        return str(value) if value is not None else None

    def _on_task_done(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)

        with contextlib.suppress(asyncio.CancelledError):
            exc = task.exception()
            if exc is not None:
                logger.warning(
                    "shadow_task_unhandled_exception",
                    extra={"task_name": task.get_name(), "error": str(exc)},
                )
