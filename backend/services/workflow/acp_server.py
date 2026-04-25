"""ButlerACPServer — durable approval coordination service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

import structlog
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.orchestrator.models import ApprovalRequest, Task

logger = structlog.get_logger(__name__)

_DEFAULT_TTL_HOURS = 24
ApprovalDecision = Literal["approved", "denied"]


class ResumableExecutor(Protocol):
    async def resume_task(self, task: Task) -> None:
        """Resume an approval-blocked task."""


class ButlerACPServer:
    """Durable ACP server using Postgres + Redis Streams."""

    def __init__(self, redis: Redis, default_ttl_hours: int = _DEFAULT_TTL_HOURS) -> None:
        self._redis = redis
        self._default_ttl_hours = default_ttl_hours

    def _get_signal_stream(self, account_id: str) -> str:
        """Return the durable signal stream key for an account."""
        return f"butler:wf:signals:account:{account_id}"

    def _validate_decision(self, decision: str) -> None:
        """Validate supported approval decisions."""
        if decision not in {"approved", "denied"}:
            raise ValueError(f"Unsupported approval decision: {decision!r}")

    async def create(
        self,
        db: AsyncSession,
        account_id: str,
        tool_name: str,
        description: str,
        task_id: str,
        workflow_id: str,
        approval_type: str = "tool",
        ttl_hours: int | None = None,
    ) -> ApprovalRequest:
        """Create an approval request and publish a durable approval-required signal."""
        ttl = ttl_hours if ttl_hours is not None else self._default_ttl_hours
        created_at = datetime.now(UTC)
        expires_at = created_at + timedelta(hours=ttl)

        req = ApprovalRequest(
            id=uuid.uuid4(),
            account_id=uuid.UUID(account_id),
            task_id=uuid.UUID(task_id),
            workflow_id=uuid.UUID(workflow_id),
            approval_type=approval_type,
            description=description,
            status="pending",
            expires_at=expires_at,
            created_at=created_at,
        )
        db.add(req)
        await db.commit()

        stream_key = self._get_signal_stream(account_id)
        notify_payload = {
            "type": "approval_required",
            "request_id": str(req.id),
            "workflow_id": workflow_id,
            "tool_name": tool_name,
            "description": description,
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        await self._redis.xadd(stream_key, notify_payload, maxlen=10000, approximate=True)

        logger.info(
            "acp_request_created",
            request_id=str(req.id),
            account_id=account_id,
            workflow_id=workflow_id,
            task_id=task_id,
            approval_type=approval_type,
        )
        return req

    async def decide(
        self,
        db: AsyncSession,
        request_id: str,
        decision: ApprovalDecision,
        human_id: str,
        executor: ResumableExecutor | None = None,
    ) -> bool:
        """Persist a human decision and publish a durable approval-decision signal."""
        self._validate_decision(decision)

        req = await db.get(ApprovalRequest, uuid.UUID(request_id))
        if req is None or req.status != "pending":
            return False

        now = datetime.now(UTC)
        if now > req.expires_at:
            req.status = "expired"
            req.decided_at = now
            req.decided_by = human_id
            await db.commit()
            logger.info(
                "acp_request_expired", request_id=request_id, account_id=str(req.account_id)
            )
            return False

        req.status = decision
        req.decided_at = now
        req.decided_by = human_id

        task: Task | None = None
        if decision == "approved" and executor is not None:
            task = await db.get(Task, req.task_id)

        await db.commit()

        stream_key = self._get_signal_stream(str(req.account_id))
        decision_payload = {
            "type": "approval_decision",
            "request_id": request_id,
            "workflow_id": str(req.workflow_id),
            "decision": decision,
            "human_id": human_id,
            "ts": now.isoformat(),
        }
        await self._redis.xadd(stream_key, decision_payload, maxlen=10000, approximate=True)

        if decision == "approved" and executor is not None and task is not None:
            await executor.resume_task(task)

        logger.info(
            "acp_decision_recorded",
            request_id=request_id,
            decision=decision,
            account_id=str(req.account_id),
            workflow_id=str(req.workflow_id),
        )
        return True

    async def list_pending(self, db: AsyncSession, account_id: str) -> list[ApprovalRequest]:
        """Return all non-expired pending approval requests for the account."""
        result = await db.execute(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.account_id == uuid.UUID(account_id),
                ApprovalRequest.status == "pending",
                ApprovalRequest.expires_at > datetime.now(UTC),
            )
            .order_by(ApprovalRequest.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_request(self, db: AsyncSession, request_id: str) -> ApprovalRequest | None:
        """Return a single approval request by ID."""
        return await db.get(ApprovalRequest, uuid.UUID(request_id))
