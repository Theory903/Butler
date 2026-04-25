"""Tenant-aware structured logging with tenant hashing."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import structlog


def hash_tenant_id(tenant_id: str) -> str:
    """Hash tenant_id for logging to avoid PII in logs."""
    if tenant_id is None:
        return "none"
    return hashlib.sha256(tenant_id.encode()).hexdigest()[:8]


def hash_account_id(account_id: str) -> str:
    """Hash account_id for logging to avoid PII in logs."""
    if account_id is None:
        return "none"
    return hashlib.sha256(account_id.encode()).hexdigest()[:8]


class TenantAwareLogger:
    """Tenant-aware logger that hashes tenant/account IDs in logs.

    Rule: Never log raw tenant_id or account_id in production logs.
    """

    def __init__(self, logger_name: str) -> None:
        self.logger = structlog.get_logger(logger_name)

    def _sanitize_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """Sanitize context by hashing tenant/account IDs."""
        sanitized = context.copy()
        if "tenant_id" in sanitized:
            sanitized["tenant_hash"] = hash_tenant_id(sanitized["tenant_id"])
            del sanitized["tenant_id"]
        if "account_id" in sanitized:
            sanitized["account_hash"] = hash_account_id(sanitized["account_id"])
            del sanitized["account_id"]
        return sanitized

    def info(self, msg: str, **kwargs: Any) -> None:
        """Log info message with tenant hashing."""
        sanitized = self._sanitize_context(kwargs)
        self.logger.info(msg, **sanitized)

    def warning(self, msg: str, **kwargs: Any) -> None:
        """Log warning message with tenant hashing."""
        sanitized = self._sanitize_context(kwargs)
        self.logger.warning(msg, **sanitized)

    def error(self, msg: str, **kwargs: Any) -> None:
        """Log error message with tenant hashing."""
        sanitized = self._sanitize_context(kwargs)
        self.logger.error(msg, **sanitized)

    def debug(self, msg: str, **kwargs: Any) -> None:
        """Log debug message with tenant hashing."""
        sanitized = self._sanitize_context(kwargs)
        self.logger.debug(msg, **sanitized)

    def exception(self, msg: str, **kwargs: Any) -> None:
        """Log exception message with tenant hashing."""
        sanitized = self._sanitize_context(kwargs)
        self.logger.exception(msg, **sanitized)


def get_tenant_aware_logger(logger_name: str) -> TenantAwareLogger:
    """Factory function to get a tenant-aware logger."""
    return TenantAwareLogger(logger_name)
