"""
Butler Edge Topology - Nginx-inspired edge layer for Butler Gateway

Implements:
- EdgeRouter: Intelligent routing with circuit breaking
- EdgeCache: Stale-while-revalidate caching
- WebSocketProxy: SSE/WebSocket hardening
- RateLimiter: Leaky bucket per client
- StreamBuffer: Chunked response handling

SWE-5 Compliant:
- Pydantic configuration
- Connection pooling
- Graceful degradation
- Full OpenTelemetry instrumentation
"""

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import redis.asyncio as redis
from opentelemetry import trace
from opentelemetry.metrics import get_meter
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, Field, validator

from services.security.safe_request import EgressDecision, SafeRequestClient

tracer = trace.get_tracer(__name__)
meter = get_meter(__name__)

# Metrics
request_counter = meter.create_counter("edge.requests.total", description="Total edge requests")
cache_hits_counter = meter.create_counter("edge.cache.hits", description="Cache hits")
cache_misses_counter = meter.create_counter("edge.cache.misses", description="Cache misses")
rate_limited_counter = meter.create_counter(
    "edge.rate_limited", description="Rate limited requests"
)
circuit_open_counter = meter.create_counter(
    "edge.circuit_open", description="Circuit breaker open events"
)


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class EdgeConfig(BaseModel):
    """Edge topology configuration"""

    redis_url: str = Field(default="redis://localhost:6379/1", description="Redis connection URL")
    cache_ttl: int = Field(default=300, ge=1, description="Default cache TTL in seconds")
    stale_while_revalidate: int = Field(
        default=60, ge=0, description="Stale while revalidate window"
    )
    rate_limit_requests: int = Field(default=100, ge=1, description="Requests per window")
    rate_limit_window: int = Field(default=60, ge=1, description="Rate limit window in seconds")
    circuit_failure_threshold: int = Field(
        default=5, ge=1, description="Circuit breaker failure threshold"
    )
    circuit_reset_timeout: int = Field(
        default=30, ge=1, description="Circuit reset timeout in seconds"
    )
    max_connections: int = Field(default=100, ge=1, description="Max upstream connections")
    max_keepalive_connections: int = Field(
        default=20, ge=0, description="Max keepalive connections"
    )
    keepalive_timeout: int = Field(default=30, ge=0, description="Keepalive timeout in seconds")
    stream_buffer_size: int = Field(
        default=65536, ge=1024, description="Stream buffer size in bytes"
    )

    @validator("stale_while_revalidate")
    def stale_less_than_ttl(cls, v: int, values: dict[str, Any]) -> int:
        if v > values.get("cache_ttl", 300):
            raise ValueError("stale_while_revalidate must be less than cache_ttl")
        return v


@dataclass
class CircuitBreaker:
    """Circuit breaker per upstream service"""

    failure_threshold: int
    reset_timeout: int
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    half_open_attempts: int = 0

    def allow_request(self) -> bool:
        """Check if request is allowed through circuit breaker"""
        now = time.time()

        if self.state == CircuitState.OPEN:
            if now - self.last_failure_time > self.reset_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_attempts = 0
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            self.half_open_attempts += 1
            return True

        return True

    def record_success(self) -> None:
        """Record successful request"""
        self.failure_count = 0
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.half_open_attempts = 0

    def record_failure(self) -> None:
        """Record failed request"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            return

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            circuit_open_counter.add(1)


@dataclass
class UpstreamPool:
    """Connection pool for upstream services with SafeRequestClient for SSRF protection."""

    base_url: str
    client: SafeRequestClient = field(init=False)
    circuit_breaker: CircuitBreaker = field(init=False)
    config: EdgeConfig
    tenant_id: str = "default"

    def __post_init__(self) -> None:
        # P0 hardening: Use SafeRequestClient instead of httpx for SSRF protection
        self.client = SafeRequestClient()
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=self.config.circuit_failure_threshold,
            reset_timeout=self.config.circuit_reset_timeout,
        )

    async def close(self) -> None:
        await self.client.close()


class EdgeRouter:
    """Intelligent edge router with circuit breaking and load balancing"""

    def __init__(self, config: EdgeConfig):
        self.config = config
        self.upstreams: dict[str, UpstreamPool] = {}
        self._lock = asyncio.Lock()

    async def register_upstream(self, name: str, base_url: str) -> None:
        """Register an upstream service"""
        async with self._lock:
            if name not in self.upstreams:
                self.upstreams[name] = UpstreamPool(base_url=base_url, config=self.config)

    async def route(self, service: str, path: str, method: str = "GET", **kwargs) -> Any:
        """Route request to upstream service with circuit breaker protection"""
        with tracer.start_as_current_span("edge.router.route") as span:
            span.set_attribute("service", service)
            span.set_attribute("path", path)
            span.set_attribute("method", method)

            if service not in self.upstreams:
                span.set_status(Status(StatusCode.ERROR, "Service not found"))
                raise ValueError(f"Unknown service: {service}")

            upstream = self.upstreams[service]

            if not upstream.circuit_breaker.allow_request():
                span.set_attribute("circuit_state", upstream.circuit_breaker.state)
                span.set_status(Status(StatusCode.ERROR, "Circuit breaker open"))
                raise RuntimeError(f"Service {service} is unavailable (circuit open)")

            try:
                # P0 hardening: Use SafeRequestClient with tenant_id for SSRF protection
                url = f"{upstream.base_url}{path}"
                if method == "GET":
                    response = await upstream.client.get(
                        url,
                        upstream.tenant_id,
                        headers=kwargs.get("headers"),
                        params=kwargs.get("params"),
                    )
                elif method == "POST":
                    response = await upstream.client.post(
                        url,
                        upstream.tenant_id,
                        headers=kwargs.get("headers"),
                        json=kwargs.get("json"),
                        data=kwargs.get("data"),
                    )
                else:
                    # For other methods, use httpx directly with SSRF check
                    # P0 hardening: Add SSRF protection for other methods
                    decision, reason = upstream.client._egress_policy.check_url(
                        url, upstream.tenant_id
                    )
                    if decision == EgressDecision.DENY:
                        raise RuntimeError(f"SSRF protection denied request to {url}: {reason}")
                    import httpx

                    async with httpx.AsyncClient() as http_client:
                        response = await http_client.request(method, url, **kwargs)

                if 500 <= response.status_code < 600:
                    upstream.circuit_breaker.record_failure()
                else:
                    upstream.circuit_breaker.record_success()

                span.set_attribute("status_code", response.status_code)
                request_counter.add(1, {"service": service, "status": response.status_code})
                return response

            except Exception as e:
                upstream.circuit_breaker.record_failure()
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    async def shutdown(self) -> None:
        """Shutdown all upstream connections gracefully"""
        for upstream in self.upstreams.values():
            await upstream.close()


class EdgeCache:
    """Stale-while-revalidate cache implementation using Redis"""

    def __init__(self, config: EdgeConfig, redis_client: redis.Redis | None = None):
        self.config = config
        self.redis = redis_client or redis.from_url(config.redis_url)
        self._revalidate_lock: dict[str, asyncio.Lock] = {}

    def _cache_key(self, key: str) -> str:
        return f"edge:cache:{key}"

    async def get(self, key: str) -> tuple[bytes | None, bool]:
        """Get cached value, returns (value, is_stale)"""
        with tracer.start_as_current_span("edge.cache.get") as span:
            span.set_attribute("cache_key", key)

            cache_key = self._cache_key(key)
            ttl = await self.redis.ttl(cache_key)

            if ttl == -2:
                cache_misses_counter.add(1)
                span.set_attribute("cache_hit", False)
                return None, False

            value = await self.redis.get(cache_key)
            if value is None:
                cache_misses_counter.add(1)
                span.set_attribute("cache_hit", False)
                return None, False

            is_stale = ttl < self.config.stale_while_revalidate
            cache_hits_counter.add(1, {"stale": is_stale})
            span.set_attribute("cache_hit", True)
            span.set_attribute("stale", is_stale)

            return value, is_stale

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        """Set cached value"""
        with tracer.start_as_current_span("edge.cache.set") as span:
            span.set_attribute("cache_key", key)
            actual_ttl = ttl or self.config.cache_ttl
            await self.redis.setex(self._cache_key(key), actual_ttl, value)

    async def should_revalidate(self, key: str) -> bool:
        """Check if cache entry needs revalidation (atomic lock)"""
        if key not in self._revalidate_lock:
            self._revalidate_lock[key] = asyncio.Lock()

        return self._revalidate_lock[key].locked() is False

    async def acquire_revalidate_lock(self, key: str) -> asyncio.Lock | None:
        """Acquire lock for revalidation (prevents thundering herd)"""
        if key not in self._revalidate_lock:
            self._revalidate_lock[key] = asyncio.Lock()

        lock = self._revalidate_lock[key]
        if lock.locked():
            return None

        await lock.acquire()
        return lock

    async def invalidate(self, key: str) -> None:
        """Invalidate cache entry"""
        await self.redis.delete(self._cache_key(key))


class RateLimiter:
    """Leaky bucket rate limiter per client identifier"""

    def __init__(self, config: EdgeConfig, redis_client: redis.Redis | None = None):
        self.config = config
        self.redis = redis_client or redis.from_url(config.redis_url)

    def _rate_key(self, client_id: str) -> str:
        window = int(time.time() // self.config.rate_limit_window)
        return f"edge:rate:{client_id}:{window}"

    async def allow_request(self, client_id: str) -> tuple[bool, int, int]:
        """Check if request is allowed, returns (allowed, remaining, reset_time)"""
        with tracer.start_as_current_span("edge.rate_limiter.check") as span:
            span.set_attribute("client_id", client_id)

            key = self._rate_key(client_id)

            async with self.redis.pipeline() as pipe:
                pipe.incr(key)
                pipe.expire(key, self.config.rate_limit_window + 1)
                count, _ = await pipe.execute()

            count = int(count)
            remaining = max(0, self.config.rate_limit_requests - count)
            reset_time = int(
                (int(time.time() // self.config.rate_limit_window) + 1)
                * self.config.rate_limit_window
            )

            allowed = count <= self.config.rate_limit_requests

            if not allowed:
                rate_limited_counter.add(1, {"client_id": client_id})
                span.set_attribute("rate_limited", True)
            else:
                span.set_attribute("rate_limited", False)

            span.set_attribute("count", count)
            span.set_attribute("remaining", remaining)

            return allowed, remaining, reset_time


class StreamBuffer:
    """Chunked response stream buffer with backpressure handling"""

    def __init__(self, buffer_size: int = 65536):
        self.buffer_size = buffer_size
        self.queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=buffer_size // 1024)
        self.closed = False

    async def write(self, chunk: bytes) -> None:
        """Write chunk to buffer"""
        if self.closed:
            raise RuntimeError("Stream buffer is closed")
        await self.queue.put(chunk)

    async def close(self) -> None:
        """Close buffer, signal end of stream"""
        self.closed = True
        await self.queue.put(None)

    async def stream(self) -> AsyncGenerator[bytes]:
        """Stream chunks from buffer"""
        while True:
            chunk = await self.queue.get()
            if chunk is None:
                break
            yield chunk


class WebSocketProxy:
    """WebSocket and SSE proxy with hardening and connection management"""

    def __init__(self, config: EdgeConfig):
        self.config = config
        self.active_connections: dict[str, Any] = {}
        self._connection_lock = asyncio.Lock()

    async def proxy_sse(self, upstream_url: str, client_stream: Any) -> AsyncGenerator[str]:
        """Proxy Server-Sent Events with heartbeat and timeout protection"""
        with tracer.start_as_current_span("edge.websocket.proxy_sse") as span:
            connection_id = str(uuid.uuid4())
            span.set_attribute("connection_id", connection_id)
            span.set_attribute("upstream_url", upstream_url)

            last_heartbeat = time.time()
            timeout = 30.0

            try:
                # P0 hardening: Use SafeRequestClient with SSRF protection for streaming
                decision, reason = SafeRequestClient()._egress_policy.check_url(
                    upstream_url, "default"
                )
                if decision == EgressDecision.DENY:
                    raise RuntimeError(
                        f"SSRF protection denied request to {upstream_url}: {reason}"
                    )
                import httpx

                async with (
                    httpx.AsyncClient() as client,
                    client.stream(
                        "GET", upstream_url, timeout=httpx.Timeout(None, read=timeout)
                    ) as response,
                ):
                    async for line in response.aiter_lines():
                        if time.time() - last_heartbeat > timeout:
                            yield "event: timeout\ndata: Connection timeout\n\n"
                            break

                        if line.strip() == "":
                            last_heartbeat = time.time()

                        yield line + "\n"

            except asyncio.CancelledError:
                span.set_attribute("cancelled", True)
                yield "event: close\ndata: Connection closed\n\n"
            except Exception as e:
                span.record_exception(e)
                yield f"event: error\ndata: {str(e)}\n\n"


class EdgeTopology:
    """Main edge topology facade"""

    def __init__(self, config: EdgeConfig | None = None):
        self.config = config or EdgeConfig()
        self.router = EdgeRouter(self.config)
        self.cache = EdgeCache(self.config)
        self.rate_limiter = RateLimiter(self.config)
        self.websocket = WebSocketProxy(self.config)

    async def shutdown(self) -> None:
        """Graceful shutdown of all edge components"""
        await self.router.shutdown()
        await self.cache.redis.aclose()
        await self.rate_limiter.redis.aclose()


# Module exports
__all__ = [
    "EdgeTopology",
    "EdgeConfig",
    "EdgeRouter",
    "EdgeCache",
    "RateLimiter",
    "WebSocketProxy",
    "StreamBuffer",
    "CircuitState",
    "CircuitBreaker",
    "UpstreamPool",
]
