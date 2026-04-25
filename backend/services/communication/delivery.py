"""Communication DeliveryService — v3.1 production.

Changes from v3.0:
  - _push_to_stream(): real redis.xadd with approximate MAXLEN trim
  - process_webhook_event(): idempotent state machine with monotonic progression

Stream design:
  key:    comm:stream:{priority_class}
  fields: message_id, channel, recipient, content, priority_class, enqueued_at_ns
  maxlen: ~10_000 (approximate trim — more efficient than exact under load)
  deadletter: comm:dlq:{priority_class} on xadd failure

Webhook state machine:
  - Dedupe by provider_event_id (Redis SET, 24h TTL)
  - Monotonic phase progression: ACCEPTED → DELIVERED → FAILED
  - Stale regressions (e.g. delivered → sent) are logged and discarded
  - Raw webhook payload stored to audit trail
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import structlog
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.communication import DeliveryPhase, DeliveryState, DeliveryStatus, SendRequest
from domain.communication.models import DeliveryRecord
from services.communication.idempotency import IdempotencyManager
from services.communication.policy import CommunicationPolicy

logger = structlog.get_logger(__name__)

# ── Phase ordering — lower int = earlier in lifecycle ─────────────────────────
_PHASE_ORDER: dict[str, int] = {
    DeliveryPhase.ACCEPTED: 0,
    DeliveryPhase.OUTBOUND: 1,
    DeliveryPhase.DELIVERED: 2,
    DeliveryPhase.READ: 3,
    DeliveryPhase.SUPPRESSED: 4,
    DeliveryPhase.COMPLAINT: 5,
    DeliveryPhase.FAILED: 99,  # terminal — always allowed
}

# Approximate stream cap — cheaper than exact under high write rate
_STREAM_MAXLEN = 10_000
_DLQ_TTL_S = 604_800  # 7-day DLQ retention
_WEBHOOK_DEDUP_TTL_S = 86_400  # 24h dedup window


class DeliveryService:
    """
    Core Communication Control Plane runtime.
    Orchestrates policy checks, idempotency locking, Redis stream push,
    and webhook routing.

    All dependencies are injected as plain typed args — no FastAPI Depends
    in the constructor. Wiring lives in core/deps.py.
    """

    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        policy: CommunicationPolicy,
        bg_tasks: Any = None,
    ) -> None:
        self.db = db
        self.redis = redis
        self.policy = policy
        self.idempotency = IdempotencyManager(redis)
        self.bg_tasks = bg_tasks

    async def enqueue_delivery(self, request: SendRequest) -> str:
        """Enqueues a message after enforcing all policies."""

        # 1. Policy governance
        policy_result = await self.policy.pre_send_check(request)
        if not policy_result.allowed:
            raise ValueError(f"Policy Blocked: {policy_result.reason}")

        # 2. Deterministic dedupe key
        idem_key_str = request.idempotency_key or self.idempotency.compute_idem_key(
            actor="butler_system",
            channel=request.channel,
            recipient=request.recipient,
            content=request.content,
            template_id=request.content.get("template_id"),
            media_ref=request.content.get("media_url"),
        )
        idem_key = f"idem:{idem_key_str}"

        # 3. Prevent replays/duplicates
        message_id = str(uuid.uuid4())
        acquired = await self.idempotency.try_acquire_lock(idem_key, message_id)
        if not acquired:
            existing_id = await self.idempotency.get_existing_message_id(idem_key)
            logger.info("delivery.idempotent_hit", existing_message_id=existing_id)
            return existing_id or "duplicate"

        # 4. Insert canonical Delivery Record
        record = DeliveryRecord(
            id=uuid.UUID(message_id),
            channel=request.channel,
            provider="pending_router",
            recipient=request.recipient,
            sender_profile_id=request.sender_profile_id,
            phase=DeliveryPhase.ACCEPTED,
            status=DeliveryStatus.QUEUED,
            metadata_json=request.metadata,
        )
        self.db.add(record)
        await self.db.commit()

        # 5. Push to prioritised Redis stream
        await self._push_to_stream(request.priority_class, message_id, request)

        return message_id

    async def _push_to_stream(
        self, priority_class: str, message_id: str, request: SendRequest
    ) -> None:
        """Append message to the priority-class Redis stream.

        Uses approximate MAXLEN trimming (~ flag) — more efficient under load
        than exact trimming because Redis can defer the cleanup.

        On failure: writes to dead-letter queue (comm:dlq:{priority_class}).
        """
        stream_key = f"comm:stream:{priority_class}"
        entry = {
            "message_id": message_id,
            "channel": request.channel,
            "recipient": request.recipient,
            "content": json.dumps(request.content),
            "priority_class": priority_class,
            "enqueued_at_ns": str(time.time_ns()),
        }
        try:
            await self.redis.xadd(
                stream_key,
                entry,
                maxlen=_STREAM_MAXLEN,
                approximate=True,  # MAXLEN ~ — efficient trim
            )
            logger.debug(
                "delivery.stream.enqueued",
                stream=stream_key,
                message_id=message_id,
            )
        except Exception as exc:
            # Dead-letter queue — never lose a message silently
            dlq_key = f"comm:dlq:{priority_class}"
            dlq_entry = {**entry, "xadd_error": str(exc)}
            try:
                await self.redis.xadd(dlq_key, dlq_entry, maxlen=1_000, approximate=True)
                await self.redis.expire(dlq_key, _DLQ_TTL_S)
            except Exception as dlq_exc:
                logger.error(
                    "delivery.stream.dlq_failed",
                    message_id=message_id,
                    stream_error=str(exc),
                    dlq_error=str(dlq_exc),
                )
            logger.error(
                "delivery.stream.enqueue_failed",
                message_id=message_id,
                stream=stream_key,
                error=str(exc),
            )

    async def get_delivery_state(self, message_id: str) -> DeliveryState | None:
        """Fetch the normalised state of a delivery."""
        record = await self.db.get(DeliveryRecord, uuid.UUID(message_id))
        if not record:
            return None

        return DeliveryState(
            message_id=str(record.id),
            channel=record.channel,
            provider=record.provider,
            phase=record.phase,
            status=record.status,
            terminal=record.terminal,
            retryable=record.retryable,
            provider_status_raw=record.provider_status_raw,
            provider_event_type=record.provider_event_type,
            provider_message_id=record.provider_message_id,
            first_provider_acceptance=record.first_provider_acceptance,
            final_delivery=record.final_delivery,
            retry_count=record.retry_count,
        )

    async def process_webhook_event(self, provider: str, payload: dict[str, Any]) -> None:
        """Process an incoming provider webhook — idempotent state machine.

        Guards:
          1. Provider event_id dedupe (Redis, 24h)
          2. Monotonic phase progression — no regressions allowed
          3. Raw payload audit trail appended to metadata_json
        """
        provider_event_id = payload.get("event_id") or payload.get("id") or payload.get("MessageId")
        provider_message_id = (
            payload.get("message_id") or payload.get("MessageSid") or payload.get("msg_id")
        )

        if not provider_message_id:
            logger.warning(
                "webhook.no_message_id",
                provider=provider,
                payload_keys=list(payload.keys()),
            )
            return

        # 1. Dedup by provider_event_id
        if provider_event_id:
            # Use tenant-scoped key if tenant_id is available
            tenant_id = getattr(self, 'tenant_id', None)
            if tenant_id:
                from services.tenant.namespace import get_tenant_namespace
                namespace = get_tenant_namespace(tenant_id)
                dedup_key = f"{namespace.prefix}:webhook:seen:{provider}:{provider_event_id}"
            else:
                # Fallback to legacy format for non-tenant contexts
                dedup_key = f"webhook:seen:{provider}:{provider_event_id}"
            already_seen = await self.redis.set(dedup_key, "1", nx=True, ex=_WEBHOOK_DEDUP_TTL_S)
            if not already_seen:
                logger.debug(
                    "webhook.duplicate_skipped",
                    provider=provider,
                    provider_event_id=provider_event_id,
                )
                return

        # 2. Locate the delivery record
        stmt = select(DeliveryRecord).where(
            DeliveryRecord.provider_message_id == provider_message_id
        )
        result = await self.db.execute(stmt)
        record: DeliveryRecord | None = result.scalar_one_or_none()

        if not record:
            logger.warning(
                "webhook.record_not_found",
                provider=provider,
                provider_message_id=provider_message_id,
            )
            return

        # 3. Normalise provider status → DeliveryPhase + DeliveryStatus
        new_phase, new_status = self._normalise_provider_status(provider, payload)

        # 4. Monotonic guard — discard stale regressions
        current_order = _PHASE_ORDER.get(record.phase, 0)
        incoming_order = _PHASE_ORDER.get(new_phase, 0)

        if incoming_order < current_order and new_phase != DeliveryPhase.FAILED:
            logger.info(
                "webhook.stale_regression_discarded",
                provider=provider,
                provider_message_id=provider_message_id,
                current_phase=record.phase,
                incoming_phase=new_phase,
            )
            return

        # 5. Apply state update
        record.phase = new_phase
        record.status = new_status
        record.provider_status_raw = payload.get("status") or payload.get("event_type", "")
        record.provider_event_type = payload.get("event_type", "")

        # 6. Audit: append raw payload reference to metadata
        meta = record.metadata_json or {}
        webhooks = meta.setdefault("webhook_events", [])
        webhooks.append(
            {
                "provider": provider,
                "event_id": provider_event_id,
                "event_type": payload.get("event_type"),
                "status": payload.get("status"),
                "ts": time.time(),
            }
        )
        record.metadata_json = meta

        await self.db.commit()
        logger.info(
            "webhook.state_updated",
            provider=provider,
            message_id=str(record.id),
            new_phase=new_phase,
            new_status=new_status,
        )

    def _normalise_provider_status(self, provider: str, payload: dict[str, Any]) -> tuple[str, str]:
        """Map provider-specific status string to (DeliveryPhase, DeliveryStatus).

        Extends with more providers as integrations are added.
        """
        raw_status = (payload.get("status") or payload.get("event_type") or "").lower()

        # Twilio / SendGrid / Mailgun common statuses
        _READ_STATUSES = {"opened", "read", "clicked"}
        _DELIVERED = {"delivered", "sent", "accepted"}
        _OUTBOUND = {"queued", "dispatched", "sending", "processed", "scheduled"}
        _SUPPRESSED = {"unsubscribed", "suppressed", "bounced", "dropped", "invalid"}
        _COMPLAINT = {"complained", "spam_report", "complaint"}
        _FAILED = {"failed", "undelivered", "rejected"}

        if raw_status in _READ_STATUSES:
            return DeliveryPhase.READ, DeliveryStatus.READ
        if raw_status in _DELIVERED:
            return DeliveryPhase.DELIVERED, DeliveryStatus.DELIVERED
        if raw_status in _OUTBOUND:
            return DeliveryPhase.OUTBOUND, DeliveryStatus.SENT
        if raw_status in _SUPPRESSED:
            return DeliveryPhase.SUPPRESSED, DeliveryStatus.SUPPRESSED
        if raw_status in _COMPLAINT:
            return DeliveryPhase.COMPLAINT, DeliveryStatus.COMPLAINT
        if raw_status in _FAILED:
            return DeliveryPhase.FAILED, DeliveryStatus.FAILED

        # Unknown provider status — treat as outbound
        return DeliveryPhase.OUTBOUND, DeliveryStatus.SENT
