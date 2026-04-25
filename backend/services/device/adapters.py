"""Device adapters — v3.1 production transport.

Changes from v3.0:
  - APIAdapter: shared SafeRequestClient (injected, not per-call) for SSRF protection
  - Auth strategy support: none | bearer | basic | hmac
  - Configurable retry budget (2 retries, exponential back-off)
  - Retryable vs non-retryable error classification
  - Circuit breaker state per adapter
  - MockAdapter fallback preserved

Auth strategy is read from device.metadata:
  {"auth_type": "bearer", "token": "..."}  → Bearer <token>
  {"auth_type": "basic", "user": "...", "password": "..."}  → Basic auth
  {"auth_type": "hmac", "secret": "..."} → HMAC-SHA256 body signature
  {} or missing → no auth
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
from abc import ABC, abstractmethod
from typing import Any

import structlog

from core.circuit_breaker import get_circuit_breaker_registry
from services.security.safe_request import SafeRequestClient

logger = structlog.get_logger(__name__)

# ── Retry config ──────────────────────────────────────────────────────────────
_MAX_RETRIES = 2
_BACKOFF_BASE_S = 0.5
_CONNECT_TIMEOUT_S = 5.0
_READ_TIMEOUT_S = 10.0

# Non-retryable HTTP status codes (client errors, auth failures)
_NON_RETRYABLE_STATUSES = frozenset({400, 401, 403, 404, 405, 409, 422, 451})


# ── Base ──────────────────────────────────────────────────────────────────────


class DeviceRegistry:
    """Minimal shim — the real model is in domain/device/models.py."""

    id: Any
    protocol: str
    metadata: dict


class DeviceAdapterBase(ABC):
    """Abstract interface defining required behaviour for any hardware connector."""

    @abstractmethod
    async def fetch_state(self, device: Any) -> dict[str, Any]:
        """Fetch real-time ambient state from the device."""

    @abstractmethod
    async def dispatch_command(
        self, device: Any, action: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        """Dispatch a physical mutation command to the device."""


# ── Auth helpers ──────────────────────────────────────────────────────────────


def _build_auth_headers(metadata: dict) -> dict[str, str]:
    auth_type = (metadata.get("auth_type") or "").lower()
    if auth_type == "bearer":
        token = metadata.get("token", "")
        return {"Authorization": f"Bearer {token}"}
    if auth_type == "basic":
        user = metadata.get("user", "")
        password = metadata.get("password", "")
        encoded = base64.b64encode(f"{user}:{password}".encode()).decode()
        return {"Authorization": f"Basic {encoded}"}
    return {}  # hmac applied per-request body; no auth → empty


def _sign_hmac(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ── Retry logic ───────────────────────────────────────────────────────────────


def _is_retryable(exc: Exception) -> bool:
    # P0 hardening: Check for retryable exceptions without httpx dependency
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    # Check for HTTP status errors if exception has response attribute
    try:
        response = getattr(exc, "response", None)
        if response is not None:
            status_code = getattr(response, "status_code", None)
            if status_code is not None:
                return status_code not in _NON_RETRYABLE_STATUSES
    except Exception:
        pass
    return False


async def _with_retry(coro_factory, *, breaker=None, max_retries: int = _MAX_RETRIES):
    """Execute coro_factory() with exponential back-off retry and circuit breaker."""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        if breaker and not breaker.allow_request():
            raise ConnectionError(f"Circuit breaker OPEN for {breaker.name}")
        try:
            result = await coro_factory()
            if breaker:
                breaker.record_success()
            return result
        except Exception as exc:
            last_exc = exc
            if breaker:
                breaker.record_failure()
            if not _is_retryable(exc) or attempt == max_retries:
                raise
            backoff = _BACKOFF_BASE_S * (2**attempt)
            logger.debug("device.retry", attempt=attempt + 1, backoff_s=backoff, error=str(exc))
            await asyncio.sleep(backoff)
    raise last_exc  # type: ignore[misc]


# ── MockAdapter ───────────────────────────────────────────────────────────────


class MockAdapter(DeviceAdapterBase):
    """Fallback dummy adapter used for simulation and unknown protocols."""

    async def fetch_state(self, device: Any) -> dict[str, Any]:
        logger.debug("device.mock.fetch_state", device_id=getattr(device, "id", "?"))
        return {"mocked_reachable": True, "simulated_value": "nominal", "_tier": "mock"}

    async def dispatch_command(
        self, device: Any, action: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        logger.info(
            "device.mock.dispatch_command",
            device_id=getattr(device, "id", "?"),
            action=action,
        )
        return {"status": "success", "latency": 12, "_tier": "mock"}


# ── APIAdapter ────────────────────────────────────────────────────────────────


class APIAdapter(DeviceAdapterBase):
    """Production HTTP adapter for LAN/cloud device endpoints.

    Supports:
      - Shared SafeRequestClient (connection pool, not per-call) for SSRF protection
      - Authentication: none | bearer | basic | hmac
      - Retry budget (2 retries, exponential back-off)
      - Circuit breaker per-instance
      - Fallback to MockAdapter on persistent failure
    """

    def __init__(
        self,
        client: SafeRequestClient | None = None,
        breaker_name: str = "device_api",
    ) -> None:
        self._client = client or SafeRequestClient()
        self._tenant_id = "default"  # P0 hardening: Use default tenant for device operations
        registry = get_circuit_breaker_registry()
        self._breaker = registry.register(breaker_name, threshold=4, window_s=60, recovery_s=30)
        self._mock = MockAdapter()

    async def fetch_state(self, device: Any) -> dict[str, Any]:
        meta = getattr(device, "metadata", {}) or {}
        endpoint_url = meta.get("endpoint_url") or meta.get("state_url")
        if not endpoint_url:
            logger.warning("device.api.no_endpoint", device_id=getattr(device, "id", "?"))
            return await self._mock.fetch_state(device)

        auth_headers = _build_auth_headers(meta)

        async def _call():
            # P0 hardening: Use SafeRequestClient for SSRF protection
            resp = await self._client.get(endpoint_url, self._tenant_id, headers=auth_headers)
            resp.raise_for_status()
            return resp.json()

        try:
            result = await _with_retry(_call, breaker=self._breaker)
            result["_tier"] = "api"
            return result
        except Exception as exc:
            logger.warning(
                "device.api.fetch_state_failed",
                device_id=getattr(device, "id", "?"),
                endpoint=endpoint_url,
                error=str(exc),
            )
            fallback = await self._mock.fetch_state(device)
            fallback["_tier"] = "mock_fallback"
            fallback["_error"] = str(exc)
            return fallback

    async def dispatch_command(
        self, device: Any, action: str, parameters: dict[str, Any]
    ) -> dict[str, Any]:
        meta = getattr(device, "metadata", {}) or {}
        endpoint_url = meta.get("endpoint_url") or meta.get("command_url")
        if not endpoint_url:
            logger.warning("device.api.no_command_endpoint", device_id=getattr(device, "id", "?"))
            return await self._mock.dispatch_command(device, action, parameters)

        body = {"action": action, **parameters}
        body_bytes = json.dumps(body).encode()
        auth_headers = _build_auth_headers(meta)

        # HMAC: add signature header
        if meta.get("auth_type", "").lower() == "hmac":
            sig = _sign_hmac(body_bytes, meta.get("secret", ""))
            auth_headers["X-Butler-Signature"] = sig

        auth_headers["Content-Type"] = "application/json"

        async def _call():
            # P0 hardening: Use SafeRequestClient for SSRF protection
            resp = await self._client.post(
                endpoint_url, self._tenant_id, json=body, headers=auth_headers
            )
            resp.raise_for_status()
            return resp.json()

        try:
            result = await _with_retry(_call, breaker=self._breaker)
            result["_tier"] = "api"
            return result
        except Exception as exc:
            logger.warning(
                "device.api.dispatch_failed",
                device_id=getattr(device, "id", "?"),
                action=action,
                error=str(exc),
            )
            # For command dispatch, do NOT silently mock — raise so caller knows it failed
            raise RuntimeError(
                f"Device command '{action}' to {endpoint_url} failed: {exc}"
            ) from exc


# ── AdapterRegistry ───────────────────────────────────────────────────────────


class AdapterRegistry:
    """Intelligently resolves device protocol names to adapters."""

    def __init__(self) -> None:
        # Shared SafeRequestClient across all APIAdapter instances
        _shared_client = SafeRequestClient()
        self._providers: dict[str, DeviceAdapterBase] = {
            "mock": MockAdapter(),
            "api": APIAdapter(client=_shared_client, breaker_name="device_api_default"),
            "http": APIAdapter(client=_shared_client, breaker_name="device_http"),
            "webhook": APIAdapter(client=_shared_client, breaker_name="device_webhook"),
        }

    def resolve(self, protocol_name: str) -> DeviceAdapterBase:
        # Fallback to Mock if the driver is not yet compiled into Butler
        adapter = self._providers.get(protocol_name, self._providers["mock"])
        if protocol_name not in self._providers:
            logger.warning(
                "device.registry.unknown_protocol", protocol=protocol_name, fallback="mock"
            )
        return adapter

    def register(self, protocol_name: str, adapter: DeviceAdapterBase) -> None:
        """Register a custom adapter (e.g., ZigbeeAdapter, MatterAdapter)."""
        self._providers[protocol_name] = adapter
        logger.info("device.registry.registered", protocol=protocol_name)
