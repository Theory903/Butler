"""
Cost Alerts Service - Budget Monitoring and Alerting

Monitors tenant spend and sends alerts when thresholds are reached.
Implements auto-shutdown when budget is exceeded with shutdown action.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

import structlog
from redis.asyncio import Redis

from services.cost.budget_enforcement import (
    Budget,
    BudgetAction,
    BudgetEnforcementService,
    BudgetPeriod,
)
from services.tenant.namespace import get_tenant_namespace

logger = structlog.get_logger(__name__)


class AlertSeverity(StrEnum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertChannel(StrEnum):
    """Alert delivery channels."""

    EMAIL = "email"
    WEBHOOK = "webhook"
    SLACK = "slack"
    PAGERDUTY = "pagerduty"


@dataclass(frozen=True, slots=True)
class Alert:
    """Cost alert."""

    tenant_id: str
    severity: AlertSeverity
    message: str
    budget: Budget
    current_spend: Decimal
    utilization_pct: float
    timestamp: datetime
    channels: frozenset[AlertChannel]


@dataclass(frozen=True, slots=True)
class AlertConfig:
    """Alert configuration for a tenant."""

    tenant_id: str
    alert_threshold_pct: Decimal  # Alert at this % of budget
    critical_threshold_pct: Decimal  # Critical alert at this %
    emergency_threshold_pct: Decimal  # Emergency alert at this %
    channels: frozenset[AlertChannel]
    webhook_url: str | None = None
    email_recipients: frozenset[str] = frozenset()


class CostAlertsService:
    """
    Cost alerts service for budget monitoring.

    Monitors spend against budgets and sends alerts.
    Implements auto-shutdown when configured.
    """

    def __init__(
        self,
        redis: Redis,
        budget_service: BudgetEnforcementService,
    ) -> None:
        """Initialize cost alerts service."""
        self._redis = redis
        self._budget_service = budget_service
        self._alert_configs: dict[str, AlertConfig] = {}
        self._shutdown_list: set[str] = set()  # Tenants shutdown for budget

    def _alert_key(self, tenant_id: str) -> str:
        """Generate Redis key for alert configuration using TenantNamespace."""
        namespace = get_tenant_namespace(tenant_id)
        return f"{namespace.prefix}:alert_config"

    def _shutdown_key(self, tenant_id: str) -> str:
        """Generate Redis key for shutdown status using TenantNamespace."""
        namespace = get_tenant_namespace(tenant_id)
        return f"{namespace.prefix}:shutdown"

    def _alert_history_key(self, tenant_id: str) -> str:
        """Generate Redis key for alert history using TenantNamespace."""
        namespace = get_tenant_namespace(tenant_id)
        return f"{namespace.prefix}:alert_history"

    async def set_alert_config(
        self,
        tenant_id: str,
        alert_threshold_pct: Decimal = Decimal("0.8"),
        critical_threshold_pct: Decimal = Decimal("0.9"),
        emergency_threshold_pct: Decimal = Decimal("1.0"),
        channels: frozenset[AlertChannel] = frozenset([AlertChannel.EMAIL]),
        webhook_url: str | None = None,
        email_recipients: frozenset[str] = frozenset(),
    ) -> AlertConfig:
        """
        Set alert configuration for a tenant.

        Args:
            tenant_id: Tenant UUID
            alert_threshold_pct: Alert threshold percentage
            critical_threshold_pct: Critical threshold percentage
            emergency_threshold_pct: Emergency threshold percentage
            channels: Alert channels
            webhook_url: Webhook URL for alerts
            email_recipients: Email recipients

        Returns:
            Alert configuration
        """
        config = AlertConfig(
            tenant_id=tenant_id,
            alert_threshold_pct=alert_threshold_pct,
            critical_threshold_pct=critical_threshold_pct,
            emergency_threshold_pct=emergency_threshold_pct,
            channels=channels,
            webhook_url=webhook_url,
            email_recipients=email_recipients,
        )

        # Store in Redis
        config_data = {
            "alert_threshold_pct": str(alert_threshold_pct),
            "critical_threshold_pct": str(critical_threshold_pct),
            "emergency_threshold_pct": str(emergency_threshold_pct),
            "channels": ",".join(channels),
            "webhook_url": webhook_url or "",
            "email_recipients": ",".join(email_recipients),
        }

        await self._redis.hset(
            self._alert_key(tenant_id),
            mapping=config_data,
        )
        await self._redis.expire(self._alert_key(tenant_id), 86400 * 30)  # 30 days TTL

        self._alert_configs[tenant_id] = config

        logger.info(
            "alert_config_set",
            tenant_id=tenant_id,
            alert_threshold_pct=alert_threshold_pct,
            critical_threshold_pct=critical_threshold_pct,
            emergency_threshold_pct=emergency_threshold_pct,
        )

        return config

    async def get_alert_config(self, tenant_id: str) -> AlertConfig | None:
        """
        Get alert configuration for a tenant.

        Args:
            tenant_id: Tenant UUID

        Returns:
            Alert configuration if exists, None otherwise
        """
        # Check cache first
        if tenant_id in self._alert_configs:
            return self._alert_configs[tenant_id]

        # Load from Redis
        config_data = await self._redis.hgetall(self._alert_key(tenant_id))

        if not config_data:
            return None

        channels = frozenset(
            AlertChannel(c) for c in config_data.get(b"channels", b"").decode().split(",")
        )
        email_recipients = frozenset(config_data.get(b"email_recipients", b"").decode().split(","))

        config = AlertConfig(
            tenant_id=tenant_id,
            alert_threshold_pct=Decimal(config_data.get(b"alert_threshold_pct", b"0.8").decode()),
            critical_threshold_pct=Decimal(
                config_data.get(b"critical_threshold_pct", b"0.9").decode()
            ),
            emergency_threshold_pct=Decimal(
                config_data.get(b"emergency_threshold_pct", b"1.0").decode()
            ),
            channels=channels,
            webhook_url=config_data.get(b"webhook_url", b"").decode() or None,
            email_recipients=email_recipients,
        )

        self._alert_configs[tenant_id] = config
        return config

    async def check_and_alert(
        self,
        tenant_id: str,
        period: BudgetPeriod,
    ) -> Alert | None:
        """
        Check budget and send alert if threshold reached.

        Args:
            tenant_id: Tenant UUID
            period: Budget period to check

        Returns:
            Alert if sent, None otherwise
        """
        budget = await self._budget_service.get_budget(tenant_id, period)

        if not budget or budget.period == BudgetPeriod.UNLIMITED:
            return None

        current_spend = await self._budget_service.get_current_spend(tenant_id, period)
        utilization_pct = (
            float((current_spend / budget.amount_usd) * 100) if budget.amount_usd > 0 else 0.0
        )

        # Get alert config
        alert_config = await self.get_alert_config(tenant_id)
        if not alert_config:
            # Use default thresholds
            alert_config = AlertConfig(
                tenant_id=tenant_id,
                alert_threshold_pct=budget.alert_threshold,
                critical_threshold_pct=Decimal("0.9"),
                emergency_threshold_pct=Decimal("1.0"),
                channels=frozenset([AlertChannel.EMAIL]),
            )

        # Determine severity
        severity = None
        if utilization_pct >= float(alert_config.emergency_threshold_pct):
            severity = AlertSeverity.EMERGENCY
        elif utilization_pct >= float(alert_config.critical_threshold_pct):
            severity = AlertSeverity.CRITICAL
        elif utilization_pct >= float(alert_config.alert_threshold_pct):
            severity = AlertSeverity.WARNING

        if severity:
            alert = Alert(
                tenant_id=tenant_id,
                severity=severity,
                message=f"Budget utilization at {utilization_pct:.1f}% for {period} period",
                budget=budget,
                current_spend=current_spend,
                utilization_pct=utilization_pct,
                timestamp=datetime.now(UTC),
                channels=alert_config.channels,
            )

            await self._send_alert(alert, alert_config)

            # Handle emergency - shutdown if configured
            if severity == AlertSeverity.EMERGENCY and budget.action == BudgetAction.SHUTDOWN:
                await self._shutdown_tenant(tenant_id, budget)

            return alert

        return None

    async def _send_alert(
        self,
        alert: Alert,
        config: AlertConfig,
    ) -> None:
        """
        Send alert through configured channels.

        Args:
            alert: Alert to send
            config: Alert configuration
        """
        # Store in alert history
        await self._redis.lpush(
            self._alert_history_key(alert.tenant_id),
            alert.message,
        )
        await self._redis.ltrim(self._alert_history_key(alert.tenant_id), 0, 99)  # Keep last 100
        await self._redis.expire(self._alert_history_key(alert.tenant_id), 86400 * 30)

        # Send to configured channels
        for channel in alert.channels:
            if channel == AlertChannel.WEBHOOK and config.webhook_url:
                await self._send_webhook_alert(alert, config.webhook_url)
            elif channel == AlertChannel.EMAIL:
                await self._send_email_alert(alert, config.email_recipients)
            elif channel == AlertChannel.SLACK:
                await self._send_slack_alert(alert)
            elif channel == AlertChannel.PAGERDUTY:
                await self._send_pagerduty_alert(alert)

        logger.info(
            "alert_sent",
            tenant_id=alert.tenant_id,
            severity=alert.severity,
            channels=list(alert.channels),
            message=alert.message,
        )

    async def _send_webhook_alert(self, alert: Alert, webhook_url: str) -> None:
        """Send alert via webhook."""
        import aiohttp

        payload = {
            "tenant_id": alert.tenant_id,
            "severity": alert.severity,
            "message": alert.message,
            "current_spend": str(alert.current_spend),
            "budget_amount": str(alert.budget.amount_usd),
            "utilization_pct": alert.utilization_pct,
            "timestamp": alert.timestamp.isoformat(),
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    if response.status != 200:
                        logger.warning(
                            "webhook_alert_failed",
                            tenant_id=alert.tenant_id,
                            status=response.status,
                        )
        except Exception as e:
            logger.exception(
                "webhook_alert_error",
                tenant_id=alert.tenant_id,
                error=str(e),
            )

    async def _send_email_alert(self, alert: Alert, recipients: frozenset[str]) -> None:
        """Send alert via email."""
        # TODO: Implement email sending
        logger.info(
            "email_alert_queued",
            tenant_id=alert.tenant_id,
            recipients=list(recipients),
            message=alert.message,
        )

    async def _send_slack_alert(self, alert: Alert) -> None:
        """Send alert via Slack."""
        # TODO: Implement Slack integration
        logger.info(
            "slack_alert_queued",
            tenant_id=alert.tenant_id,
            message=alert.message,
        )

    async def _send_pagerduty_alert(self, alert: Alert) -> None:
        """Send alert via PagerDuty."""
        # TODO: Implement PagerDuty integration
        logger.info(
            "pagerduty_alert_queued",
            tenant_id=alert.tenant_id,
            message=alert.message,
        )

    async def _shutdown_tenant(self, tenant_id: str, budget: Budget) -> None:
        """
        Shutdown tenant access due to budget exceeded.

        Args:
            tenant_id: Tenant UUID
            budget: Budget that was exceeded
        """
        # Mark tenant as shutdown
        await self._redis.set(
            self._shutdown_key(tenant_id),
            "1",
            ex=86400,  # 24 hours TTL
        )

        self._shutdown_list.add(tenant_id)

        logger.error(
            "tenant_shutdown_for_budget",
            tenant_id=tenant_id,
            budget_amount=budget.amount_usd,
            period=budget.period,
            action=budget.action,
        )

        # TODO: Implement actual tenant shutdown
        # - Block new requests
        # - Stop running workflows
        # - Notify tenant

    async def is_tenant_shutdown(self, tenant_id: str) -> bool:
        """
        Check if tenant is shutdown for budget.

        Args:
            tenant_id: Tenant UUID

        Returns:
            True if shutdown, False otherwise
        """
        shutdown_status = await self._redis.get(self._shutdown_key(tenant_id))
        return shutdown_status is not None

    async def restore_tenant(self, tenant_id: str) -> None:
        """
        Restore tenant access after shutdown.

        Args:
            tenant_id: Tenant UUID
        """
        await self._redis.delete(self._shutdown_key(tenant_id))

        if tenant_id in self._shutdown_list:
            self._shutdown_list.remove(tenant_id)

        logger.info(
            "tenant_restored",
            tenant_id=tenant_id,
        )

    async def monitor_budgets(
        self,
        interval_seconds: int = 60,
    ) -> None:
        """
        Continuously monitor all tenant budgets.

        Args:
            interval_seconds: Monitoring interval
        """
        while True:
            try:
                # Get all tenants with budgets
                # TODO: Implement tenant discovery
                # For now, this is a placeholder

                await asyncio.sleep(interval_seconds)

            except Exception as e:
                logger.exception(
                    "budget_monitoring_error",
                    error=str(e),
                )
                await asyncio.sleep(interval_seconds)

    async def get_alert_history(
        self,
        tenant_id: str,
        limit: int = 10,
    ) -> list[str]:
        """
        Get alert history for a tenant.

        Args:
            tenant_id: Tenant UUID
            limit: Number of alerts to return

        Returns:
            List of alert messages
        """
        history = await self._redis.lrange(
            self._alert_history_key(tenant_id),
            0,
            limit - 1,
        )

        return [msg.decode() if isinstance(msg, bytes) else msg for msg in history]
