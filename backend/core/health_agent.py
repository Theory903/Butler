from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any, Literal

import psutil
import structlog
from redis.asyncio import Redis

from core.observability import ButlerMetrics, get_metrics
from core.state_sync import GlobalStateSyncer
from infrastructure.config import settings

logger = structlog.get_logger(__name__)

NodeStatus = Literal["STARTING", "HEALTHY", "DEGRADED", "UNHEALTHY"]


class ButlerHealthAgent:
    """Autonomous agent for cluster health and self-healing.

    Responsibilities:
    - publish local node heartbeat
    - derive local node health from resource pressure
    - aggregate cluster health
    - detect dead nodes by comparing presence state vs active node registry
    - trigger cleanup for dead nodes

    Notes:
    - this implementation avoids Redis KEYS in favor of SCAN
    - all long-running loops are cancellation-safe
    - task shutdown is awaited cleanly
    """

    def __init__(
        self,
        redis: Redis,
        syncer: GlobalStateSyncer,
        node_id: str = settings.BUTLER_NODE_ID,
        metrics: ButlerMetrics | None = None,
    ) -> None:
        self._redis = redis
        self._syncer = syncer
        self._node_id = node_id
        self._metrics = metrics or get_metrics()

        self._is_running = False
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._reaper_task: asyncio.Task[None] | None = None

        self._node_key = f"butler:nodes:{self._node_id}"
        self._cluster_health_key = "butler:cluster:health"

        self._heartbeat_interval = 5
        self._reaper_interval = 10
        self._node_ttl = 15
        self._redis_timeout_seconds = 5.0

        self._cpu_threshold = 85.0
        self._mem_threshold = 90.0
        self._current_status: NodeStatus = "STARTING"
        self._started_at = time.time()

        # Warm up psutil so the first sample is not junk.
        psutil.cpu_percent(interval=None)

    @property
    def status(self) -> NodeStatus:
        """Current health status of this node."""
        return self._current_status

    async def start(self) -> None:
        """Start heartbeat and reaper loops."""
        if self._is_running:
            logger.debug("health_agent_already_running", node_id=self._node_id)
            return

        self._is_running = True
        logger.info("health_agent_starting", node_id=self._node_id)

        await self._register_node()

        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(),
            name=f"butler-health-heartbeat:{self._node_id}",
        )
        self._reaper_task = asyncio.create_task(
            self._reaper_loop(),
            name=f"butler-health-reaper:{self._node_id}",
        )

        logger.info("health_agent_started", node_id=self._node_id)

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        if not self._is_running:
            return

        self._is_running = False

        tasks = [task for task in (self._heartbeat_task, self._reaper_task) if task is not None]
        for task in tasks:
            task.cancel()

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                    logger.warning(
                        "health_agent_task_shutdown_error",
                        node_id=self._node_id,
                        error=str(result),
                    )

        self._heartbeat_task = None
        self._reaper_task = None

        try:
            await self._redis_delete(self._node_key)
        except Exception as exc:
            logger.warning(
                "health_agent_shutdown_registry_delete_failed",
                node_id=self._node_id,
                error=str(exc),
            )

        logger.info("health_agent_shutdown", node_id=self._node_id)

    async def _get_resource_status(self) -> NodeStatus:
        """Calculate node health from local resource pressure."""
        try:
            cpu_pct, mem_pct = self._sample_resources()

            if cpu_pct >= 95.0 or mem_pct >= 97.0:
                logger.warning(
                    "node_resource_pressure_unhealthy",
                    node_id=self._node_id,
                    cpu_percent=cpu_pct,
                    memory_percent=mem_pct,
                )
                return "UNHEALTHY"

            if cpu_pct > self._cpu_threshold or mem_pct > self._mem_threshold:
                logger.warning(
                    "node_resource_pressure_degraded",
                    node_id=self._node_id,
                    cpu_percent=cpu_pct,
                    cpu_threshold=self._cpu_threshold,
                    memory_percent=mem_pct,
                    memory_threshold=self._mem_threshold,
                )
                return "DEGRADED"

            return "HEALTHY"
        except Exception as exc:
            logger.error(
                "health_check_resource_failed",
                node_id=self._node_id,
                error=str(exc),
            )
            return "DEGRADED"

    async def _register_node(self) -> None:
        """Register current node metadata in Redis."""
        self._current_status = await self._get_resource_status()
        cpu_pct, mem_pct = self._sample_resources()

        metadata = {
            "node_id": self._node_id,
            "started_at": self._started_at,
            "updated_at": time.time(),
            "version": settings.SERVICE_VERSION,
            "status": self._current_status,
            "cpu_percent": cpu_pct,
            "memory_percent": mem_pct,
            "heartbeat_interval_seconds": self._heartbeat_interval,
            "ttl_seconds": self._node_ttl,
        }

        await self._redis_set_json(self._node_key, metadata, ex=self._node_ttl)

    async def _heartbeat_loop(self) -> None:
        """Periodic heartbeat to keep node registration alive."""
        try:
            while self._is_running:
                try:
                    self._current_status = await self._get_resource_status()
                    cpu_pct, mem_pct = self._sample_resources()

                    metadata = {
                        "node_id": self._node_id,
                        "started_at": self._started_at,
                        "updated_at": time.time(),
                        "version": settings.SERVICE_VERSION,
                        "status": self._current_status,
                        "cpu_percent": cpu_pct,
                        "memory_percent": mem_pct,
                        "heartbeat_interval_seconds": self._heartbeat_interval,
                        "ttl_seconds": self._node_ttl,
                    }

                    async with self._redis.pipeline() as pipe:
                        pipe.set(self._node_key, json.dumps(metadata), ex=self._node_ttl)
                        pipe.expire(self._node_key, self._node_ttl)
                        await self._redis_exec(pipe)

                    logger.debug(
                        "health_heartbeat_sent",
                        node_id=self._node_id,
                        status=self._current_status,
                        cpu_percent=cpu_pct,
                        memory_percent=mem_pct,
                    )

                    self._record_node_metrics(cpu_pct=cpu_pct, mem_pct=mem_pct)
                    await self._update_cluster_health()

                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error(
                        "health_heartbeat_failed",
                        node_id=self._node_id,
                        error=str(exc),
                    )

                await asyncio.sleep(self._heartbeat_interval)
        except asyncio.CancelledError:
            logger.debug("health_heartbeat_loop_cancelled", node_id=self._node_id)
            raise

    async def _reaper_loop(self) -> None:
        """Scans for failed nodes and triggers self-healing."""
        try:
            while self._is_running:
                try:
                    await self._perform_reaping()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error(
                        "health_reaper_failed",
                        node_id=self._node_id,
                        error=str(exc),
                    )

                await asyncio.sleep(self._reaper_interval)
        except asyncio.CancelledError:
            logger.debug("health_reaper_loop_cancelled", node_id=self._node_id)
            raise

    async def _perform_reaping(self) -> None:
        """Identify dead nodes by comparing presence-node keys vs active node registry."""
        presence_node_ids = {
            self._extract_tail_key_segment(key)
            async for key in self._scan_iter("butler:presence:nodes:*")
        }
        active_node_ids = {
            self._extract_tail_key_segment(key) async for key in self._scan_iter("butler:nodes:*")
        }

        if not presence_node_ids:
            return

        dead_node_ids = sorted(
            node_id for node_id in presence_node_ids if node_id not in active_node_ids
        )
        for dead_node_id in dead_node_ids:
            logger.warning("dead_node_detected", node_id=dead_node_id)
            await self._heal_node(dead_node_id)

    async def _heal_node(self, node_id: str) -> None:
        """Cleanup logic for a dead node."""
        presence_key = f"butler:presence:nodes:{node_id}"

        raw_account_ids = await self._redis_smembers(presence_key)
        account_ids = sorted(str(account_id) for account_id in raw_account_ids if account_id)

        if account_ids:
            logger.info(
                "health_agent_healing_node",
                node_id=node_id,
                account_count=len(account_ids),
            )

            async with self._redis.pipeline(transaction=True) as read_pipe:
                for account_id in account_ids:
                    read_pipe.hget(f"presence:{account_id}", "node_id")
                current_node_ids = await self._redis_exec(read_pipe)

            async with self._redis.pipeline(transaction=True) as cleanup_pipe:
                for idx, account_id in enumerate(account_ids):
                    current_node_id = current_node_ids[idx]
                    if current_node_id == node_id:
                        cleanup_pipe.hset(f"presence:{account_id}", "status", "disconnected")

                cleanup_pipe.delete(presence_key)
                await self._redis_exec(cleanup_pipe)
        else:
            await self._redis_delete(presence_key)

        await self._syncer.broadcast_global_event(
            "NODE_OFFLINE",
            {
                "node_id": node_id,
                "timestamp": time.time(),
            },
        )

        logger.info("health_agent_node_healed", node_id=node_id)

    async def _update_cluster_health(self) -> None:
        """Aggregate node statuses and update the global cluster health key."""
        try:
            node_keys = [
                key
                async for key in self._scan_iter("butler:nodes:*")
                if self._is_direct_node_registry_key(key)
            ]

            total = len(node_keys)
            if total == 0:
                await self._redis_set_text(self._cluster_health_key, "NO_NODES", ex=30)
                self._set_cluster_health_metric("NO_NODES")
                return

            async with self._redis.pipeline(transaction=False) as pipe:
                for key in node_keys:
                    pipe.get(key)
                raw_nodes = await self._redis_exec(pipe)

            unhealthy = 0
            degraded = 0

            for raw in raw_nodes:
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except Exception:
                    logger.warning("cluster_health_invalid_node_payload", payload=str(raw)[:200])
                    continue

                status = data.get("status")
                if status == "UNHEALTHY":
                    unhealthy += 1
                elif status == "DEGRADED":
                    degraded += 1

            if unhealthy / max(total, 1) > 0.5:
                cluster_health = "CRITICAL"
            elif unhealthy > 0 or degraded > 0:
                cluster_health = "DEGRADED"
            else:
                cluster_health = "HEALTHY"

            await self._redis_set_text(self._cluster_health_key, cluster_health, ex=30)
            self._set_cluster_health_metric(cluster_health)

            logger.debug(
                "cluster_health_updated",
                total_nodes=total,
                unhealthy_nodes=unhealthy,
                degraded_nodes=degraded,
                cluster_health=cluster_health,
            )
        except Exception as exc:
            logger.error("cluster_health_update_failed", error=str(exc))

    def _record_node_metrics(self, *, cpu_pct: float, mem_pct: float) -> None:
        try:
            self._metrics.record_node_resource(
                node_id=self._node_id,
                cpu=cpu_pct,
                mem=mem_pct,
                status=self._current_status,
            )
        except Exception as exc:
            logger.debug(
                "health_agent_metric_record_failed",
                node_id=self._node_id,
                error=str(exc),
            )

    def _set_cluster_health_metric(self, cluster_health: str) -> None:
        health_value = {
            "CRITICAL": 0,
            "DEGRADED": 1,
            "HEALTHY": 2,
            "NO_NODES": -1,
        }.get(cluster_health, -2)

        try:
            self._metrics.GAUGE_CLUSTER_HEALTH.set(health_value)
        except Exception as exc:
            logger.debug(
                "cluster_health_metric_failed",
                cluster_health=cluster_health,
                error=str(exc),
            )

    def _sample_resources(self) -> tuple[float, float]:
        cpu_pct = float(psutil.cpu_percent(interval=None))
        mem_pct = float(psutil.virtual_memory().percent)
        return cpu_pct, mem_pct

    async def _scan_iter(self, pattern: str) -> AsyncIterator[str]:
        cursor = 0
        while True:
            cursor, keys = await asyncio.wait_for(
                self._redis.scan(cursor=cursor, match=pattern, count=200),
                timeout=self._redis_timeout_seconds,
            )
            for key in keys:
                yield str(key)
            if cursor == 0:
                break

    def _extract_tail_key_segment(self, key: str) -> str:
        return key.rsplit(":", 1)[-1]

    def _is_direct_node_registry_key(self, key: str) -> bool:
        # Matches butler:nodes:<node_id> only
        return key.startswith("butler:nodes:") and key.count(":") == 2

    async def _redis_set_json(
        self, key: str, payload: dict[str, Any], *, ex: int | None = None
    ) -> None:
        await asyncio.wait_for(
            self._redis.set(key, json.dumps(payload), ex=ex),
            timeout=self._redis_timeout_seconds,
        )

    async def _redis_set_text(self, key: str, value: str, *, ex: int | None = None) -> None:
        await asyncio.wait_for(
            self._redis.set(key, value, ex=ex),
            timeout=self._redis_timeout_seconds,
        )

    async def _redis_delete(self, key: str) -> int:
        return int(
            await asyncio.wait_for(
                self._redis.delete(key),
                timeout=self._redis_timeout_seconds,
            )
        )

    async def _redis_smembers(self, key: str) -> set[Any]:
        result = await asyncio.wait_for(
            self._redis.smembers(key),
            timeout=self._redis_timeout_seconds,
        )
        return set(result)

    async def _redis_exec(self, pipe: Any) -> Any:
        return await asyncio.wait_for(
            pipe.execute(),
            timeout=self._redis_timeout_seconds,
        )
