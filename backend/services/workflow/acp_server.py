"""ButlerACPServer — Phase 8b Hardened (Durable).

Action Confirmation Protocol (ACP) server. Aligns with Oracle-Grade reliability:
- Persistent storage (Postgres) via ApprovalRequest model.
- Redis Streams for durable signal delivery (replaces Pub/Sub).
- Multi-node scalability for long-running workflow suspension.
"""

from __future__ import annotations
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.orchestrator.models import ApprovalRequest, Task

logger = structlog.get_logger(__name__)

_DEFAULT_TTL_HOURS = 24

class ButlerACPServer:
    """Production-grade ACP server with persistent state and durable stream signals."""

    def __init__(self, redis: Redis, default_ttl_hours: int = _DEFAULT_TTL_HOURS) -> None:
        self._redis = redis
        self._default_ttl_hours = default_ttl_hours

    def _get_signal_stream(self, account_id: str) -> str:
        """Get the durable signal stream for an account."""
        return f"butler:wf:signals:account:{account_id}"

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
        """Create and register a new ACP request in DB and notify via Redis Streams."""
        ttl = ttl_hours if ttl_hours is not None else self._default_ttl_hours
        
        request_id = uuid.uuid4()
        req = ApprovalRequest(
            id=request_id,
            account_id=uuid.UUID(account_id),
            task_id=uuid.UUID(task_id),
            workflow_id=uuid.UUID(workflow_id),
            approval_type=approval_type,
            description=description,
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(hours=ttl),
        )
        db.add(req)
        await db.flush()

        # Notify active clients via Redis Streams (Durable Signal)
        stream_key = self._get_signal_stream(account_id)
        notify_payload = {
            "type": "approval_required",
            "request_id": str(request_id),
            "workflow_id": str(workflow_id),
            "tool_name": tool_name,
            "description": description,
            "created_at": req.created_at.isoformat()
        }
        await self._redis.xadd(stream_key, notify_payload, maxlen=10000, approximate=True)
        
        logger.info("acp_request_created", request_id=str(request_id), account_id=account_id)
        return req

    async def decide(
        self,
        db: AsyncSession,
        request_id: str,
        decision: str,  # approved | denied
        human_id: str,
        executor: Any = None  # DurableExecutor to resume task
    ) -> bool:
        """Record a human decision and broadcast it via durable Redis Stream."""
        uid = uuid.UUID(request_id)
        req = await db.get(ApprovalRequest, uid)
        
        if not req or req.status != "pending":
            return False

        if datetime.now(UTC) > req.expires_at:
            req.status = "expired"
            await db.commit()
            return False

        req.status = decision
        req.decided_at = datetime.now(UTC)
        req.decided_by = human_id
        
        # Broadcast decision to the account signal stream
        stream_key = self._get_signal_stream(str(req.account_id))
        decision_payload = {
            "type": "approval_decision",
            "request_id": request_id,
            "workflow_id": str(req.workflow_id),
            "decision": decision,
            "human_id": human_id,
            "ts": req.decided_at.isoformat()
        }
        await self._redis.xadd(stream_key, decision_payload, maxlen=10000, approximate=True)

        # If a DurableExecutor is provided, resume the task immediately if approved
        if executor and decision == "approved":
            task = await db.get(Task, req.task_id)
            if task:
                await executor.resume_task(task)

        logger.info("acp_decision_recorded", request_id=request_id, decision=decision)
        return True

    # Note: await_decision (Pub/Sub) removed. 
    # Workflows now resume by listening to the durable Redis Stream in WorkflowEngine.

    async def list_pending(self, db: AsyncSession, account_id: str) -> list[ApprovalRequest]:
        result = await db.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.account_id == uuid.UUID(account_id),
                ApprovalRequest.status == "pending",
                ApprovalRequest.expires_at > datetime.now(UTC)
            ).order_by(ApprovalRequest.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_request(self, db: AsyncSession, request_id: str) -> ApprovalRequest | None:
        return await db.get(ApprovalRequest, uuid.UUID(request_id))
