"""
Alerting Service - Alert Management with Notification Channels

Implements alerting system with multiple notification channels.
Supports alert rules, notification routing, and alert history.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class AlertSeverity(StrEnum):
    """Alert severity level."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class NotificationChannel(StrEnum):
    """Notification channel."""

    EMAIL = "email"
    SLACK = "slack"
    PAGERDUTY = "pagerduty"
    WEBHOOK = "webhook"


@dataclass(frozen=True, slots=True)
class AlertRule:
    """Alert rule definition."""

    rule_id: str
    name: str
    metric_name: str
    condition: str  # e.g., "value > 100"
    severity: AlertSeverity
    enabled: bool
    notification_channels: list[NotificationChannel]
    cooldown_seconds: int


@dataclass(frozen=True, slots=True)
class Alert:
    """Alert instance."""

    alert_id: str
    rule_id: str
    severity: AlertSeverity
    message: str
    metric_name: str
    metric_value: float
    triggered_at: datetime
    tenant_id: str
    resolved: bool
    resolved_at: datetime | None


class AlertingService:
    """
    Alerting service for monitoring and notifications.

    Features:
    - Alert rule management
    - Multi-channel notifications
    - Alert history
    - Cooldown periods
    """

    def __init__(self) -> None:
        """Initialize alerting service."""
        self._rules: dict[str, AlertRule] = {}
        self._alerts: list[Alert] = []
        self._last_triggered: dict[str, datetime] = {}  # rule_id -> last triggered time
        self._notification_handlers: dict[
            NotificationChannel, Callable[[Alert], Awaitable[None]]
        ] = {}

    def create_rule(
        self,
        rule_id: str,
        name: str,
        metric_name: str,
        condition: str,
        severity: AlertSeverity,
        notification_channels: list[NotificationChannel],
        cooldown_seconds: int = 300,
    ) -> AlertRule:
        """
        Create an alert rule.

        Args:
            rule_id: Rule identifier
            name: Rule name
            metric_name: Metric to monitor
            condition: Alert condition
            severity: Alert severity
            notification_channels: Notification channels
            cooldown_seconds: Cooldown period

        Returns:
            Alert rule
        """
        rule = AlertRule(
            rule_id=rule_id,
            name=name,
            metric_name=metric_name,
            condition=condition,
            severity=severity,
            enabled=True,
            notification_channels=notification_channels,
            cooldown_seconds=cooldown_seconds,
        )

        self._rules[rule_id] = rule

        logger.info(
            "alert_rule_created",
            rule_id=rule_id,
            name=name,
            metric_name=metric_name,
        )

        return rule

    async def evaluate_metric(
        self,
        metric_name: str,
        value: float,
        tenant_id: str,
    ) -> list[Alert]:
        """
        Evaluate metric against alert rules.

        Args:
            metric_name: Metric name
            value: Metric value
            tenant_id: Tenant identifier

        Returns:
            List of triggered alerts
        """
        triggered_alerts = []

        for rule_id, rule in self._rules.items():
            if not rule.enabled:
                continue

            if rule.metric_name != metric_name:
                continue

            # Check cooldown
            last_triggered = self._last_triggered.get(rule_id)
            if last_triggered:
                cooldown_expired = (
                    datetime.now(UTC) - last_triggered
                ).total_seconds() >= rule.cooldown_seconds
                if not cooldown_expired:
                    continue

            # Evaluate condition (simplified)
            # In production, this would use a proper expression evaluator
            if self._evaluate_condition(rule.condition, value):
                alert = await self._trigger_alert(rule, value, tenant_id)
                triggered_alerts.append(alert)

        return triggered_alerts

    def _evaluate_condition(self, condition: str, value: float) -> bool:
        """
        Evaluate alert condition.

        Args:
            condition: Condition string
            value: Metric value

        Returns:
            True if condition met
        """
        # Simplified condition evaluation
        # In production, use a proper expression evaluator
        try:
            if ">" in condition:
                threshold = float(condition.split(">")[1].strip())
                return value > threshold
            if "<" in condition:
                threshold = float(condition.split("<")[1].strip())
                return value < threshold
            if "==" in condition:
                threshold = float(condition.split("==")[1].strip())
                return value == threshold
        except (ValueError, IndexError):
            return False

        return False

    async def _trigger_alert(
        self,
        rule: AlertRule,
        value: float,
        tenant_id: str,
    ) -> Alert:
        """
        Trigger an alert.

        Args:
            rule: Alert rule
            value: Metric value
            tenant_id: Tenant identifier

        Returns:
            Alert
        """
        alert_id = f"alert-{datetime.now(UTC).timestamp()}"

        alert = Alert(
            alert_id=alert_id,
            rule_id=rule.rule_id,
            severity=rule.severity,
            message=f"Alert: {rule.name} - {rule.metric_name} = {value}",
            metric_name=rule.metric_name,
            metric_value=value,
            triggered_at=datetime.now(UTC),
            tenant_id=tenant_id,
            resolved=False,
            resolved_at=None,
        )

        self._alerts.append(alert)
        self._last_triggered[rule.rule_id] = datetime.now(UTC)

        # Send notifications
        await self._send_notifications(alert, rule.notification_channels)

        logger.warning(
            "alert_triggered",
            alert_id=alert_id,
            rule_id=rule.rule_id,
            severity=rule.severity,
        )

        return alert

    async def _send_notifications(
        self,
        alert: Alert,
        channels: list[NotificationChannel],
    ) -> None:
        """
        Send notifications through channels.

        Args:
            alert: Alert
            channels: Notification channels
        """
        for channel in channels:
            handler = self._notification_handlers.get(channel)
            if handler:
                try:
                    await handler(alert)
                except Exception as e:
                    logger.error(
                        "notification_failed",
                        channel=channel,
                        alert_id=alert.alert_id,
                        error=str(e),
                    )

    def register_notification_handler(
        self,
        channel: NotificationChannel,
        handler: Callable[[Alert], Awaitable[None]],
    ) -> None:
        """
        Register a notification handler.

        Args:
            channel: Notification channel
            handler: Notification handler
        """
        self._notification_handlers[channel] = handler

        logger.info(
            "notification_handler_registered",
            channel=channel,
        )

    def resolve_alert(self, alert_id: str) -> bool:
        """
        Resolve an alert.

        Args:
            alert_id: Alert identifier

        Returns:
            True if resolved
        """
        for i, alert in enumerate(self._alerts):
            if alert.alert_id == alert_id and not alert.resolved:
                resolved_alert = Alert(
                    alert_id=alert.alert_id,
                    rule_id=alert.rule_id,
                    severity=alert.severity,
                    message=alert.message,
                    metric_name=alert.metric_name,
                    metric_value=alert.metric_value,
                    triggered_at=alert.triggered_at,
                    tenant_id=alert.tenant_id,
                    resolved=True,
                    resolved_at=datetime.now(UTC),
                )

                self._alerts[i] = resolved_alert

                logger.info(
                    "alert_resolved",
                    alert_id=alert_id,
                )

                return True
        return False

    def get_alerts(
        self,
        tenant_id: str | None = None,
        severity: AlertSeverity | None = None,
        resolved: bool | None = None,
        limit: int = 100,
    ) -> list[Alert]:
        """
        Get alerts with optional filters.

        Args:
            tenant_id: Filter by tenant
            severity: Filter by severity
            resolved: Filter by resolved status
            limit: Maximum number of alerts

        Returns:
            List of alerts
        """
        alerts = self._alerts

        if tenant_id:
            alerts = [a for a in alerts if a.tenant_id == tenant_id]

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        if resolved is not None:
            alerts = [a for a in alerts if a.resolved == resolved]

        return sorted(alerts, key=lambda a: a.triggered_at, reverse=True)[:limit]

    def get_rule(self, rule_id: str) -> AlertRule | None:
        """
        Get an alert rule.

        Args:
            rule_id: Rule identifier

        Returns:
            Alert rule or None
        """
        return self._rules.get(rule_id)

    def disable_rule(self, rule_id: str) -> bool:
        """
        Disable an alert rule.

        Args:
            rule_id: Rule identifier

        Returns:
            True if disabled
        """
        if rule_id in self._rules:
            rule = self._rules[rule_id]
            disabled_rule = AlertRule(
                rule_id=rule.rule_id,
                name=rule.name,
                metric_name=rule.metric_name,
                condition=rule.condition,
                severity=rule.severity,
                enabled=False,
                notification_channels=rule.notification_channels,
                cooldown_seconds=rule.cooldown_seconds,
            )

            self._rules[rule_id] = disabled_rule

            logger.info(
                "alert_rule_disabled",
                rule_id=rule_id,
            )

            return True
        return False

    def enable_rule(self, rule_id: str) -> bool:
        """
        Enable an alert rule.

        Args:
            rule_id: Rule identifier

        Returns:
            True if enabled
        """
        if rule_id in self._rules:
            rule = self._rules[rule_id]
            enabled_rule = AlertRule(
                rule_id=rule.rule_id,
                name=rule.name,
                metric_name=rule.metric_name,
                condition=rule.condition,
                severity=rule.severity,
                enabled=True,
                notification_channels=rule.notification_channels,
                cooldown_seconds=rule.cooldown_seconds,
            )

            self._rules[rule_id] = enabled_rule

            logger.info(
                "alert_rule_enabled",
                rule_id=rule_id,
            )

            return True
        return False

    def get_alerting_stats(self) -> dict[str, Any]:
        """
        Get alerting statistics.

        Returns:
            Alerting statistics
        """
        total_alerts = len(self._alerts)
        active_alerts = sum(1 for a in self._alerts if not a.resolved)

        severity_counts: dict[str, int] = {}
        for alert in self._alerts:
            severity_counts[alert.severity] = severity_counts.get(alert.severity, 0) + 1

        return {
            "total_rules": len(self._rules),
            "enabled_rules": sum(1 for r in self._rules.values() if r.enabled),
            "total_alerts": total_alerts,
            "active_alerts": active_alerts,
            "resolved_alerts": total_alerts - active_alerts,
            "severity_breakdown": severity_counts,
        }
