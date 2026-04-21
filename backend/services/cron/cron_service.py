"""ButlerCronService — Phase 8b Hardening.

A production-grade, persistent scheduler for Butler. 
Aligns with OpenClaw's durable scheduler pattern:
- Persistent storage (Postgres)
- Distributed synchronization (Postgres table locks via APScheduler)
- SSRF Guarded Webhook Delivery
- Orchestrator Event Integration
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.redis import RedisJobStore
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.network import safe_request
from core.locks import LockManager
from domain.cron.models import ButlerCronJob, ButlerCronRun, CronJobStatus, CronDeliveryMode
from domain.orchestrator.contracts import OrchestratorServiceContract
from core.envelope import ButlerEnvelope

logger = structlog.get_logger(__name__)

_MAX_ACTIVE_JOBS_PER_ACCOUNT = 50


class ButlerCronService:
    """Manages persistent cron jobs for Butler accounts.
    
    Uses APScheduler with SQLAlchemyJobStore for durability.
    """

    def __init__(
        self, 
        redis_url: str,
        lock_manager: LockManager | None = None,
        orchestrator: OrchestratorServiceContract | None = None
    ) -> None:
        self._orchestrator = orchestrator
        self._lock_manager = lock_manager
        
        # Parse Redis URL for APScheduler (doesn't support URL param)
        parsed = urlparse(redis_url)
        jobstores = {
            'default': RedisJobStore(
                host=parsed.hostname or "localhost",
                port=parsed.port or 6379,
                password=parsed.password,
                db=int(parsed.path.lstrip("/") or 0) if parsed.path else 0,
            )
        }
        
        self.scheduler = AsyncIOScheduler(jobstores=jobstores)
        self._is_running = False

    async def start(self):
        """Start the scheduler."""
        if not self._is_running:
            self.scheduler.start()
            self._is_running = True
            logger.info("cron_service_started")

    async def shutdown(self):
        """Shutdown the scheduler."""
        if self._is_running:
            self.scheduler.shutdown()
            self._is_running = False
            logger.info("cron_service_shutdown")

    # ── Cron Lifecycle ─────────────────────────────────────────────────────────

    async def create_job(
        self, 
        db: AsyncSession,
        account_id: str,
        name: str,
        expression: str,
        delivery_mode: CronDeliveryMode,
        delivery_meta: dict[str, Any],
        description: str | None = None,
        timezone_str: str = "UTC"
    ) -> ButlerCronJob:
        """Create a new cron job, persist to DB, and schedule in APScheduler."""
        
        # 1. Enforce limits
        active_count_result = await db.execute(
            select(ButlerCronJob).where(
                ButlerCronJob.account_id == account_id,
                ButlerCronJob.status == CronJobStatus.ACTIVE
            )
        )
        if len(active_count_result.scalars().all()) >= _MAX_ACTIVE_JOBS_PER_ACCOUNT:
            raise ValueError(f"Max active jobs ({_MAX_ACTIVE_JOBS_PER_ACCOUNT}) reached for account.")

        # 2. Create DB record
        job_id = uuid.uuid4()
        new_job = ButlerCronJob(
            id=job_id,
            account_id=account_id,
            name=name,
            description=description,
            expression=expression,
            timezone=timezone_str,
            delivery_mode=delivery_mode,
            delivery_meta=delivery_meta,
            status=CronJobStatus.ACTIVE
        )
        db.add(new_job)
        await db.flush()

        # 3. Schedule in APScheduler
        self.scheduler.add_job(
            self._execute_job_task,
            trigger='cron',
            args=[str(job_id)],
            id=str(job_id),
            replace_existing=True,
            misfire_grace_time=60,
            **self._parse_expression(expression)
        )
        
        logger.info("cron_job_created", job_id=str(job_id), account_id=account_id)
        return new_job

    async def delete_job(self, db: AsyncSession, job_id: uuid.UUID) -> bool:
        """Remove job from DB and scheduler."""
        result = await db.execute(delete(ButlerCronJob).where(ButlerCronJob.id == job_id))
        if result.rowcount > 0:
            try:
                self.scheduler.remove_job(str(job_id))
            except:
                pass
            logger.info("cron_job_deleted", job_id=str(job_id))
            return True
        return False

    async def pause_job(self, db: AsyncSession, job_id: uuid.UUID) -> bool:
        """Pause a cron job."""
        await db.execute(
            update(ButlerCronJob)
            .where(ButlerCronJob.id == job_id)
            .values(status=CronJobStatus.PAUSED)
        )
        try:
            self.scheduler.pause_job(str(job_id))
        except:
            pass
        return True

    async def resume_job(self, db: AsyncSession, job_id: uuid.UUID) -> bool:
        """Resume a paused cron job."""
        await db.execute(
            update(ButlerCronJob)
            .where(ButlerCronJob.id == job_id)
            .values(status=CronJobStatus.ACTIVE)
        )
        try:
            self.scheduler.resume_job(str(job_id))
        except:
            pass
        return True

    # ── Internal Execution ─────────────────────────────────────────────────────

    async def _execute_job_task(self, job_id_str: str):
        """The actual task executed by APScheduler.
        
        Provides orchestration for the delivery (Webhook or Orchestrator).
        """
        job_id = uuid.UUID(job_id_str)
        
        # We need a fresh session for the background task
        # NOTE: In production, this should use a session factory
        from infrastructure.database import async_session_factory
        async with async_session_factory() as db:
            # 0. Acquire distributed lock for THIS specific run
            # Uses a unique key per run based on job_id and firing time bucket (minutely)
            # This handles cases where multiple nodes might "pick up" the same job.
            lock_key = f"cron:exec:{job_id_str}:{datetime.now().strftime('%Y%m%d%H%M')}"
            
            if self._lock_manager:
                async with self._lock_manager.lock(lock_key, ttl_s=120) as acquired:
                    if not acquired:
                        logger.debug("cron_job_already_executing_elsewhere", job_id=job_id_str)
                        return
                    await self._inner_execute(db, job_id)
            else:
                await self._inner_execute(db, job_id)

    async def _inner_execute(self, db: AsyncSession, job_id: uuid.UUID):
        """Inner execution logic after lock acquisition."""
        job = await db.get(ButlerCronJob, job_id)
        if not job or job.status != CronJobStatus.ACTIVE:
            return

        run = ButlerCronRun(job_id=job_id, status="executing")
        db.add(run)
        await db.commit()

        start_time = datetime.now(timezone.utc)
        success = False
        error_msg = None
        result_meta = {}

        try:
            if job.delivery_mode == CronDeliveryMode.WEBHOOK:
                success, result_meta = await self._deliver_webhook(job)
            elif job.delivery_mode == CronDeliveryMode.ORCHESTRATOR:
                success, result_meta = await self._deliver_orchestrator(job)
            else:
                raise ValueError(f"Unknown delivery mode: {job.delivery_mode}")

            success = True
        except Exception as e:
            logger.error("cron_execution_failed", job_id=str(job_id), error=str(e))
            success = False
            error_msg = str(e)

        run.status = "success" if success else "error"
        run.completed_at = datetime.now(timezone.utc)
        run.error_message = error_msg
        run.result_meta = result_meta

        job.last_run_at = start_time

        await db.commit()

    async def _deliver_webhook(self, job: ButlerCronJob) -> tuple[bool, dict]:
        """Delivery to an external webhook with SSRF protection."""
        url = job.delivery_meta.get("url")
        payload = job.delivery_meta.get("payload", {})
        
        if not url:
            raise ValueError("Webhook URL missing in delivery_meta")

        resp = await safe_request("POST", url, json={
            "job_name": job.name,
            "account_id": job.account_id,
            "fired_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload
        })
        
        return resp.is_success, {"status_code": resp.status_code}

    async def _deliver_orchestrator(self, job: ButlerCronJob) -> tuple[bool, dict]:
        """Injection into the Butler Orchestrator pipeline."""
        if not self._orchestrator:
            raise RuntimeError("Orchestrator not initialized in CronService")
            
        action = job.delivery_meta.get("action")
        payload = job.delivery_meta.get("payload", {})
        
        envelope = ButlerEnvelope(
            account_id=job.account_id,
            session_id=f"cron-{job.id}",
            message=f"Cron trigger: {action} with {json.dumps(payload)}",
            channel="cron"
        )
        
        result = await self._orchestrator.intake(envelope)
        return True, {"workflow_id": result.workflow_id}

    def _parse_expression(self, expression: str) -> dict[str, str]:
        """Parse 5-field crontab into APScheduler fields."""
        parts = expression.split()
        if len(parts) != 5:
            raise ValueError("Invalid cron expression: must be 5 fields")
            
        return {
            'minute': parts[0],
            'hour': parts[1],
            'day': parts[2],
            'month': parts[3],
            'day_of_week': parts[4]
        }
