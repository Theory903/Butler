"""ButlerACPServer — Phase 8.

Action Confirmation Protocol (ACP) server.

ACP governs every tool call that requires human approval before Butler
can execute it. The protocol has three actors:
  1. Butler (producer)  — raises ApprovalRequired, creates an ACPRequest
  2. Human (approver)   — approves or denies via API/mobile/Slack/email
  3. Butler (consumer)  — receives decision, resumes or cancels workflow

ACP request lifecycle:
  PENDING → (approved | denied | timed_out | cancelled)

Persistence strategy (Phase 8):
  In-process dict (same process). Phase 8b: Postgres + Redis pub/sub for
  multi-node delivery of the approval decision to the waiting workflow.

Security rules:
  - ACPRequests are account-scoped. Only the issuing account can view them.
  - Approval decisions must include a human_id claim from the JWT.
  - ACP tokens (request_id) are UUIDs — opaque, unguessable, single-use.
  - Default TTL: 24h. After TTL the request auto-transitions to TIMED_OUT.
  - No retry: a denied or timed-out request cannot be re-approved.
    The workflow must be re-submitted.

Tool policy integration:
  ButlerToolPolicyGate.check() raises ApprovalRequired.
  HermesAgentBackend catches it and calls ACPServer.create_request().
  It then pauses the workflow segment and waits for ACPServer.await_decision().
  Once the human approves, RuntimeKernel.resume_after_approval() is called.

ACP is referenced in docs/02-services/orchestrator.md §ACP.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum


def _now() -> datetime:
    return datetime.now(UTC)


_DEFAULT_TTL_HOURS = 24


class ACPDecision(str, Enum):
    APPROVED   = "approved"
    DENIED     = "denied"
    TIMED_OUT  = "timed_out"
    CANCELLED  = "cancelled"


class ACPStatus(str, Enum):
    PENDING    = "pending"
    APPROVED   = "approved"
    DENIED     = "denied"
    TIMED_OUT  = "timed_out"
    CANCELLED  = "cancelled"


@dataclass
class ACPRequest:
    """A single approval request created when a tool requires human sign-off."""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    account_id: str = ""
    tool_name: str = ""
    approval_mode: str = "explicit"    # explicit | critical
    risk_tier: str = "L2"
    description: str = ""
    payload_summary: dict = field(default_factory=dict)  # Sanitised (no secrets)
    task_id: str = ""
    session_id: str = ""
    workflow_id: str | None = None
    status: ACPStatus = ACPStatus.PENDING
    created_at: datetime = field(default_factory=_now)
    expires_at: datetime = field(
        default_factory=lambda: _now() + timedelta(hours=_DEFAULT_TTL_HOURS)
    )
    decided_at: datetime | None = None
    decided_by: str | None = None      # human_id from JWT claim
    decision_note: str | None = None   # Optional reason from approver


@dataclass
class ACPDecisionResult:
    """Returned to the resuming workflow after a decision is made."""
    request_id: str
    decision: ACPDecision
    tool_name: str
    account_id: str
    decided_by: str | None
    decided_at: datetime


# ── ButlerACPServer ────────────────────────────────────────────────────────────

class ButlerACPServer:
    """In-process ACP request registry and decision broker.

    Usage pattern (non-blocking check):
        server = ButlerACPServer()
        req = server.create(account_id, "send_email", ...)
        # ... pause workflow, send notification to human ...
        decision = server.decide(req.request_id, ACPDecision.APPROVED, human_id)

    Usage pattern (async await — suspends until decision or timeout):
        decision = await server.await_decision(req.request_id, timeout_s=300)
    """

    def __init__(self, default_ttl_hours: int = _DEFAULT_TTL_HOURS) -> None:
        self._requests: dict[str, ACPRequest] = {}
        self._waiters: dict[str, asyncio.Future] = {}  # request_id → Future[ACPDecision]
        self._default_ttl_hours = default_ttl_hours

    # ── Create ────────────────────────────────────────────────────────────────

    def create(
        self,
        account_id: str,
        tool_name: str,
        approval_mode: str,
        risk_tier: str,
        description: str,
        task_id: str = "",
        session_id: str = "",
        workflow_id: str | None = None,
        payload_summary: dict | None = None,
        ttl_hours: int | None = None,
    ) -> ACPRequest:
        """Create and register a new ACP request."""
        ttl = ttl_hours if ttl_hours is not None else self._default_ttl_hours
        req = ACPRequest(
            account_id=account_id,
            tool_name=tool_name,
            approval_mode=approval_mode,
            risk_tier=risk_tier,
            description=description,
            task_id=task_id,
            session_id=session_id,
            workflow_id=workflow_id,
            payload_summary=payload_summary or {},
            expires_at=_now() + timedelta(hours=ttl),
        )
        self._requests[req.request_id] = req
        return req

    # ── Decide ────────────────────────────────────────────────────────────────

    def decide(
        self,
        request_id: str,
        decision: ACPDecision,
        human_id: str,
        note: str | None = None,
    ) -> ACPDecisionResult | None:
        """Record a human decision for a pending ACP request.

        Returns None if the request does not exist or is no longer PENDING.
        Resolves any waiter future for await_decision().
        """
        req = self._requests.get(request_id)
        if req is None:
            return None
        if req.status != ACPStatus.PENDING:
            return None  # Already decided or timed out
        if _now() > req.expires_at:
            req.status = ACPStatus.TIMED_OUT
            self._resolve_waiter(request_id, ACPDecision.TIMED_OUT)
            return None

        req.status = ACPStatus(decision.value)
        req.decided_at = _now()
        req.decided_by = human_id
        req.decision_note = note
        self._resolve_waiter(request_id, decision)

        return ACPDecisionResult(
            request_id=request_id,
            decision=decision,
            tool_name=req.tool_name,
            account_id=req.account_id,
            decided_by=human_id,
            decided_at=req.decided_at,
        )

    def cancel(self, request_id: str) -> bool:
        """Cancel a pending ACP request (workflow was abandoned)."""
        req = self._requests.get(request_id)
        if req is None or req.status != ACPStatus.PENDING:
            return False
        req.status = ACPStatus.CANCELLED
        req.decided_at = _now()
        self._resolve_waiter(request_id, ACPDecision.CANCELLED)
        return True

    # ── Async wait ────────────────────────────────────────────────────────────

    async def await_decision(
        self,
        request_id: str,
        timeout_s: float = 300.0,
    ) -> ACPDecision:
        """Suspend the calling coroutine until a decision is made or timeout.

        Returns the ACPDecision enum value.
        On timeout, marks the request as TIMED_OUT and returns TIMED_OUT.
        """
        req = self._requests.get(request_id)
        if req is None:
            return ACPDecision.TIMED_OUT
        if req.status != ACPStatus.PENDING:
            return ACPDecision(req.status.value)

        loop = asyncio.get_event_loop()
        fut: asyncio.Future[ACPDecision] = loop.create_future()
        self._waiters[request_id] = fut

        try:
            decision = await asyncio.wait_for(asyncio.shield(fut), timeout=timeout_s)
            return decision
        except asyncio.TimeoutError:
            req.status = ACPStatus.TIMED_OUT
            req.decided_at = _now()
            return ACPDecision.TIMED_OUT
        finally:
            self._waiters.pop(request_id, None)

    def _resolve_waiter(self, request_id: str, decision: ACPDecision) -> None:
        fut = self._waiters.get(request_id)
        if fut is not None and not fut.done():
            fut.set_result(decision)

    # ── Query ─────────────────────────────────────────────────────────────────

    def get(self, request_id: str) -> ACPRequest | None:
        return self._requests.get(request_id)

    def list_pending(self, account_id: str) -> list[ACPRequest]:
        now = _now()
        results = []
        for req in self._requests.values():
            if req.account_id != account_id or req.status != ACPStatus.PENDING:
                continue
            if now > req.expires_at:
                req.status = ACPStatus.TIMED_OUT  # Lazy expiry
                continue
            results.append(req)
        return sorted(results, key=lambda r: r.created_at)

    def list_all(self, account_id: str) -> list[ACPRequest]:
        return sorted(
            [r for r in self._requests.values() if r.account_id == account_id],
            key=lambda r: r.created_at,
        )

    def expire_stale(self) -> int:
        """Lazily expire timed-out requests. Returns number expired."""
        now = _now()
        count = 0
        for req in self._requests.values():
            if req.status == ACPStatus.PENDING and now > req.expires_at:
                req.status = ACPStatus.TIMED_OUT
                self._resolve_waiter(req.request_id, ACPDecision.TIMED_OUT)
                count += 1
        return count

    @property
    def pending_count(self) -> int:
        return sum(1 for r in self._requests.values() if r.status == ACPStatus.PENDING)

    @property
    def total_count(self) -> int:
        return len(self._requests)


# ── Singleton ──────────────────────────────────────────────────────────────────

_acp_server: ButlerACPServer | None = None


def get_acp_server() -> ButlerACPServer:
    global _acp_server  # noqa: PLW0603
    if _acp_server is None:
        _acp_server = ButlerACPServer()
    return _acp_server
