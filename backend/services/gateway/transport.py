"""Gateway Transport Layer.

Implements Nginx-inspired edge hardening patterns for WebSocket and SSE connections.
This is the entry point for the Hermes Integration Layer, enforcing strict boundaries
before traffic reaches the core Orchestrator.

Key Features:
- Layer 7 Leaky Bucket Rate Limiting
- Connection Throttling and Backpressure
- Strict Ping/Pong Timeouts
- JWT Bearer Authentication integration
"""

import asyncio
import time

from fastapi import WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from core.observability import get_metrics
from core.tracing import tracer
from domain.auth.contracts import AccountContext
from services.gateway.auth_middleware import JWTAuthMiddleware


class LeakyBucketRateLimiter:
    """Nginx-inspired leaky bucket rate limiter."""

    def __init__(self, redis: Redis, rate: float = 10.0, capacity: int = 50):
        """
        Args:
            redis: Redis connection.
            rate: Tokens added per second.
            capacity: Maximum burst capacity.
        """
        self.redis = redis
        self.rate = rate
        self.capacity = capacity

    async def acquire(self, key: str) -> bool:
        """Attempt to acquire a token from the bucket."""
        with tracer.start_as_current_span("rate_limit.acquire"):
            now = time.time()
            lua_script = """
            local key = KEYS[1]
            local rate = tonumber(ARGV[1])
            local capacity = tonumber(ARGV[2])
            local now = tonumber(ARGV[3])

            local current_level = tonumber(redis.call('HGET', key, 'level') or '0')
            local last_update = tonumber(redis.call('HGET', key, 'last_update') or now)

            -- Leak tokens based on elapsed time
            local elapsed = math.max(0, now - last_update)
            local leaked = elapsed * rate
            current_level = math.max(0, current_level - leaked)

            if current_level + 1 <= capacity then
                current_level = current_level + 1
                redis.call('HSET', key, 'level', current_level, 'last_update', now)
                redis.call('EXPIRE', key, 60)
                return 1
            else:
                return 0
            """

            result = await self.redis.eval(lua_script, 1, key, self.rate, self.capacity, now)
            return bool(result)


class ButlerTransportContext:
    """Wrapper holding connection state and isolated context."""

    def __init__(self, account: AccountContext, websocket: WebSocket):
        self.account = account
        self.websocket = websocket
        self.connected_at = time.time()
        self.last_active = time.time()


class HermesTransportEdge:
    """Nginx-inspired WebSocket transport edge."""

    def __init__(self, auth_middleware: JWTAuthMiddleware, redis: Redis):
        self.auth_middleware = auth_middleware
        self.rate_limiter = LeakyBucketRateLimiter(redis, rate=5.0, capacity=20)
        self.active_transports: dict[str, ButlerTransportContext] = {}

    async def connect(self, websocket: WebSocket, token: str) -> ButlerTransportContext | None:
        """Authenticate and establish hardened connection."""
        await websocket.accept()

        try:
            # Enforce authentication explicitly at the transport boundary
            account_ctx = await self.auth_middleware.authenticate(f"Bearer {token}")
        except Exception:
            get_metrics().inc_counter("gateway.transport.rejected", tags={"reason": "auth_failure"})
            await websocket.close(code=1008, reason="Authentication Failed")
            return None

        # Check rate limits for the tenant/account
        rl_key = f"ratelimit:ws:{account_ctx.sub}"
        if not await self.rate_limiter.acquire(rl_key):
            get_metrics().inc_counter("gateway.transport.rejected", tags={"reason": "rate_limit"})
            await websocket.close(code=1008, reason="Rate Limit Exceeded")
            return None

        transport_ctx = ButlerTransportContext(account=account_ctx, websocket=websocket)
        self.active_transports[account_ctx.session_id] = transport_ctx

        get_metrics().inc_counter("gateway.transport.connected", tags={"tenant": account_ctx.sub})
        return transport_ctx

    async def disconnect(self, session_id: str) -> None:
        """Cleanly remove the transport context."""
        if session_id in self.active_transports:
            del self.active_transports[session_id]
            get_metrics().inc_counter("gateway.transport.disconnected")

    async def run_ping_pong_loop(
        self, transport_ctx: ButlerTransportContext, timeout_s: float = 30.0
    ):
        """Hardened ping/pong lifecycle to prevent zombie agent holding."""
        websocket = transport_ctx.websocket
        while True:
            try:
                await asyncio.sleep(timeout_s / 2)
                # Enforce stage timeout boundary using asyncio.timeout
                async with asyncio.timeout(timeout_s):
                    # We expect custom heartbeat protocol from client or standard WS ping
                    await websocket.send_json({"type": "ping", "timestamp": time.time()})
                    # Wait for pong or data
                    await websocket.receive_text()
                    transport_ctx.last_active = time.time()
            except TimeoutError:
                get_metrics().inc_counter(
                    "gateway.transport.timeout", tags={"session": transport_ctx.account.session_id}
                )
                await websocket.close(code=1011, reason="Ping Timeout")
                break
            except WebSocketDisconnect:
                break
            except Exception:
                break

        await self.disconnect(transport_ctx.account.session_id)
