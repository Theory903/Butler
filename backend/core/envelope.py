"""Canonical Butler request envelope.

Every inbound request is normalized into this envelope by the Gateway
before dispatching to the Orchestrator. This ensures multi-device
continuity and trace propagation across all execution layers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class ButlerEnvelope(BaseModel):
    """Canonical request envelope — the contract between Gateway and Orchestrator.

    The Gateway builds this. The Orchestrator consumes it.
    No service downstream should read raw HTTP requests.
    """

    # Identity & routing
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    account_id: str
    session_id: str
    device_id: Optional[str] = None

    # Channel context
    channel: str = "api"  # mobile | web | watch | voice | api

    # Timing & tracing
    # ...
    # Payload
    message: str = ""
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    mode: str = "auto"
    model: Optional[str] = None  # e.g. "cloud-deepseek"

    # Context hints (from client)
    location: Optional[dict[str, Any]] = None
    client_version: Optional[str] = None

    # Gateway-set fields (not client-controlled)
    assurance_level: str = "aal1"  # aal1 | aal2 | aal3
    idempotency_key: Optional[str] = None
    rate_limit_remaining: Optional[int] = None

    model_config = {"extra": "ignore"}


class OrchestratorResult(BaseModel):
    """Result returned by Orchestrator back to Gateway."""

    workflow_id: str
    content: str
    actions: list[dict[str, Any]] = Field(default_factory=list)
    requires_approval: bool = False
    approval_id: Optional[str] = None
    session_id: str = ""
    request_id: str = ""
