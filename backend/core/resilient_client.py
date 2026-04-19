from __future__ import annotations

import time
import asyncio
import uuid
from typing import Any, Dict, Optional, Callable, Awaitable

import httpx
import structlog
from pydantic import BaseModel

from core.retry_budget import RetryBudget
from core.circuit_breaker import ButlerCircuitBreaker, get_circuit_breaker_registry

logger = structlog.get_logger(__name__)

class InternalRequest(BaseModel):
    service: str
    method: str
    path: str
    data: Optional[Dict[str, Any]] = None
    headers: Dict[str, str] = {}
    idempotency_key: Optional[str] = None

class ResilientClient:
    """
    High-performance resilient internal client (v3.0).
    
    Principles:
    - Never overload a failing peer (Retry Budget).
    - Fail fast (Circuit Breaker).
    - Propagate context (Trace IDs, Idempotency).
    """

    def __init__(
        self,
        source_service: str,
        base_url: str,
        timeout: float = 5.0,
        max_retries: int = 3
    ):
        self.source_service = source_service
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        
        # Shared Resilience State
        self._budget = RetryBudget()
        self._breaker_registry = get_circuit_breaker_registry()
        
        # Connection Pool
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            limits=httpx.Limits(max_keepalive_connections=50, max_connections=100)
        )

    async def call(self, request: InternalRequest) -> httpx.Response:
        """Execute a resilient call with budget-aware retries."""
        
        breaker = self._breaker_registry.register(request.service)
        last_exception = None
        
        # Automatic Header Injection
        request.headers.update({
            "X-Butler-Source": self.source_service,
            "X-Butler-Request-ID": str(uuid.uuid4()),
        })
        if request.idempotency_key:
            request.headers["X-Idempotency-Key"] = request.idempotency_key

        for attempt in range(self.max_retries + 1):
            is_retry = attempt > 0
            
            # 1. Check Retry Budget if this is a retry
            if is_retry and not self._budget.withdraw():
                logger.warning("retry_budget_exhausted", 
                               service=request.service, 
                               path=request.path)
                break

            # 2. Guard with Circuit Breaker
            try:
                # We use the raw allow_request/record pattern for finer control
                if not breaker.allow_request():
                    logger.error("circuit_breaker_open", service=request.service)
                    raise ConnectionError(f"Circuit {request.service} is open")

                response = await self._client.request(
                    method=request.method,
                    url=request.path,
                    json=request.data,
                    headers=request.headers
                )
                
                # Success Recording
                if response.status_code < 500:
                    breaker.record_success()
                    if not is_retry:
                        self._budget.deposit()
                    return response
                
                # Server Error -> Record Failure
                breaker.record_failure()
                response.raise_for_status()

            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                last_exception = e
                breaker.record_failure()
                
                # Only retry on connection errors or 5xx server errors
                should_retry = isinstance(e, httpx.ConnectError) or \
                               (isinstance(e, httpx.HTTPStatusError) and e.response.status_code >= 500)
                
                if not should_retry:
                    raise e
                
                # Exponential Backoff
                if attempt < self.max_retries:
                    wait_time = (2 ** attempt) * 0.1
                    logger.debug("retrying_call", 
                                 service=request.service, 
                                 path=request.path, 
                                 attempt=attempt + 1,
                                 wait=wait_time)
                    await asyncio.sleep(wait_time)
        
        if last_exception:
            raise last_exception
        raise ConnectionError(f"Failed to call {request.service} after {self.max_retries} attempts")

    async def close(self):
        """Clean up the connection pool."""
        await self._client.aclose()
