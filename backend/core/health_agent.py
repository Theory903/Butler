import asyncio
import json
import time
from typing import Any, Literal

import psutil
import structlog
from redis.asyncio import Redis
from core.observability import ButlerMetrics, get_metrics

from infrastructure.config import settings
from core.state_sync import GlobalStateSyncer

logger = structlog.get_logger(__name__)

NodeStatus = Literal["STARTING", "HEALTHY", "DEGRADED", "UNHEALTHY"]

class ButlerHealthAgent:
    """Autonomous agent for cluster health and self-healing."""

    def __init__(
        self,
        redis: Redis,
        syncer: GlobalStateSyncer,
        node_id: str = settings.BUTLER_NODE_ID,
        metrics: ButlerMetrics | None = None
    ) -> None:
        self._redis = redis
        self._syncer = syncer
        self._node_id = node_id
        self._metrics = metrics or get_metrics()
        self._is_running = False
        self._heartbeat_task: asyncio.Task | None = None
        self._reaper_task: asyncio.Task | None = None
        
        self._node_key = f"butler:nodes:{self._node_id}"
        self._heartbeat_interval = 5  # seconds
        self._node_ttl = 15  # seconds
        
        # Load thresholds from settings or defaults
        self._cpu_threshold = 85.0
        self._mem_threshold = 90.0
        self._current_status: NodeStatus = "STARTING"
        
        # Oracle-Grade: Initialize psutil to discard the first 0.0 value
        psutil.cpu_percent(interval=None)

    @property
    def status(self) -> NodeStatus:
        """Current health status of this node."""
        return self._current_status

    async def start(self):
        """Start heartbeat and reaper loops."""
        if self._is_running:
            return
        
        self._is_running = True
        logger.info("health_agent_starting", node_id=self._node_id)
        
        # 1. Register self
        await self._register_node()
        
        # 2. Spawn loops
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._reaper_task = asyncio.create_task(self._reaper_loop())

    async def shutdown(self):
        """Graceful shutdown."""
        self._is_running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._reaper_task:
            self._reaper_task.cancel()
        
        # Unregister self
        await self._redis.delete(self._node_key)
        logger.info("health_agent_shutdown", node_id=self._node_id)

    async def _get_resource_status(self) -> NodeStatus:
        """Calculate node health based on local resource pressure."""
        try:
            cpu_pct = psutil.cpu_percent(interval=None)
            mem_pct = psutil.virtual_memory().percent
            
            if cpu_pct > self._cpu_threshold:
                logger.warning("node_resource_pressure_cpu", cpu=cpu_pct, threshold=self._cpu_threshold)
                return "DEGRADED"
            
            if mem_pct > self._mem_threshold:
                logger.warning("node_resource_pressure_mem", mem=mem_pct, threshold=self._mem_threshold)
                return "DEGRADED"
            
            return "HEALTHY"
        except Exception as e:
            logger.error("health_check_resource_failed", error=str(e))
            return "DEGRADED"

    async def _register_node(self):
        """Register current node metadata in Redis."""
        self._current_status = await self._get_resource_status()
        metadata = {
            "node_id": self._node_id,
            "started_at": time.time(),
            "version": settings.SERVICE_VERSION,
            "status": self._current_status,
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_percent": psutil.virtual_memory().percent
        }
        await self._redis.set(self._node_key, json.dumps(metadata), ex=self._node_ttl)

    async def _heartbeat_loop(self):
        """Periodic heartbeat to keep node registration alive."""
        while self._is_running:
            try:
                # Update status and metadata on every heartbeat
                self._current_status = await self._get_resource_status()
                metadata = {
                    "node_id": self._node_id,
                    "updated_at": time.time(),
                    "status": self._current_status,
                    "cpu_percent": psutil.cpu_percent(interval=None),
                    "memory_percent": psutil.virtual_memory().percent,
                }
                
                async with self._redis.pipeline() as pipe:
                    pipe.set(self._node_key, json.dumps(metadata), ex=self._node_ttl)
                    # Also refresh the expire just in case set failed
                    pipe.expire(self._node_key, self._node_ttl)
                    await pipe.execute()
                
                logger.debug("health_heartbeat_sent", node_id=self._node_id, status=self._current_status)
                
                # Update Prometheus metrics
                self._metrics.record_node_resource(
                    node_id=self._node_id,
                    cpu=metadata["cpu_percent"],
                    mem=metadata["memory_percent"],
                    status=self._current_status
                )
                
                # After heartbeat, also compute cluster aggregate (can be done by any node)
                await self._update_cluster_health()
            except Exception as e:
                logger.error("health_heartbeat_failed", error=str(e))
            
            await asyncio.sleep(self._heartbeat_interval)

    async def _reaper_loop(self):
        """Scans for failed nodes and triggers self-healing."""
        while self._is_running:
            try:
                await self._perform_reaping()
            except Exception as e:
                logger.error("health_reaper_failed", error=str(e))
            
            await asyncio.sleep(10)  # Reaper runs less frequently

    async def _perform_reaping(self):
        """Identify dead nodes by checking all known presence nodes vs active node registry."""
        # 1. Get all nodes that HAVE presence data
        presence_nodes = await self._redis.keys("butler:presence:nodes:*")
        presence_node_ids = [k.split(":")[-1] for k in presence_nodes] if presence_nodes else []
        
        # 2. Get all ACTIVE nodes from registry
        active_nodes = await self._redis.keys("butler:nodes:*")
        active_node_ids = {k.split(":")[-1] for k in active_nodes} if active_nodes else set()
        
        for p_node_id in presence_node_ids:
            if p_node_id not in active_node_ids:
                # Dead node detected!
                logger.warn("dead_node_detected", node_id=p_node_id)
                await self._heal_node(p_node_id)

    async def _heal_node(self, node_id: str):
        """Cleanup logic for a dead node."""
        presence_key = f"butler:presence:nodes:{node_id}"
        
        # 1. Get all account IDs associated with the dead node
        account_ids = await self._redis.smembers(presence_key)
        
        if account_ids:
            # redis-py async with decode_responses=True returns strings already
            logger.info("health_agent_healing_node", node_id=node_id, account_count=len(account_ids))
            
            # 2. Mark them as disconnected (if they haven't reconnected elsewhere)
            async with self._redis.pipeline(transaction=True) as pipe:
                for account_id in account_ids:
                    pipe.hget(f"presence:{account_id}", "node_id")
                
                current_node_ids = await pipe.execute()
                
                async with self._redis.pipeline(transaction=True) as pipe_cleanup:
                    for i, account_id in enumerate(account_ids):
                        if current_node_ids[i] == node_id:
                            pipe_cleanup.hset(f"presence:{account_id}", "status", "disconnected")
                    
                    pipe_cleanup.delete(presence_key)
                    await pipe_cleanup.execute()

        # 3. Broadcast failure
        await self._syncer.broadcast_global_event(
            "NODE_OFFLINE",
            {"node_id": node_id, "timestamp": time.time()}
        )
        logger.info("health_agent_node_healed", node_id=node_id)

    async def _update_cluster_health(self):
        """Aggregate all node statuses and update the global cluster health key."""
        try:
            node_keys = await self._redis.keys("butler:nodes:*")
            # Only root keys
            registry_keys = [k for k in node_keys if k.count(":") == 2]
            
            total = len(registry_keys)
            if total == 0:
                await self._redis.set("butler:cluster:health", "NO_NODES", ex=30)
                return

            unhealthy = 0
            degraded = 0
            for key in registry_keys:
                raw = await self._redis.get(key)
                if raw:
                    data = json.loads(raw)
                    status = data.get("status")
                    if status == "UNHEALTHY":
                        unhealthy += 1
                    elif status == "DEGRADED":
                        degraded += 1

            if unhealthy / max(total, 1) > 0.5:
                cluster_health = "CRITICAL"
            elif (unhealthy + degraded) > 0:
                cluster_health = "DEGRADED"
            else:
                cluster_health = "HEALTHY"

            await self._redis.set("butler:cluster:health", cluster_health, ex=30)
            
            # Record cluster health as a metric (numerical)
            health_value = {"CRITICAL": 0, "DEGRADED": 1, "HEALTHY": 2, "NO_NODES": -1}.get(cluster_health, -2)
            self._metrics.GAUGE_CLUSTER_HEALTH.set(health_value)
            
        except Exception as e:
            logger.error("cluster_health_update_failed", error=str(e))
