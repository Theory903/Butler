"""
Tenant Metering Service - Append-Only Usage Tracking

Records tenant usage events for billing and analytics.
Append-only - usage events are never mutated.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from services.tenant.namespace import get_tenant_namespace

logger = structlog.get_logger(__name__)


class ResourceType(StrEnum):
    """Resource types for metering."""

    MODEL_TOKENS = "model_tokens"
    MODEL_REQUESTS = "model_requests"
    TOOL_EXECUTIONS = "tool_executions"
    API_REQUESTS = "api_requests"
    STORAGE_BYTES = "storage_bytes"
    BANDWIDTH_BYTES = "bandwidth_bytes"


class Provider(StrEnum):
    """Provider names for metering."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"
    BEDROCK = "bedrock"
    LOCAL = "local"


@dataclass(frozen=True, slots=True)
class UsageEvent:
    """
    Usage event for billing and analytics.

    Append-only - never mutated after creation.
    """

    id: str
    tenant_id: str
    account_id: str
    user_id: str | None
    request_id: str
    session_id: str | None
    provider: Provider
    resource_type: ResourceType
    quantity: Decimal
    unit: str
    cost_usd: Decimal
    metadata: dict[str, Any]
    recorded_at: datetime

    @classmethod
    def create(
        cls,
        tenant_id: str,
        account_id: str,
        provider: Provider,
        resource_type: ResourceType,
        quantity: Decimal,
        unit: str,
        cost_usd: Decimal,
        request_id: str,
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UsageEvent:
        """Create a new usage event."""
        return cls(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            account_id=account_id,
            user_id=user_id,
            request_id=request_id,
            session_id=session_id,
            provider=provider,
            resource_type=resource_type,
            quantity=quantity,
            unit=unit,
            cost_usd=cost_usd,
            metadata=metadata or {},
            recorded_at=datetime.now(UTC),
        )


class TenantMeteringService:
    """
    Tenant metering service for usage tracking.

    Records usage events to append-only table and Redis for real-time tracking.
    Events are never mutated - only inserted.
    """

    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
    ) -> None:
        """Initialize metering service."""
        self._db = db
        self._redis = redis

    def _usage_key(self, tenant_id: str, resource_type: ResourceType) -> str:
        """Generate Redis key for usage tracking using TenantNamespace."""
        namespace = get_tenant_namespace(tenant_id)
        return f"{namespace.prefix}:usage:{resource_type}"

    def _daily_usage_key(self, tenant_id: str, resource_type: ResourceType, date: str) -> str:
        """Generate Redis key for daily usage tracking using TenantNamespace."""
        namespace = get_tenant_namespace(tenant_id)
        return f"{namespace.prefix}:usage:daily:{date}:{resource_type}"

    async def record_event(self, event: UsageEvent) -> None:
        """
        Record a usage event.

        Records to Redis for real-time tracking and prepares for database batch insert.

        Args:
            event: Usage event to record

        Raises:
            ValueError: If event validation fails
        """
        # Validate event
        if event.quantity < 0:
            raise ValueError(f"Quantity cannot be negative: {event.quantity}")

        if event.cost_usd < 0:
            raise ValueError(f"Cost cannot be negative: {event.cost_usd}")

        # Record to Redis for real-time tracking
        usage_key = self._usage_key(event.tenant_id, event.resource_type)
        daily_key = self._daily_usage_key(
            event.tenant_id,
            event.resource_type,
            event.recorded_at.strftime("%Y-%m-%d"),
        )

        # Increment counters
        pipe = self._redis.pipeline()
        pipe.hincrby(usage_key, "total_quantity", int(event.quantity))
        pipe.hincrbyfloat(usage_key, "total_cost", float(event.cost_usd))
        pipe.hincrby(usage_key, "event_count", 1)
        pipe.expire(usage_key, 86400 * 30)  # 30 days TTL

        pipe.hincrby(daily_key, "total_quantity", int(event.quantity))
        pipe.hincrbyfloat(daily_key, "total_cost", float(event.cost_usd))
        pipe.hincrby(daily_key, "event_count", 1)
        pipe.expire(daily_key, 86400 * 7)  # 7 days TTL

        await pipe.execute()

        # TODO: Queue for database batch insert
        # For now, we'll use Redis for real-time and implement DB batch later

        logger.info(
            "usage_event_recorded",
            event_id=event.id,
            tenant_id=event.tenant_id,
            resource_type=event.resource_type,
            quantity=event.quantity,
            cost_usd=event.cost_usd,
        )

    async def record_events_batch(self, events: list[UsageEvent]) -> None:
        """
        Record multiple usage events in batch.

        Args:
            events: List of usage events to record

        Raises:
            ValueError: If any event validation fails
        """
        for event in events:
            await self.record_event(event)

        logger.info(
            "usage_events_batch_recorded",
            count=len(events),
        )

    async def get_usage_summary(
        self,
        tenant_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> dict[str, Any]:
        """
        Get usage summary for tenant in date range.

        Queries Redis for real-time summary.

        Args:
            tenant_id: Tenant UUID
            start_date: Start of date range
            end_date: End of date range

        Returns:
            Usage summary with totals by resource type and provider
        """
        # Aggregate daily usage from Redis
        summary = {
            "tenant_id": tenant_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "resource_types": {},
            "total_cost_usd": Decimal("0"),
            "total_events": 0,
        }

        current_date = start_date.date()
        end_date_only = end_date.date()

        while current_date <= end_date_only:
            date_str = current_date.strftime("%Y-%m-%d")

            # Get all resource types for this date
            pattern = f"usage:daily:{date_str}:tenant:{tenant_id}:*"
            keys = await self._redis.keys(pattern)

            for key in keys:
                # Extract resource type from key
                parts = key.split(":")
                if len(parts) >= 5:
                    resource_type = parts[4]

                    # Get daily stats
                    data = await self._redis.hgetall(key)
                    if data:
                        quantity = Decimal(data.get(b"total_quantity", b"0").decode())
                        cost = Decimal(data.get(b"total_cost", b"0").decode())
                        event_count = int(data.get(b"event_count", b"0").decode())

                        if resource_type not in summary["resource_types"]:
                            summary["resource_types"][resource_type] = {
                                "total_quantity": Decimal("0"),
                                "total_cost_usd": Decimal("0"),
                                "event_count": 0,
                            }

                        summary["resource_types"][resource_type]["total_quantity"] += quantity
                        summary["resource_types"][resource_type]["total_cost_usd"] += cost
                        summary["resource_types"][resource_type]["event_count"] += event_count
                        summary["total_cost_usd"] += cost
                        summary["total_events"] += event_count

            current_date += timedelta(days=1)

        logger.debug(
            "usage_summary_retrieved",
            tenant_id=tenant_id,
            total_cost_usd=summary["total_cost_usd"],
            total_events=summary["total_events"],
        )

        return summary

    async def get_daily_usage(
        self,
        tenant_id: str,
        date: datetime,
    ) -> dict[str, Any]:
        """
        Get usage summary for tenant on specific date.

        Args:
            tenant_id: Tenant UUID
            date: Date to query

        Returns:
            Daily usage summary by resource type
        """
        date_str = date.strftime("%Y-%m-%d")
        pattern = f"usage:daily:{date_str}:tenant:{tenant_id}:*"
        keys = await self._redis.keys(pattern)

        daily_usage = {
            "tenant_id": tenant_id,
            "date": date_str,
            "resource_types": {},
            "total_cost_usd": Decimal("0"),
            "total_events": 0,
        }

        for key in keys:
            parts = key.split(":")
            if len(parts) >= 5:
                resource_type = parts[4]

                data = await self._redis.hgetall(key)
                if data:
                    quantity = Decimal(data.get(b"total_quantity", b"0").decode())
                    cost = Decimal(data.get(b"total_cost", b"0").decode())
                    event_count = int(data.get(b"event_count", b"0").decode())

                    daily_usage["resource_types"][resource_type] = {
                        "total_quantity": quantity,
                        "total_cost_usd": cost,
                        "event_count": event_count,
                    }
                    daily_usage["total_cost_usd"] += cost
                    daily_usage["total_events"] += event_count

        logger.debug(
            "daily_usage_retrieved",
            tenant_id=tenant_id,
            date=date_str,
            total_cost_usd=daily_usage["total_cost_usd"],
        )

        return daily_usage

    async def get_realtime_usage(
        self,
        tenant_id: str,
        resource_type: ResourceType,
    ) -> dict[str, Any]:
        """
        Get real-time usage statistics for tenant and resource.

        Args:
            tenant_id: Tenant UUID
            resource_type: Resource type

        Returns:
            Real-time usage statistics
        """
        key = self._usage_key(tenant_id, resource_type)
        data = await self._redis.hgetall(key)

        if not data:
            return {
                "tenant_id": tenant_id,
                "resource_type": resource_type,
                "total_quantity": Decimal("0"),
                "total_cost_usd": Decimal("0"),
                "event_count": 0,
            }

        return {
            "tenant_id": tenant_id,
            "resource_type": resource_type,
            "total_quantity": Decimal(data.get(b"total_quantity", b"0").decode()),
            "total_cost_usd": Decimal(data.get(b"total_cost", b"0").decode()),
            "event_count": int(data.get(b"event_count", b"0").decode()),
        }
