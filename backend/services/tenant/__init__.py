"""
Butler Tenant Security Platform

Single shared security substrate for multi-tenant SaaS operations.
Provides tenant context, resolution, namespace, entitlements, credentials,
quota, metering, audit, isolation, and cryptographic services.

All tenant operations must go through this platform. No provider-specific
tenant manager explosion. Civilization narrowly survives.
"""

from .audit import AuditEvent, AuditEventType, AuditSeverity, TenantAuditService
from .context import IsolationLevel, TenantContext
from .credentials import CredentialBroker
from .crypto import TenantCryptoService
from .entitlements import Entitlement, EntitlementPolicy, Plan, get_default_policy
from .isolation import (
    IsolationLevel as TenantIsolationLevel,
)
from .isolation import (
    IsolationPolicy,
    TenantIsolationService,
)
from .metering import (
    Provider,
    TenantMeteringService,
    UsageEvent,
)
from .metering import (
    ResourceType as MeteringResourceType,
)
from .namespace import TenantNamespace
from .quota import (
    DEFAULT_CONCURRENCY_LIMITS,
    DEFAULT_QUOTA_LIMITS,
    DEFAULT_RATE_LIMITS,
    ConcurrencyLimit,
    ConcurrencyLimitExceededError,
    QuotaExceededError,
    QuotaLimit,
    RateLimit,
    RateLimitExceededError,
    ResourceType,
    TenantQuotaService,
)
from .resolver import TenantResolver

__all__ = [
    "TenantContext",
    "IsolationLevel",
    "TenantNamespace",
    "TenantResolver",
    "Entitlement",
    "EntitlementPolicy",
    "Plan",
    "get_default_policy",
    "CredentialBroker",
    "ConcurrencyLimit",
    "ConcurrencyLimitExceededError",
    "DEFAULT_CONCURRENCY_LIMITS",
    "DEFAULT_QUOTA_LIMITS",
    "DEFAULT_RATE_LIMITS",
    "QuotaExceededError",
    "QuotaLimit",
    "RateLimit",
    "RateLimitExceededError",
    "ResourceType",
    "TenantQuotaService",
    "Provider",
    "MeteringResourceType",
    "UsageEvent",
    "TenantMeteringService",
    "AuditEvent",
    "AuditEventType",
    "AuditSeverity",
    "TenantAuditService",
    "TenantIsolationLevel",
    "IsolationPolicy",
    "TenantIsolationService",
    "TenantCryptoService",
]
