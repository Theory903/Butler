"""
Tenant Context - Canonical Tenant Identity

Immutable frozen dataclass representing tenant identity and context.
Created only by TenantResolver. Passed to all services. Never reconstructed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class IsolationLevel(StrEnum):
    """Tenant isolation level for SaaS deployment."""

    SHARED = "shared"
    DEDICATED_WORKER = "dedicated_worker"
    DEDICATED_VPC = "dedicated_vpc"


@dataclass(frozen=True, slots=True)
class TenantContext:
    """
    Immutable canonical tenant context.

    Created only by TenantResolver from validated JWT/session.
    Passed to providers, tools, memory, search, storage, and billing.
    Never reconstructed inside downstream services.
    Never accepted directly from client payload.

    Attributes:
        tenant_id: UUID as string - primary isolation key
        account_id: UUID as string for billing account
        user_id: UUID as string for requesting user
        plan: subscription plan (free, pro, operator, enterprise)
        region: deployment region
        isolation_level: isolation level enum
        request_id: unique request identifier
        session_id: session identifier
        actor_type: type of actor (user, system, api_key)
        scopes: frozenset of granted scopes
        metadata: additional tenant metadata
        tenant_slug: display-only string (e.g., "acme-corp")
        org_id: UUID as string or None for organization
    """

    tenant_id: str  # UUID as string
    account_id: str  # UUID as string
    user_id: str  # UUID as string
    plan: str
    region: str
    isolation_level: IsolationLevel
    request_id: str
    session_id: str
    actor_type: str
    scopes: frozenset[str]
    metadata: Mapping[str, str]
    tenant_slug: str | None = None  # display only
    org_id: str | None = None  # UUID as string
