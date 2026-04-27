from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import structlog
from fastapi import Request, Response
from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.responses import Response as StarletteResponse

from core.middleware import get_tenant_context
from infrastructure.cache import get_redis
from services.tenant.namespace import get_tenant_namespace

logger = structlog.get_logger(__name__)

IDEMPOTENCY_PREFIX = "idem"
DEFAULT_LOCK_TTL = timedelta(minutes=5)
DEFAULT_RESULT_TTL = timedelta(hours=24)
MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

_SAFE_RESPONSE_HEADERS = {
    "content-type",
    "location",
    "etag",
    "last-modified",
    "cache-control",
}


@dataclass(slots=True, frozen=True)
class IdempotencyConfig:
    lock_ttl: timedelta = DEFAULT_LOCK_TTL
    result_ttl: timedelta = DEFAULT_RESULT_TTL
    require_key_for_mutations: bool = False
    cache_client_errors: bool = True
    cache_server_errors: bool = False
    max_body_bytes_for_fingerprint: int = 1024 * 1024  # 1 MB


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Production-grade idempotency middleware.

    Guarantees:
    - same user + same idempotency key + same request fingerprint => replay cached response
    - same user + same idempotency key + request still processing => 409 conflict
    - same user + same idempotency key + different fingerprint => 409 conflict
    - 5xx responses are not cached by default
    """

    def __init__(
        self,
        app: Any,
        config: IdempotencyConfig | None = None,
    ) -> None:
        super().__init__(app)
        self._config = config or IdempotencyConfig()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method.upper() not in MUTATION_METHODS:
            return await call_next(request)

        idempotency_key = request.headers.get("X-Idempotency-Key")
        if not idempotency_key:
            if self._config.require_key_for_mutations:
                return self._problem(
                    status=400,
                    title="Missing Idempotency Key",
                    detail="Mutation requests must include X-Idempotency-Key.",
                    type_="https://docs.butler.lasmoid.ai/problems/missing-idempotency-key",
                )
            return await call_next(request)

        normalized_key = idempotency_key.strip()
        if not normalized_key:
            return self._problem(
                status=400,
                title="Invalid Idempotency Key",
                detail="X-Idempotency-Key must not be empty.",
                type_="https://docs.butler.lasmoid.ai/problems/invalid-idempotency-key",
            )

        user_scope = self._resolve_user_scope(request)
        request_fingerprint = await self._build_request_fingerprint(request)
        storage_key = self._build_storage_key(user_scope=user_scope, idem_key=normalized_key)

        redis = await get_redis()

        acquired = await redis.set(
            storage_key,
            json.dumps(
                {
                    "state": "processing",
                    "fingerprint": request_fingerprint,
                }
            ),
            nx=True,
            ex=int(self._config.lock_ttl.total_seconds()),
        )

        if acquired:
            try:
                response = await call_next(request)
                response_body = await self._extract_response_body(response)

                should_cache = self._should_cache_status(response.status_code)
                if should_cache and response_body is not None:
                    payload = self._serialize_cached_response(
                        response=response,
                        body=response_body,
                        fingerprint=request_fingerprint,
                    )
                    await redis.set(
                        storage_key,
                        json.dumps(payload),
                        ex=int(self._config.result_ttl.total_seconds()),
                    )
                else:
                    await redis.delete(storage_key)

                return self._rebuild_response(
                    original=response,
                    body=response_body,
                    replayed=False,
                )
            except Exception:
                await redis.delete(storage_key)
                raise

        raw_value = await redis.get(storage_key)
        if raw_value is None:
            logger.warning(
                "idempotency_race_key_missing_after_lock_failure",
                idempotency_key=normalized_key,
                user_scope=user_scope,
            )
            return await call_next(request)

        cached_record = self._safe_json_loads(raw_value)
        if not isinstance(cached_record, dict):
            logger.error(
                "idempotency_corrupt_cache_record",
                idempotency_key=normalized_key,
                user_scope=user_scope,
            )
            await redis.delete(storage_key)
            return await call_next(request)

        cached_fingerprint = str(cached_record.get("fingerprint") or "")
        if cached_fingerprint and cached_fingerprint != request_fingerprint:
            logger.warning(
                "idempotency_key_reused_with_different_request",
                idempotency_key=normalized_key,
                user_scope=user_scope,
            )
            return self._problem(
                status=409,
                title="Idempotency Key Reused",
                detail=("This idempotency key was already used for a different request payload."),
                type_="https://docs.butler.lasmoid.ai/problems/idempotency-key-reused",
            )

        state = cached_record.get("state")
        if state == "processing":
            logger.warning(
                "idempotency_conflict_processing",
                idempotency_key=normalized_key,
                user_scope=user_scope,
            )
            return self._problem(
                status=409,
                title="Idempotency Conflict",
                detail=(f"A request with key '{normalized_key}' is already being processed."),
                type_="https://docs.butler.lasmoid.ai/problems/idempotency-conflict",
            )

        if state == "completed":
            logger.info(
                "idempotency_replay_hit",
                idempotency_key=normalized_key,
                user_scope=user_scope,
                status_code=cached_record.get("status_code"),
            )
            return self._response_from_cache(cached_record)

        logger.error(
            "idempotency_unknown_record_state",
            idempotency_key=normalized_key,
            user_scope=user_scope,
            state=state,
        )
        await redis.delete(storage_key)
        return await call_next(request)

    def _resolve_user_scope(self, request: Request) -> str:
        """Resolve user scope for idempotency key isolation."""
        # Try to get tenant_id from TenantContext for multi-tenant isolation
        ctx = get_tenant_context()
        if ctx:
            return f"tenant:{ctx.tenant_id}"

        # Fallback to user-based scope for single-tenant or non-tenant contexts
        user_id = request.headers.get("X-User-Id") or request.headers.get(
            "X-Request-Id", "anonymous"
        )
        return f"user:{user_id}"

    def _get_storage_key(self, normalized_key: str, user_scope: str) -> str:
        """Generate tenant-scoped storage key for idempotency."""
        ctx = get_tenant_context()
        if ctx:
            namespace = get_tenant_namespace(ctx.tenant_id)
            return f"{namespace.prefix}:{IDEMPOTENCY_PREFIX}:{normalized_key}"
        # Fallback for non-tenant contexts
        return f"{IDEMPOTENCY_PREFIX}:{user_scope}:{normalized_key}"

    def _build_storage_key(self, user_scope: str, idem_key: str) -> str:
        """Build storage key with user scope."""
        return self._get_storage_key(idem_key, user_scope)

    async def _build_request_fingerprint(self, request: Request) -> str:
        raw_body = await request.body()
        if len(raw_body) > self._config.max_body_bytes_for_fingerprint:
            body_digest = hashlib.sha256(raw_body).hexdigest()
            normalized_body_repr = f"sha256:{body_digest}"
        else:
            normalized_body_repr = self._normalize_body_for_fingerprint(raw_body)

        fingerprint_payload = {
            "method": request.method.upper(),
            "path": request.url.path,
            "query": sorted(request.query_params.multi_items()),
            "content_type": request.headers.get("content-type", ""),
            "body": normalized_body_repr,
        }

        encoded = json.dumps(
            fingerprint_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _normalize_body_for_fingerprint(self, raw_body: bytes) -> str:
        if not raw_body:
            return ""

        try:
            parsed = json.loads(raw_body.decode("utf-8"))
            return json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        except Exception:
            return raw_body.decode("utf-8", errors="replace")

    def _build_storage_key(self, *, user_scope: str, idem_key: str) -> str:
        return f"{IDEMPOTENCY_PREFIX}:{user_scope}:{idem_key}"

    def _should_cache_status(self, status_code: int) -> bool:
        if status_code >= 500 and not self._config.cache_server_errors:
            return False
        return not (400 <= status_code < 500 and not self._config.cache_client_errors)

    async def _extract_response_body(self, response: Response) -> bytes | None:
        body = getattr(response, "body", None)
        if isinstance(body, bytes):
            return body

        if hasattr(response, "body_iterator") and response.body_iterator is not None:
            chunks: list[bytes] = []
            async for chunk in response.body_iterator:
                if isinstance(chunk, bytes):
                    chunks.append(chunk)
                else:
                    chunks.append(str(chunk).encode("utf-8"))
            return b"".join(chunks)

        return None

    def _serialize_cached_response(
        self,
        *,
        response: Response,
        body: bytes,
        fingerprint: str,
    ) -> dict[str, Any]:
        return {
            "state": "completed",
            "fingerprint": fingerprint,
            "status_code": response.status_code,
            "headers": self._filter_response_headers(response.headers),
            "body": self._decode_body_for_cache(body, response.headers.get("content-type")),
        }

    def _decode_body_for_cache(
        self,
        body: bytes,
        content_type: str | None,
    ) -> Any:
        if not body:
            return None

        normalized_content_type = (content_type or "").lower()
        if "application/json" in normalized_content_type:
            try:
                return json.loads(body.decode("utf-8"))
            except Exception:
                return {"raw": body.decode("utf-8", errors="replace")}

        return {
            "raw": body.decode("utf-8", errors="replace"),
        }

    def _filter_response_headers(
        self, headers: MutableHeaders | dict[str, str] | Any
    ) -> dict[str, str]:
        result: dict[str, str] = {}
        for key, value in headers.items():
            if key.lower() in _SAFE_RESPONSE_HEADERS:
                result[key] = value
        return result

    def _response_from_cache(self, record: dict[str, Any]) -> Response:
        headers = dict(record.get("headers") or {})
        headers["X-Idempotency-Replayed"] = "true"

        body = record.get("body")
        status_code = int(record.get("status_code") or 200)

        if isinstance(body, dict) and "raw" in body and len(body) == 1:
            return StarletteResponse(
                content=body["raw"],
                status_code=status_code,
                headers=headers,
                media_type=headers.get("content-type"),
            )

        return JSONResponse(
            content=body,
            status_code=status_code,
            headers=headers,
        )

    def _rebuild_response(
        self,
        *,
        original: Response,
        body: bytes | None,
        replayed: bool,
    ) -> Response:
        headers = dict(original.headers)
        if replayed:
            headers["X-Idempotency-Replayed"] = "true"

        if body is None:
            return original

        media_type = headers.get("content-type")
        return StarletteResponse(
            content=body,
            status_code=original.status_code,
            headers=headers,
            media_type=media_type,
            background=original.background,
        )

    def _safe_json_loads(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return None
        return None

    def _problem(
        self,
        *,
        status: int,
        title: str,
        detail: str,
        type_: str,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content={
                "type": type_,
                "title": title,
                "status": status,
                "detail": detail,
            },
        )
