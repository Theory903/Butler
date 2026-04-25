"""
Spend Tracking Service - Cost Monitoring and Aggregation

Tracks tenant spend across all cost categories.
Provides real-time spend visibility and forecasting.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

import structlog
from redis.asyncio import Redis

from services.tenant.namespace import get_tenant_namespace

logger = structlog.get_logger(__name__)


class CostCategory(StrEnum):
    """Cost categories for spend tracking."""

    MODEL_CALLS = "model_calls"
    TOOL_EXECUTIONS = "tool_executions"
    STORAGE = "storage"
    BANDWIDTH = "bandwidth"
    COMPUTE = "compute"
    QUEUE = "queue"
    DATABASE = "database"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class SpendRecord:
    """Individual spend record."""

    tenant_id: str
    amount_usd: Decimal
    category: CostCategory
    timestamp: datetime
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SpendSummary:
    """Spend summary for a period."""

    tenant_id: str
    period_start: datetime
    period_end: datetime
    total_spend_usd: Decimal
    category_breakdown: dict[CostCategory, Decimal]
    forecast_usd: Decimal | None = None


class SpendTrackingService:
    """
    Spend tracking service for cost monitoring.

    Tracks spend across categories, provides summaries,
    and forecasts future spend.
    """

    def __init__(self, redis: Redis) -> None:
        """Initialize spend tracking service."""
        self._redis = redis

    def _spend_key(self, tenant_id: str, category: CostCategory, period: str) -> str:
        """Generate Redis key for spend tracking using TenantNamespace."""
        namespace = get_tenant_namespace(tenant_id)
        return f"{namespace.prefix}:spend:{period}:{category}"

    def _hourly_key(self, tenant_id: str, category: CostCategory) -> str:
        """Generate hourly spend key."""
        now = datetime.now(UTC)
        hour_key = now.strftime("%Y-%m-%d-%H")
        return self._spend_key(tenant_id, category, f"hourly:{hour_key}")

    def _daily_key(self, tenant_id: str, category: CostCategory) -> str:
        """Generate daily spend key."""
        now = datetime.now(UTC)
        day_key = now.strftime("%Y-%m-%d")
        return self._spend_key(tenant_id, category, f"daily:{day_key}")

    def _monthly_key(self, tenant_id: str, category: CostCategory) -> str:
        """Generate monthly spend key."""
        now = datetime.now(UTC)
        month_key = now.strftime("%Y-%m")
        return self._spend_key(tenant_id, category, f"monthly:{month_key}")

    async def record_spend(
        self,
        tenant_id: str,
        amount_usd: Decimal,
        category: CostCategory,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Record spend for a tenant.

        Args:
            tenant_id: Tenant UUID
            amount_usd: Spend amount in USD
            category: Cost category
            metadata: Additional metadata
        """
        # Record to hourly, daily, monthly keys
        pipe = self._redis.pipeline()

        # Hourly
        hourly_key = self._hourly_key(tenant_id, category)
        pipe.hincrbyfloat(hourly_key, "total", float(amount_usd))
        pipe.hincrby(hourly_key, "count", 1)
        pipe.expire(hourly_key, 86400 * 2)  # 2 days TTL

        # Daily
        daily_key = self._daily_key(tenant_id, category)
        pipe.hincrbyfloat(daily_key, "total", float(amount_usd))
        pipe.hincrby(daily_key, "count", 1)
        pipe.expire(daily_key, 86400 * 7)  # 7 days TTL

        # Monthly
        monthly_key = self._monthly_key(tenant_id, category)
        pipe.hincrbyfloat(monthly_key, "total", float(amount_usd))
        pipe.hincrby(monthly_key, "count", 1)
        pipe.expire(monthly_key, 86400 * 30)  # 30 days TTL

        await pipe.execute()

        logger.debug(
            "spend_recorded",
            tenant_id=tenant_id,
            amount_usd=amount_usd,
            category=category,
        )

    async def get_category_spend(
        self,
        tenant_id: str,
        category: CostCategory,
        period: str = "daily",
    ) -> dict[str, Any]:
        """
        Get spend for a specific category and period.

        Args:
            tenant_id: Tenant UUID
            category: Cost category
            period: Period (hourly, daily, monthly)

        Returns:
            Spend data with total and count
        """
        if period == "hourly":
            key = self._hourly_key(tenant_id, category)
        elif period == "daily":
            key = self._daily_key(tenant_id, category)
        elif period == "monthly":
            key = self._monthly_key(tenant_id, category)
        else:
            return {"total": Decimal("0"), "count": 0}

        spend_data = await self._redis.hgetall(key)

        if spend_data:
            total = spend_data.get(b"total")
            count = spend_data.get(b"count")

            return {
                "total": Decimal(total.decode()) if total else Decimal("0"),
                "count": int(count.decode()) if count else 0,
            }

        return {"total": Decimal("0"), "count": 0}

    async def get_total_spend(
        self,
        tenant_id: str,
        period: str = "daily",
    ) -> Decimal:
        """
        Get total spend across all categories for a period.

        Args:
            tenant_id: Tenant UUID
            period: Period (hourly, daily, monthly)

        Returns:
            Total spend in USD
        """
        total_spend = Decimal("0")

        for category in CostCategory:
            category_spend = await self.get_category_spend(tenant_id, category, period)
            total_spend += category_spend["total"]

        return total_spend

    async def get_spend_summary(
        self,
        tenant_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> SpendSummary:
        """
        Get spend summary for a date range.

        Args:
            tenant_id: Tenant UUID
            period_start: Start of period
            period_end: End of period

        Returns:
            Spend summary with category breakdown
        """
        category_breakdown = {}
        total_spend = Decimal("0")

        # Aggregate by category
        for category in CostCategory:
            category_spend = await self.get_category_spend(tenant_id, category, "daily")
            category_breakdown[category] = category_spend["total"]
            total_spend += category_spend["total"]

        # Simple forecast based on current rate
        forecast = await self._forecast_spend(tenant_id, total_spend)

        return SpendSummary(
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
            total_spend_usd=total_spend,
            category_breakdown=category_breakdown,
            forecast_usd=forecast,
        )

    async def _forecast_spend(
        self,
        tenant_id: str,
        current_spend: Decimal,
    ) -> Decimal | None:
        """
        Forecast future spend based on current rate.

        Args:
            tenant_id: Tenant UUID
            current_spend: Current spend

        Returns:
            Forecasted spend
        """
        # Get hourly spend for the last few hours to calculate rate
        now = datetime.now(UTC)

        # Get last 3 hours of data
        hourly_spend = []
        for i in range(3):
            hour_key = now - timedelta(hours=i)
            hour_str = hour_key.strftime("%Y-%m-%d-%H")

            # Sum across all categories for this hour
            hour_total = Decimal("0")
            for category in CostCategory:
                key = f"spend:hourly:{hour_str}:{tenant_id}:{category}"
                spend_data = await self._redis.hget(key, "total")
                if spend_data:
                    hour_total += Decimal(spend_data.decode())

            hourly_spend.append(hour_total)

        if not hourly_spend or sum(hourly_spend) == 0:
            return None

        # Calculate average hourly rate
        avg_hourly_rate = sum(hourly_spend) / len(hourly_spend)

        # Forecast for remaining hours in the day
        hours_remaining = 24 - now.hour
        return current_spend + (avg_hourly_rate * hours_remaining)

    async def get_top_spenders(
        self,
        limit: int = 10,
        period: str = "daily",
    ) -> list[dict[str, Any]]:
        """
        Get top spending tenants.

        Args:
            limit: Number of top spenders to return
            period: Period (daily, monthly)

        Returns:
            List of top spenders with spend amounts
        """
        # This would require scanning all tenant keys
        # For now, return empty list
        # TODO: Implement with Redis SCAN or maintain a sorted set
        return []

    async def get_spend_trend(
        self,
        tenant_id: str,
        days: int = 7,
    ) -> list[dict[str, Any]]:
        """
        Get spend trend over multiple days.

        Args:
            tenant_id: Tenant UUID
            days: Number of days to include

        Returns:
            List of daily spend amounts
        """
        trend = []
        now = datetime.now(UTC)

        for i in range(days):
            date = now - timedelta(days=i)
            day_str = date.strftime("%Y-%m-%d")

            # Sum across all categories for this day
            day_total = Decimal("0")
            for category in CostCategory:
                key = f"spend:daily:{day_str}:{tenant_id}:{category}"
                spend_data = await self._redis.hget(key, "total")
                if spend_data:
                    day_total += Decimal(spend_data.decode())

            trend.append(
                {
                    "date": day_str,
                    "total_spend_usd": day_total,
                }
            )

        return trend

    async def get_category_breakdown(
        self,
        tenant_id: str,
        period: str = "daily",
    ) -> dict[CostCategory, dict[str, Any]]:
        """
        Get detailed breakdown by category.

        Args:
            tenant_id: Tenant UUID
            period: Period (hourly, daily, monthly)

        Returns:
            Dictionary mapping category to spend details
        """
        breakdown = {}

        for category in CostCategory:
            spend_data = await self.get_category_spend(tenant_id, category, period)
            breakdown[category] = spend_data

        return breakdown
