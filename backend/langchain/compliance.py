"""Butler Compliance & Privacy for LangChain Agents.

Provides compliance checking, privacy controls, and audit logging.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ComplianceLevel(str, Enum):
    """Compliance levels."""

    NONE = "none"
    BASIC = "basic"
    STANDARD = "standard"
    STRICT = "strict"


class PrivacyLevel(str, Enum):
    """Privacy levels."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class ComplianceCheck(str, Enum):
    """Compliance check types."""

    PII_DETECTION = "pii_detection"
    DATA_RETENTION = "data_retention"
    ACCESS_CONTROL = "access_control"
    AUDIT_LOGGING = "audit_logging"
    ENCRYPTION = "encryption"


@dataclass
class ComplianceRule:
    """A compliance rule definition."""

    rule_id: str
    rule_type: ComplianceCheck
    description: str = ""
    severity: str = "error"  # "error", "warning", "info"
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditLogEntry:
    """An audit log entry."""

    entry_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str = ""
    account_id: str = ""
    session_id: str = ""
    user_id: str = ""
    action: str = ""
    resource: str = ""
    outcome: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class ButlerComplianceChecker:
    """Compliance checker for agent operations.

    This checker:
    - Validates compliance with rules
    - Checks for PII
    - Enforces data retention policies
    - Provides compliance reports
    """

    def __init__(self, compliance_level: ComplianceLevel = ComplianceLevel.STANDARD):
        """Initialize the compliance checker.

        Args:
            compliance_level: Compliance level
        """
        self._compliance_level = compliance_level
        self._rules: dict[str, ComplianceRule] = {}
        self._load_default_rules()

    def _load_default_rules(self) -> None:
        """Load default compliance rules."""
        # PII detection rule
        self._rules["pii_detection"] = ComplianceRule(
            rule_id="pii_detection",
            rule_type=ComplianceCheck.PII_DETECTION,
            description="Detect and flag personally identifiable information",
            severity="warning",
            enabled=True,
        )

        # Data retention rule
        self._rules["data_retention"] = ComplianceRule(
            rule_id="data_retention",
            rule_type=ComplianceCheck.DATA_RETENTION,
            description="Enforce data retention policies",
            severity="error",
            enabled=True,
        )

        # Access control rule
        self._rules["access_control"] = ComplianceRule(
            rule_id="access_control",
            rule_type=ComplianceCheck.ACCESS_CONTROL,
            description="Validate access permissions",
            severity="error",
            enabled=True,
        )

        # Audit logging rule
        self._rules["audit_logging"] = ComplianceRule(
            rule_id="audit_logging",
            rule_type=ComplianceCheck.AUDIT_LOGGING,
            description="Ensure audit logging is enabled",
            severity="warning",
            enabled=True,
        )

        logger.info("compliance_rules_loaded", count=len(self._rules))

    def add_rule(self, rule: ComplianceRule) -> None:
        """Add a compliance rule.

        Args:
            rule: Compliance rule
        """
        self._rules[rule.rule_id] = rule
        logger.info("compliance_rule_added", rule_id=rule.rule_id)

    def check_compliance(
        self,
        data: str | dict[str, Any],
        rules: list[ComplianceCheck] | None = None,
    ) -> dict[str, Any]:
        """Check compliance for data.

        Args:
            data: Data to check
            rules: Optional list of rules to check

        Returns:
            Compliance check result
        """
        results = {
            "compliant": True,
            "violations": [],
            "warnings": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        rules_to_check = rules or [r.rule_type for r in self._rules.values() if r.enabled]

        for rule_type in rules_to_check:
            rule = self._rules.get(rule_type.value)
            if not rule:
                continue

            violation = self._check_rule(rule, data)
            if violation:
                results["compliant"] = False
                if rule.severity == "error":
                    results["violations"].append(violation)
                else:
                    results["warnings"].append(violation)

        logger.info("compliance_check_completed", compliant=results["compliant"])
        return results

    def _check_rule(self, rule: ComplianceRule, data: str | dict[str, Any]) -> dict[str, Any] | None:
        """Check a specific rule.

        Args:
            rule: Compliance rule
            data: Data to check

        Returns:
            Violation details or None
        """
        if rule.rule_type == ComplianceCheck.PII_DETECTION:
            return self._check_pii(data)
        elif rule.rule_type == ComplianceCheck.DATA_RETENTION:
            return self._check_data_retention(data)
        elif rule.rule_type == ComplianceCheck.ACCESS_CONTROL:
            return self._check_access_control(data)
        elif rule.rule_type == ComplianceCheck.AUDIT_LOGGING:
            return self._check_audit_logging(data)
        return None

    def _check_pii(self, data: str | dict[str, Any]) -> dict[str, Any] | None:
        """Check for PII in data.

        Args:
            data: Data to check

        Returns:
            Violation details or None
        """
        data_str = str(data) if isinstance(data, dict) else data

        # Simple PII patterns
        pii_patterns = {
            "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            "phone": r"\d{3}-\d{3}-\d{4}",
            "ssn": r"\d{3}-\d{2}-\d{4}",
            "credit_card": r"\d{4}-\d{4}-\d{4}-\d{4}",
        }

        import re
        for pii_type, pattern in pii_patterns.items():
            if re.search(pattern, data_str):
                return {
                    "rule_id": "pii_detection",
                    "rule_type": "pii_detection",
                    "severity": "warning",
                    "message": f"Potential {pii_type} detected",
                }

        return None

    def _check_data_retention(self, data: str | dict[str, Any]) -> dict[str, Any] | None:
        """Check data retention compliance.

        Args:
            data: Data to check

        Returns:
            Violation details or None
        """
        # In production, this would check against retention policies
        return None

    def _check_access_control(self, data: str | dict[str, Any]) -> dict[str, Any] | None:
        """Check access control compliance.

        Args:
            data: Data to check

        Returns:
            Violation details or None
        """
        # In production, this would validate access permissions
        return None

    def _check_audit_logging(self, data: str | dict[str, Any]) -> dict[str, Any] | None:
        """Check audit logging compliance.

        Args:
            data: Data to check

        Returns:
            Violation details or None
        """
        # In production, this would check if audit logging is enabled
        return None

    def get_compliance_report(self) -> dict[str, Any]:
        """Get compliance report.

        Returns:
            Compliance report
        """
        return {
            "compliance_level": self._compliance_level.value,
            "rules_count": len(self._rules),
            "enabled_rules": len([r for r in self._rules.values() if r.enabled]),
            "rule_types": [r.rule_type.value for r in self._rules.values()],
        }


class ButlerPrivacyController:
    """Privacy controller for agent operations.

    This controller:
    - Manages privacy levels
    - Controls data access
    - Implements privacy policies
    - Provides privacy reports
    """

    def __init__(self, default_level: PrivacyLevel = PrivacyLevel.INTERNAL):
        """Initialize the privacy controller.

        Args:
            default_level: Default privacy level
        """
        self._default_level = default_level
        self._data_privacy: dict[str, PrivacyLevel] = {}

    def set_privacy_level(self, data_id: str, level: PrivacyLevel) -> None:
        """Set privacy level for data.

        Args:
            data_id: Data identifier
            level: Privacy level
        """
        self._data_privacy[data_id] = level
        logger.info("privacy_level_set", data_id=data_id, level=level.value)

    def get_privacy_level(self, data_id: str) -> PrivacyLevel:
        """Get privacy level for data.

        Args:
            data_id: Data identifier

        Returns:
            Privacy level
        """
        return self._data_privacy.get(data_id, self._default_level)

    def check_access(
        self,
        data_id: str,
        requested_level: PrivacyLevel,
    ) -> bool:
        """Check if access is allowed.

        Args:
            data_id: Data identifier
            requested_level: Requested privacy level

        Returns:
            True if access allowed
        """
        data_level = self.get_privacy_level(data_id)

        # Define level hierarchy (lower number = less restrictive)
        level_hierarchy = {
            PrivacyLevel.PUBLIC: 0,
            PrivacyLevel.INTERNAL: 1,
            PrivacyLevel.CONFIDENTIAL: 2,
            PrivacyLevel.RESTRICTED: 3,
        }

        return level_hierarchy.get(requested_level, 99) >= level_hierarchy.get(data_level, 0)

    def mask_data(self, data: str, level: PrivacyLevel) -> str:
        """Mask data based on privacy level.

        Args:
            data: Data to mask
            level: Privacy level

        Returns:
            Masked data
        """
        if level == PrivacyLevel.PUBLIC:
            return data
        elif level == PrivacyLevel.INTERNAL:
            return "[INTERNAL DATA]"
        elif level == PrivacyLevel.CONFIDENTIAL:
            return "[CONFIDENTIAL DATA]"
        elif level == PrivacyLevel.RESTRICTED:
            return "[RESTRICTED DATA]"

        return data

    def get_privacy_report(self) -> dict[str, Any]:
        """Get privacy report.

        Returns:
            Privacy report
        """
        level_counts = {}
        for level in self._data_privacy.values():
            level_counts[level.value] = level_counts.get(level.value, 0) + 1

        return {
            "default_level": self._default_level.value,
            "data_count": len(self._data_privacy),
            "level_distribution": level_counts,
        }


class ButlerAuditLogger:
    """Audit logger for compliance tracking.

    This logger:
    - Logs audit events
    - Maintains audit trail
    - Supports log export
    - Provides log queries
    """

    def __init__(self):
        """Initialize the audit logger."""
        self._logs: list[AuditLogEntry] = []

    def log_event(
        self,
        event_type: str,
        account_id: str = "",
        session_id: str = "",
        user_id: str = "",
        action: str = "",
        resource: str = "",
        outcome: str = "",
        details: dict[str, Any] | None = None,
    ) -> str:
        """Log an audit event.

        Args:
            event_type: Event type
            account_id: Account ID
            session_id: Session ID
            user_id: User ID
            action: Action performed
            resource: Resource affected
            outcome: Event outcome
            details: Additional details

        Returns:
            Entry ID
        """
        import uuid
        entry_id = str(uuid.uuid4())

        entry = AuditLogEntry(
            entry_id=entry_id,
            event_type=event_type,
            account_id=account_id,
            session_id=session_id,
            user_id=user_id,
            action=action,
            resource=resource,
            outcome=outcome,
            details=details or {},
        )

        self._logs.append(entry)
        logger.info("audit_event_logged", entry_id=entry_id, event_type=event_type)
        return entry_id

    def get_logs(
        self,
        account_id: str | None = None,
        session_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[AuditLogEntry]:
        """Get audit logs with filters.

        Args:
            account_id: Optional account filter
            session_id: Optional session filter
            event_type: Optional event type filter
            limit: Result limit

        Returns:
            List of audit log entries
        """
        logs = self._logs

        if account_id:
            logs = [l for l in logs if l.account_id == account_id]
        if session_id:
            logs = [l for l in logs if l.session_id == session_id]
        if event_type:
            logs = [l for l in logs if l.event_type == event_type]

        return logs[-limit:] if limit else logs

    def export_logs(self, format: str = "json") -> str | list[dict[str, Any]]:
        """Export audit logs.

        Args:
            format: Export format

        Returns:
            Exported logs
        """
        if format == "json":
            import json
            return json.dumps([self._entry_to_dict(l) for l in self._logs], indent=2)
        else:
            return [self._entry_to_dict(l) for l in self._logs]

    def _entry_to_dict(self, entry: AuditLogEntry) -> dict[str, Any]:
        """Convert entry to dictionary.

        Args:
            entry: Audit log entry

        Returns:
            Dictionary representation
        """
        return {
            "entry_id": entry.entry_id,
            "timestamp": entry.timestamp.isoformat(),
            "event_type": entry.event_type,
            "account_id": entry.account_id,
            "session_id": entry.session_id,
            "user_id": entry.user_id,
            "action": entry.action,
            "resource": entry.resource,
            "outcome": entry.outcome,
            "details": entry.details,
        }

    def clear_logs(self) -> None:
        """Clear all audit logs."""
        self._logs.clear()
        logger.info("audit_logs_cleared")


class ButlerCompliancePrivacy:
    """Combined compliance and privacy system.

    This system:
    - Combines compliance checking
    - Integrates privacy controls
    - Provides audit logging
    - Offers unified reporting
    """

    def __init__(
        self,
        compliance_level: ComplianceLevel = ComplianceLevel.STANDARD,
        privacy_level: PrivacyLevel = PrivacyLevel.INTERNAL,
    ):
        """Initialize the compliance and privacy system.

        Args:
            compliance_level: Default compliance level
            privacy_level: Default privacy level
        """
        self._compliance = ButlerComplianceChecker(compliance_level)
        self._privacy = ButlerPrivacyController(privacy_level)
        self._audit = ButlerAuditLogger()

    @property
    def compliance(self) -> ButlerComplianceChecker:
        """Get the compliance checker."""
        return self._compliance

    @property
    def privacy(self) -> ButlerPrivacyController:
        """Get the privacy controller."""
        return self._privacy

    @property
    def audit(self) -> ButlerAuditLogger:
        """Get the audit logger."""
        return self._audit

    def check_and_log(
        self,
        data: str | dict[str, Any],
        account_id: str = "",
        session_id: str = "",
        user_id: str = "",
    ) -> dict[str, Any]:
        """Check compliance and log the result.

        Args:
            data: Data to check
            account_id: Account ID
            session_id: Session ID
            user_id: User ID

        Returns:
            Combined result
        """
        compliance_result = self._compliance.check_compliance(data)

        self._audit.log_event(
            event_type="compliance_check",
            account_id=account_id,
            session_id=session_id,
            user_id=user_id,
            action="compliance_check",
            outcome="compliant" if compliance_result["compliant"] else "non_compliant",
            details=compliance_result,
        )

        return compliance_result

    def get_system_report(self) -> dict[str, Any]:
        """Get system compliance and privacy report.

        Returns:
            System report
        """
        return {
            "compliance": self._compliance.get_compliance_report(),
            "privacy": self._privacy.get_privacy_report(),
            "audit": {
                "total_logs": len(self._audit._logs),
                "recent_logs": len(self._audit.get_logs(limit=10)),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def export_all(self) -> dict[str, Any]:
        """Export all compliance and privacy data.

        Returns:
            Exported data
        """
        return {
            "compliance_rules": [
                {
                    "rule_id": r.rule_id,
                    "rule_type": r.rule_type.value,
                    "description": r.description,
                    "enabled": r.enabled,
                }
                for r in self._compliance._rules.values()
            ],
            "privacy_levels": {k: v.value for k, v in self._privacy._data_privacy.items()},
            "audit_logs": self._audit.export_logs(format="dict"),
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
        }
