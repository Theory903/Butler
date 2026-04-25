from __future__ import annotations

import asyncio
import random
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field

from core.circuit_breaker import CircuitOpenError, get_circuit_breaker_registry
from core.retry_budget import RetryBudget

logger = structlog.get_logger(__name__)


class InternalRequest(BaseModel):
    """Canonical internal Butler service-to-service request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    service: str
    method: str
    path: str
    data: dict[str, Any] | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    params: dict[str, str | int | float | bool] = Field(default_factory=dict)
    idempotency_key: str | None = None
    timeout: float | None = None
    retryable: bool | None = None


@dataclass(slots=True, frozen=True)
class ResilientClientConfig:
    timeout: float = 5.0
    max_retries: int = 3
    max_keepalive_connections: int = 50
    max_connections: int = 100
    base_backoff_seconds: float = 0.1
    max_backoff_seconds: float = 2.0
    jitter_ratio: float = 0.2


class ResilientClientError(Exception):
    """Base exception for resilient client failures."""


class RetryBudgetExhaustedError(ResilientClientError):
    """Raised when retries are blocked by retry budget."""


class ResilientClient:
    """
    Production-grade resilient internal client.

    Guarantees:
    - bounded retries
    - retry-budget aware
    - breaker-aware
    - idempotency-aware retry policy
    - immutable input handling
    """

    RETRYABLE_STATUS_CODES = {500, 502, 503, 504}
    IDEMPOTENT_METHODS = {"GET", "HEAD", "PUT", "DELETE", "OPTIONS"}

    def __init__(
        self,
        source_service: str,
        base_url: str,
        *,
        config: ResilientClientConfig | None = None,
        retry_budget: RetryBudget | None = None,
    ) -> None:
        self.source_service = source_service.strip()
        self.base_url = base_url.rstrip("/")
        self.config = config or ResilientClientConfig()
        self._budget = retry_budget or RetryBudget()
        self._breaker_registry = get_circuit_breaker_registry()

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.config.timeout,
            limits=httpx.Limits(
                max_keepalive_connections=self.config.max_keepalive_connections,
                max_connections=self.config.max_connections,
            ),
        )

    async def call(self, request: InternalRequest) -> httpx.Response:
        """Execute a resilient internal HTTP call."""
        breaker = self._breaker_registry.register(request.service)
        method = request.method.upper()
        last_exception: Exception | None = None

        headers = self._build_headers(request.headers, request.idempotency_key)
        request_timeout = request.timeout or self.config.timeout
        retry_allowed = self._is_retry_allowed(request, method)

        for attempt in range(self.config.max_retries + 1):
            is_retry = attempt > 0

            if is_retry:
                if not retry_allowed:
                    break
                if not self._budget.withdraw():
                    logger.warning(
                        "resilient_client_retry_budget_exhausted",
                        service=request.service,
                        method=method,
                        path=request.path,
                        attempt=attempt,
                    )
                    raise RetryBudgetExhaustedError(
                        f"Retry budget exhausted for {request.service} {method} {request.path}"
                    )

            if not breaker.allow_request():
                stats = breaker.stats()
                logger.error(
                    "resilient_client_circuit_open",
                    service=request.service,
                    method=method,
                    path=request.path,
                    attempt=attempt,
                    recovery_remaining_s=stats.recovery_remaining_s,
                )
                raise CircuitOpenError(breaker.name, (stats.opened_at or 0) + stats.recovery_s)

            try:
                response = await self._client.request(
                    method=method,
                    url=request.path,
                    json=request.data,
                    params=request.params,
                    headers=headers,
                    timeout=request_timeout,
                )

                if response.status_code < 500:
                    breaker.record_success()
                    if not is_retry:
                        self._budget.deposit()

                    logger.info(
                        "resilient_client_call_succeeded",
                        service=request.service,
                        method=method,
                        path=request.path,
                        status_code=response.status_code,
                        attempt=attempt,
                    )
                    return response

                if response.status_code not in self.RETRYABLE_STATUS_CODES:
                    breaker.record_success()
                    logger.warning(
                        "resilient_client_non_retryable_http_error",
                        service=request.service,
                        method=method,
                        path=request.path,
                        status_code=response.status_code,
                        attempt=attempt,
                    )
                    response.raise_for_status()

                last_exception = httpx.HTTPStatusError(
                    message=f"Retryable upstream error: {response.status_code}",
                    request=response.request,
                    response=response,
                )
                breaker.record_failure()
                await response.aclose()

            except httpx.HTTPStatusError as exc:
                last_exception = exc
                if not self._should_retry_exception(exc):
                    raise
                breaker.record_failure()

            except httpx.RequestError as exc:
                last_exception = exc
                if not self._should_retry_exception(exc):
                    raise
                breaker.record_failure()

            if attempt >= self.config.max_retries:
                break

            backoff = self._compute_backoff(attempt)
            logger.warning(
                "resilient_client_retrying",
                service=request.service,
                method=method,
                path=request.path,
                attempt=attempt + 1,
                backoff_s=backoff,
                error=type(last_exception).__name__ if last_exception else None,
            )
            await asyncio.sleep(backoff)

        if last_exception is not None:
            raise last_exception

        raise ResilientClientError(
            f"Failed to call {request.service} {method} {request.path} with no terminal response"
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> ResilientClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    def _build_headers(
        self,
        inbound_headers: Mapping[str, str],
        idempotency_key: str | None,
    ) -> dict[str, str]:
        headers = dict(inbound_headers)
        headers.setdefault("X-Butler-Source", self.source_service)
        headers.setdefault("X-Butler-Request-ID", str(uuid.uuid4()))
        if idempotency_key:
            headers.setdefault("X-Idempotency-Key", idempotency_key)
        return headers

    def _is_retry_allowed(self, request: InternalRequest, method: str) -> bool:
        if request.retryable is not None:
            return request.retryable

        if method in self.IDEMPOTENT_METHODS:
            return True

        return bool(request.idempotency_key)

    def _should_retry_exception(self, exc: Exception) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            status_code = exc.response.status_code
            return status_code in self.RETRYABLE_STATUS_CODES

        return bool(
            isinstance(
                exc,
                (
                    httpx.ConnectError,
                    httpx.ConnectTimeout,
                    httpx.ReadTimeout,
                    httpx.WriteTimeout,
                    httpx.PoolTimeout,
                    httpx.RemoteProtocolError,
                ),
            )
        )

    def _compute_backoff(self, attempt: int) -> float:
        base = min(
            self.config.base_backoff_seconds * (2**attempt),
            self.config.max_backoff_seconds,
        )
        jitter = base * self.config.jitter_ratio * random.random()
        return base + jitter
