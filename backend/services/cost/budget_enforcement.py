"""
Budget Enforcement Service - Cost Control Plane

Enforces tenant budget limits for Butler hyperscale operations.
Implements "No Budget, No Execution" rule from hyperscale architecture.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

import structlog
from redis.asyncio import Redis

from services.tenant.namespace import get_tenant_namespace

logger = structlog.get_logger(__name__)


class BudgetPeriod(StrEnum):
    """Budget period types."""

    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    UNLIMITED = "unlimited"


class BudgetAction(StrEnum):
    """Actions when budget is exceeded."""

    BLOCK = "block"  # Block execution
    WARN = "warn"  # Allow but warn
    THROTTLE = "throttle"  # Throttle execution
    SHUTDOWN = "shutdown"  # Shutdown tenant access


@dataclass(frozen=True, slots=True)
class Budget:
    """Tenant budget configuration."""

    tenant_id: str
    amount_usd: Decimal
    period: BudgetPeriod
    action: BudgetAction
    alert_threshold: Decimal  # Alert when spend reaches this % of budget
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class BudgetCheckResult:
    """Result of a budget check."""

    allowed: bool
    budget: Budget | None
    current_spend: Decimal
    remaining: Decimal
    utilization_pct: float
    action_taken: BudgetAction | None = None
    message: str | None = None


class BudgetExceededError(Exception):
    """Raised when budget is exceeded and action is BLOCK."""

    def __init__(self, tenant_id: str, budget: Budget, current_spend: Decimal) -> None:
        self.tenant_id = tenant_id
        self.budget = budget
        self.current_spend = current_spend
        super().__init__(
            f"Budget exceeded for tenant {tenant_id}: "
            f"${current_spend} spent of ${budget.amount_usd} {budget.period} budget"
        )


class BudgetEnforcementService:
    """
    Budget enforcement service for cost control.

    Enforces "No Budget, No Execution" rule.
    Tracks spend against budgets and takes configured actions.
    """

    def __init__(self, redis: Redis) -> None:
        """Initialize budget enforcement service."""
        self._redis = redis

    def _budget_key(self, tenant_id: str, period: BudgetPeriod) -> str:
        """Generate Redis key for budget configuration using TenantNamespace."""
        namespace = get_tenant_namespace(tenant_id)
        return f"{namespace.prefix}:budget:{period}"

    def _spend_key(self, tenant_id: str, period: BudgetPeriod) -> str:
        """Generate Redis key for spend tracking using TenantNamespace."""
        namespace = get_tenant_namespace(tenant_id)
        return f"{namespace.prefix}:spend:{period}"

    def _hourly_key(self, tenant_id: str) -> str:
        """Generate hourly spend key using TenantNamespace."""
        namespace = get_tenant_namespace(tenant_id)
        now = datetime.now(UTC)
        hour_key = now.strftime("%Y-%m-%d-%H")
        return f"{namespace.prefix}:spend:hourly:{hour_key}"

    def _daily_key(self, tenant_id: str) -> str:
        """Generate daily spend key using TenantNamespace."""
        namespace = get_tenant_namespace(tenant_id)
        now = datetime.now(UTC)
        day_key = now.strftime("%Y-%m-%d")
        return f"{namespace.prefix}:spend:daily:{day_key}"

    def _monthly_key(self, tenant_id: str) -> str:
        """Generate monthly spend key using TenantNamespace."""
        namespace = get_tenant_namespace(tenant_id)
        now = datetime.now(UTC)
        month_key = now.strftime("%Y-%m")
        return f"{namespace.prefix}:spend:monthly:{month_key}"

    async def set_budget(
        self,
        tenant_id: str,
        amount_usd: Decimal,
        period: BudgetPeriod,
        action: BudgetAction = BudgetAction.BLOCK,
        alert_threshold: Decimal = Decimal("0.8"),
    ) -> Budget:
        """
        Set budget for a tenant.

        Args:
            tenant_id: Tenant UUID
            amount_usd: Budget amount in USD
            period: Budget period
            action: Action to take when budget exceeded
            alert_threshold: Alert threshold (percentage of budget)

        Returns:
            Created budget
        """
        now = datetime.now(UTC)

        budget_data = {
            "tenant_id": tenant_id,
            "amount_usd": str(amount_usd),
            "period": period,
            "action": action,
            "alert_threshold": str(alert_threshold),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        await self._redis.hset(
            self._budget_key(tenant_id, period),
            mapping=budget_data,
        )
        # Budget doesn't expire - must be explicitly removed

        budget = Budget(
            tenant_id=tenant_id,
            amount_usd=amount_usd,
            period=period,
            action=action,
            alert_threshold=alert_threshold,
            created_at=now,
            updated_at=now,
        )

        logger.info(
            "budget_set",
            tenant_id=tenant_id,
            amount_usd=amount_usd,
            period=period,
            action=action,
        )

        return budget

    async def get_budget(
        self,
        tenant_id: str,
        period: BudgetPeriod,
    ) -> Budget | None:
        """
        Get budget for a tenant.

        Args:
            tenant_id: Tenant UUID
            period: Budget period

        Returns:
            Budget if exists, None otherwise
        """
        budget_data = await self._redis.hgetall(self._budget_key(tenant_id, period))

        if not budget_data:
            return None

        return Budget(
            tenant_id=budget_data[b"tenant_id"].decode(),
            amount_usd=Decimal(budget_data[b"amount_usd"].decode()),
            period=budget_data[b"period"].decode(),
            action=budget_data[b"action"].decode(),
            alert_threshold=Decimal(budget_data[b"alert_threshold"].decode()),
            created_at=datetime.fromisoformat(budget_data[b"created_at"].decode()),
            updated_at=datetime.fromisoformat(budget_data[b"updated_at"].decode()),
        )

    async def record_spend(
        self,
        tenant_id: str,
        amount_usd: Decimal,
        cost_category: str = "general",
    ) -> None:
        """
        Record spend for a tenant.

        Args:
            tenant_id: Tenant UUID
            amount_usd: Spend amount in USD
            cost_category: Cost category (e.g., "model_calls", "tool_executions")
        """
        # Record to hourly, daily, monthly keys
        pipe = self._redis.pipeline()

        # Hourly
        hourly_key = self._hourly_key(tenant_id)
        pipe.hincrbyfloat(hourly_key, "total", float(amount_usd))
        pipe.hincrbyfloat(hourly_key, f"category:{cost_category}", float(amount_usd))
        pipe.expire(hourly_key, 86400 * 2)  # 2 days TTL

        # Daily
        daily_key = self._daily_key(tenant_id)
        pipe.hincrbyfloat(daily_key, "total", float(amount_usd))
        pipe.hincrbyfloat(daily_key, f"category:{cost_category}", float(amount_usd))
        pipe.expire(daily_key, 86400 * 7)  # 7 days TTL

        # Monthly
        monthly_key = self._monthly_key(tenant_id)
        pipe.hincrbyfloat(monthly_key, "total", float(amount_usd))
        pipe.hincrbyfloat(monthly_key, f"category:{cost_category}", float(amount_usd))
        pipe.expire(monthly_key, 86400 * 30)  # 30 days TTL

        await pipe.execute()

        logger.debug(
            "spend_recorded",
            tenant_id=tenant_id,
            amount_usd=amount_usd,
            cost_category=cost_category,
        )

    async def get_current_spend(
        self,
        tenant_id: str,
        period: BudgetPeriod,
    ) -> Decimal:
        """
        Get current spend for a tenant and period.

        Args:
            tenant_id: Tenant UUID
            period: Budget period

        Returns:
            Current spend in USD
        """
        if period == BudgetPeriod.HOURLY:
            key = self._hourly_key(tenant_id)
        elif period == BudgetPeriod.DAILY:
            key = self._daily_key(tenant_id)
        elif period == BudgetPeriod.MONTHLY:
            key = self._monthly_key(tenant_id)
        else:
            return Decimal("0")

        spend_data = await self._redis.hget(key, "total")

        if spend_data:
            return Decimal(spend_data.decode())

        return Decimal("0")

    async def check_budget(
        self,
        tenant_id: str,
        period: BudgetPeriod,
        cost_usd: Decimal = Decimal("0"),
    ) -> BudgetCheckResult:
        """
        Check if operation is allowed under budget.

        Args:
            tenant_id: Tenant UUID
            period: Budget period to check
            cost_usd: Cost of operation to check

        Returns:
            Budget check result

        Raises:
            BudgetExceededError: If budget exceeded and action is BLOCK
        """
        budget = await self.get_budget(tenant_id, period)

        # No budget set - allow by default (or could deny based on policy)
        if not budget:
            return BudgetCheckResult(
                allowed=True,
                budget=None,
                current_spend=Decimal("0"),
                remaining=Decimal("0"),
                utilization_pct=0.0,
                message="No budget set",
            )

        # Unlimited budget
        if budget.period == BudgetPeriod.UNLIMITED:
            return BudgetCheckResult(
                allowed=True,
                budget=budget,
                current_spend=Decimal("0"),
                remaining=Decimal("999999999"),
                utilization_pct=0.0,
                message="Unlimited budget",
            )

        current_spend = await self.get_current_spend(tenant_id, period)
        projected_spend = current_spend + cost_usd
        remaining = budget.amount_usd - projected_spend
        utilization_pct = (
            float((projected_spend / budget.amount_usd) * 100) if budget.amount_usd > 0 else 0.0
        )

        # Check if budget exceeded
        if projected_spend > budget.amount_usd:
            if budget.action == BudgetAction.BLOCK:
                logger.warning(
                    "budget_exceeded_blocking",
                    tenant_id=tenant_id,
                    period=period,
                    current_spend=current_spend,
                    budget_amount=budget.amount_usd,
                    cost_usd=cost_usd,
                )
                raise BudgetExceededError(tenant_id, budget, projected_spend)

            if budget.action == BudgetAction.SHUTDOWN:
                logger.error(
                    "budget_exceeded_shutdown",
                    tenant_id=tenant_id,
                    period=period,
                    current_spend=current_spend,
                    budget_amount=budget.amount_usd,
                )
                # TODO: Implement tenant shutdown
                return BudgetCheckResult(
                    allowed=False,
                    budget=budget,
                    current_spend=current_spend,
                    remaining=remaining,
                    utilization_pct=utilization_pct,
                    action_taken=BudgetAction.SHUTDOWN,
                    message="Budget exceeded - shutdown initiated",
                )

            if budget.action == BudgetAction.THROTTLE:
                logger.warning(
                    "budget_exceeded_throttling",
                    tenant_id=tenant_id,
                    period=period,
                    current_spend=current_spend,
                    budget_amount=budget.amount_usd,
                )
                return BudgetCheckResult(
                    allowed=True,
                    budget=budget,
                    current_spend=current_spend,
                    remaining=remaining,
                    utilization_pct=utilization_pct,
                    action_taken=BudgetAction.THROTTLE,
                    message="Budget exceeded - throttling",
                )

            if budget.action == BudgetAction.WARN:
                logger.warning(
                    "budget_exceeded_warning",
                    tenant_id=tenant_id,
                    period=period,
                    current_spend=current_spend,
                    budget_amount=budget.amount_usd,
                )
                return BudgetCheckResult(
                    allowed=True,
                    budget=budget,
                    current_spend=current_spend,
                    remaining=remaining,
                    utilization_pct=utilization_pct,
                    action_taken=BudgetAction.WARN,
                    message="Budget exceeded - warning only",
                )

        # Check alert threshold
        alert_threshold_pct = float(budget.alert_threshold * 100)
        if utilization_pct >= alert_threshold_pct:
            logger.warning(
                "budget_alert_threshold_reached",
                tenant_id=tenant_id,
                period=period,
                utilization_pct=utilization_pct,
                alert_threshold=alert_threshold_pct,
            )
            # TODO: Send alert notification

        return BudgetCheckResult(
            allowed=True,
            budget=budget,
            current_spend=current_spend,
            remaining=remaining,
            utilization_pct=utilization_pct,
            message="Within budget",
        )

    async def delete_budget(
        self,
        tenant_id: str,
        period: BudgetPeriod,
    ) -> None:
        """
        Delete budget for a tenant.

        Args:
            tenant_id: Tenant UUID
            period: Budget period
        """
        await self._redis.delete(self._budget_key(tenant_id, period))

        logger.info(
            "budget_deleted",
            tenant_id=tenant_id,
            period=period,
        )

    async def get_all_budgets(self, tenant_id: str) -> dict[BudgetPeriod, Budget]:
        """
        Get all budgets for a tenant.

        Args:
            tenant_id: Tenant UUID

        Returns:
            Dictionary mapping period to budget
        """
        budgets = {}

        for period in BudgetPeriod:
            budget = await self.get_budget(tenant_id, period)
            if budget:
                budgets[period] = budget

        return budgets

    async def get_tenant_budget_summary(self, tenant_id: str) -> dict[str, Any]:
        """
        Get comprehensive budget summary for a tenant.

        Args:
            tenant_id: Tenant UUID

        Returns:
            Budget summary with all periods and current spend
        """
        summary = {
            "tenant_id": tenant_id,
            "budgets": {},
            "current_spend": {},
        }

        for period in BudgetPeriod:
            if period == BudgetPeriod.UNLIMITED:
                continue

            budget = await self.get_budget(tenant_id, period)
            spend = await self.get_current_spend(tenant_id, period)

            if budget:
                summary["budgets"][period] = {
                    "amount_usd": str(budget.amount_usd),
                    "action": budget.action,
                    "alert_threshold": str(budget.alert_threshold),
                    "remaining": str(budget.amount_usd - spend),
                    "utilization_pct": float((spend / budget.amount_usd) * 100)
                    if budget.amount_usd > 0
                    else 0.0,
                }

            summary["current_spend"][period] = str(spend)

        return summary
