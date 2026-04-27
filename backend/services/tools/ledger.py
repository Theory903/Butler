"""Tool execution ledger service.

Butler-owned service for durable, tenant-scoped tool execution ledger writes.
Hardened for high concurrency, strict observability, and cache resilience.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Final, TypedDict
from uuid import UUID, uuid4

import structlog
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from domain.tools.ledger import (
    ExecutionStatus,
    PolicyDecision,
    ToolExecutionLedger,
    ToolExecutionLedgerEntry,
)
from domain.tools.models import ToolExecution
from services.tenant.context import TenantContext
from services.tenant.namespace import TenantNamespace

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

# Constants
CACHE_TTL_SECONDS: Final[int] = 3600
REDACTED_STR: Final[str] = "[REDACTED]"
SENSITIVE_MARKERS: Final[frozenset[str]] = frozenset(
    ["api_key", "authorization", "bearer", "password", "secret", "token"]
)

# Lua script for atomic JSON patching in Redis to prevent read-modify-write race conditions
LUA_JSON_PATCH = """
local val = redis.call('GET', KEYS[1])
if not val then return nil end
local data = cjson.decode(val)
local patch = cjson.decode(ARGV[1])
for k, v in pairs(patch) do
    data[k] = v
end
redis.call('SETEX', KEYS[1], tonumber(ARGV[2]), cjson.encode(data))
return 1
"""


class ToolAggregationResult(TypedDict):
    """Strict typing for tool aggregations."""
    count: int
    avg_latency_ms: float
    completed_count: int
    failed_count: int


def _json_default(value: Any) -> str:
    """Safely serialize common non-JSON primitive values."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return repr(value)


class ToolExecutionLedgerService(ToolExecutionLedger):
    """Tenant-scoped service implementation for tool execution ledger."""

    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        namespace: TenantNamespace,
        *,
        autocommit: bool = False,
    ) -> None:
        self._db = db
        self._redis = redis
        self._namespace = namespace
        self._autocommit = autocommit
        # Register Lua script for performance (Redis parses it once)
        self._patch_script = self._redis.register_script(LUA_JSON_PATCH)

    def hash_payload(self, payload: dict[str, Any] | None) -> str | None:
        """Return stable SHA256 hash for JSON-like payloads."""
        if payload is None:
            return None

        # Note: In a highly perf-sensitive path, consider `orjson` instead of standard `json`
        normalized = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=_json_default,
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _cache_key(self, ctx: TenantContext, execution_id: UUID) -> str:
        return self._namespace.key(ctx, "tool_ledger", str(execution_id))

    async def _maybe_commit(self) -> None:
        if self._autocommit:
            await self._db.commit()

    async def create_entry(
        self,
        ctx: TenantContext,
        account_id: UUID,
        session_id: str,
        tool_name: str,
        tool_spec_version: str,
        input_hash: str,
        workflow_id: UUID | None = None,
        task_id: UUID | None = None,
        risk_tier: str = "unknown",
        idempotency_key: str | None = None,
    ) -> ToolExecutionLedgerEntry:
        """Create a pending ledger entry before tool execution."""
        with tracer.start_as_current_span("tool_ledger.create_entry") as span:
            execution_id = uuid4()
            now = datetime.now(UTC)

            span.set_attributes(
                {
                    "butler.tenant_id": ctx.tenant_id,
                    "butler.account_id": str(account_id),
                    "butler.session_id": session_id,
                    "butler.tool_name": tool_name,
                    "butler.execution_id": str(execution_id),
                }
            )

            try:
                entry = ToolExecutionLedgerEntry(
                    execution_id=execution_id,
                    tenant_id=ctx.tenant_id,
                    account_id=str(account_id),
                    session_id=session_id,
                    tool_name=tool_name,
                    tool_spec_version=tool_spec_version,
                    input_hash=input_hash,
                    status=ExecutionStatus.PENDING,
                    created_at=now,
                    updated_at=now,
                    workflow_id=str(workflow_id) if workflow_id else None,
                    task_id=str(task_id) if task_id else None,
                )

                execution = ToolExecution(
                    id=execution_id,
                    tenant_id=UUID(ctx.tenant_id),
                    account_id=account_id,
                    task_id=task_id,
                    workflow_id=workflow_id,
                    tool_name=tool_name,
                    input_params={
                        "ledger": {
                            "session_id": session_id,
                            "tool_spec_version": tool_spec_version,
                            "input_hash": input_hash,
                        }
                    },
                    risk_tier=risk_tier,
                    status=ExecutionStatus.PENDING.value,
                    idempotency_key=idempotency_key,
                )

                self._db.add(execution)
                await self._db.flush()
                await self._maybe_commit()

                # Best-effort caching. Redis failure should not block DB writes.
                await self._safe_cache_set(ctx, execution_id, entry)

                logger.info(
                    "tool_ledger_entry_created",
                    tenant_id=ctx.tenant_id,
                    account_id=str(account_id),
                    session_id=session_id,
                    execution_id=str(execution_id),
                    tool_name=tool_name,
                )
                return entry

            except Exception as e:
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR))
                logger.error("tool_ledger_creation_failed", error=str(e), exc_info=True)
                raise

    async def update_entry_status(
        self,
        ctx: TenantContext,
        execution_id: UUID,
        status: ExecutionStatus,
    ) -> None:
        """Update ledger entry status, tenant-scoped."""
        with tracer.start_as_current_span("tool_ledger.update_status") as span:
            now = datetime.now(UTC)
            span.set_attributes(
                {
                    "butler.tenant_id": ctx.tenant_id,
                    "butler.execution_id": str(execution_id),
                    "butler.status": status.value,
                }
            )

            try:
                stmt = (
                    update(ToolExecution)
                    .where(
                        ToolExecution.id == execution_id,
                        ToolExecution.tenant_id == UUID(ctx.tenant_id),
                    )
                    .values(
                        status=status.value,
                        completed_at=now
                        if status in {
                            ExecutionStatus.COMPLETED,
                            ExecutionStatus.FAILED,
                            ExecutionStatus.CANCELLED,
                        }
                        else None,
                    )
                    .execution_options(synchronize_session=False)
                )

                result = await self._db.execute(stmt)
                if result.rowcount == 0:
                    raise LookupError(f"Tool execution ledger entry not found: {execution_id}")

                await self._maybe_commit()

                await self._safe_cache_patch(
                    ctx,
                    execution_id,
                    {
                        "status": status.value,
                        "updated_at": now.isoformat(),
                    },
                )

                logger.info(
                    "tool_ledger_status_updated",
                    tenant_id=ctx.tenant_id,
                    execution_id=str(execution_id),
                    status=status.value,
                )

            except Exception as e:
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR))
                raise

    async def finalize_entry(
        self,
        ctx: TenantContext,
        execution_id: UUID,
        status: ExecutionStatus,
        output_hash: str | None = None,
        latency_ms: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        policy_decision: PolicyDecision | None = None,
        sandbox_used: bool = False,
        approval_id: str | None = None,
        degraded_mode: str | None = None,
        compensation_handler_id: str | None = None,
    ) -> None:
        """Finalize ledger entry after execution."""
        with tracer.start_as_current_span("tool_ledger.finalize") as span:
            now = datetime.now(UTC)
            span.set_attributes(
                {
                    "butler.tenant_id": ctx.tenant_id,
                    "butler.execution_id": str(execution_id),
                    "butler.status": status.value,
                    "butler.sandbox_used": sandbox_used,
                }
            )

            if latency_ms is not None:
                span.set_attribute("butler.latency_ms", latency_ms)

            try:
                output_result = {
                    "ledger": {
                        "output_hash": output_hash,
                        "policy_decision": (policy_decision.value if policy_decision else None),
                        "sandbox_used": sandbox_used,
                        "approval_id": approval_id,
                        "degraded_mode": degraded_mode,
                        "compensation_handler_id": compensation_handler_id,
                    }
                }

                error_data = None
                if error_code or error_message:
                    error_data = {
                        "error_code": error_code,
                        "error_message": self._redact_error_message(error_message),
                    }

                stmt = (
                    update(ToolExecution)
                    .where(
                        ToolExecution.id == execution_id,
                        ToolExecution.tenant_id == UUID(ctx.tenant_id),
                    )
                    .values(
                        status=status.value,
                        completed_at=now,
                        duration_ms=latency_ms,
                        output_result=output_result,
                        error_data=error_data,
                    )
                    .execution_options(synchronize_session=False)
                )

                result = await self._db.execute(stmt)
                if result.rowcount == 0:
                    raise LookupError(f"Tool execution ledger entry not found: {execution_id}")

                await self._maybe_commit()

                await self._safe_cache_patch(
                    ctx,
                    execution_id,
                    {
                        "status": status.value,
                        "updated_at": now.isoformat(),
                        "output_hash": output_hash,
                        "latency_ms": latency_ms,
                        "error_code": error_code,
                        "error_message": error_data["error_message"] if error_data else None,
                        "policy_decision": (policy_decision.value if policy_decision else None),
                        "sandbox_used": sandbox_used,
                        "approval_id": approval_id,
                        "degraded_mode": degraded_mode,
                        "compensation_handler_id": compensation_handler_id,
                    },
                )

                logger.info(
                    "tool_ledger_entry_finalized",
                    tenant_id=ctx.tenant_id,
                    execution_id=str(execution_id),
                    status=status.value,
                    latency_ms=latency_ms,
                )

            except Exception as e:
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR))
                raise

    # ----------------------------------------------------------------------
    # Resilience & Caching Layer
    # ----------------------------------------------------------------------

    async def _safe_cache_set(self, ctx: TenantContext, execution_id: UUID, entry: ToolExecutionLedgerEntry) -> None:
        """Best-effort caching. Swallows Redis errors to protect DB transactions."""
        try:
            payload = json.dumps(self._entry_to_cache_payload(entry), default=_json_default)
            await self._redis.set(self._cache_key(ctx, execution_id), payload, ex=CACHE_TTL_SECONDS)
        except RedisError as e:
            logger.warning("redis_cache_set_failed", execution_id=str(execution_id), error=str(e))

    async def _safe_cache_patch(self, ctx: TenantContext, execution_id: UUID, patch: dict[str, Any]) -> None:
        """Atomic JSON patching via Lua script. Best effort."""
        try:
            patch_json = json.dumps(patch, default=_json_default)
            await self._patch_script(
                keys=[self._cache_key(ctx, execution_id)],
                args=[patch_json, CACHE_TTL_SECONDS],
            )
        except RedisError as e:
            logger.warning("redis_cache_patch_failed", execution_id=str(execution_id), error=str(e))

    @staticmethod
    def _redact_error_message(message: str | None) -> str | None:
        if not message:
            return None

        lowered = message.lower()
        if any(marker in lowered for marker in SENSITIVE_MARKERS):
            return REDACTED_STR
        
        # Hard truncate to prevent DB bloat/DDoS via massive error traces
        return message[:2048]

    # ----------------------------------------------------------------------
    # Query Layer
    # ----------------------------------------------------------------------

    async def _execute_query(self, stmt) -> list[ToolExecutionLedgerEntry]:
        """Wrapper to standardise execution and error handling for reads."""
        try:
            result = await self._db.execute(stmt)
            return [self._model_to_entry(row) for row in result.scalars().all()]
        except SQLAlchemyError as e:
            logger.error("tool_ledger_query_failed", error=str(e))
            raise

    async def query_by_tenant(self, ctx: TenantContext, limit: int = 100) -> list[ToolExecutionLedgerEntry]:
        stmt = select(ToolExecution).where(ToolExecution.tenant_id == UUID(ctx.tenant_id)).order_by(ToolExecution.created_at.desc()).limit(min(max(limit, 1), 500))
        return await self._execute_query(stmt)

    async def query_by_account(self, ctx: TenantContext, account_id: UUID, limit: int = 100) -> list[ToolExecutionLedgerEntry]:
        stmt = select(ToolExecution).where(ToolExecution.tenant_id == UUID(ctx.tenant_id), ToolExecution.account_id == account_id).order_by(ToolExecution.created_at.desc()).limit(min(max(limit, 1), 500))
        return await self._execute_query(stmt)

    async def aggregate_by_tool(
        self,
        ctx: TenantContext,
        time_range: tuple[datetime, datetime] | None = None,
    ) -> dict[str, ToolAggregationResult]:
        """Aggregate current tenant's ledger entries by tool."""
        try:
            stmt = (
                select(
                    ToolExecution.tool_name,
                    func.count().label("count"),
                    func.avg(ToolExecution.duration_ms).label("avg_latency_ms"),
                    func.sum(case((ToolExecution.status == ExecutionStatus.COMPLETED.value, 1), else_=0)).label("completed_count"),
                    func.sum(case((ToolExecution.status == ExecutionStatus.FAILED.value, 1), else_=0)).label("failed_count"),
                )
                .where(ToolExecution.tenant_id == UUID(ctx.tenant_id))
                .group_by(ToolExecution.tool_name)
            )

            if time_range:
                stmt = stmt.where(ToolExecution.created_at >= time_range[0], ToolExecution.created_at <= time_range[1])

            result = await self._db.execute(stmt)
            rows = result.all()

            return {
                row.tool_name: {
                    "count": int(row.count or 0),
                    "avg_latency_ms": float(row.avg_latency_ms or 0.0),
                    "completed_count": int(row.completed_count or 0),
                    "failed_count": int(row.failed_count or 0),
                }
                for row in rows
            }
        except SQLAlchemyError as e:
            logger.error("tool_ledger_aggregation_failed", error=str(e))
            raise