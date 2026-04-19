"""ButlerCronService — Phase 8.

Schedules and manages time-based trigger jobs for Butler.
A cron job is an account-scoped recurring action that fires
a ButlerEvent into the Orchestrator at the scheduled time.

Architecture:
  CronJob (DB record)
    ↓  APScheduler in-process (or Celery beat in Phase 8b for multi-node)
  ButlerCronService.trigger()
    ↓
  OrchestratorService.handle_cron_trigger()
    ↓
  Normal execution pipeline (RuntimeKernel → tools → memory → realtime)

Why in-process APScheduler (Phase 8):
  - Simpler deployment, no extra infra
  - All cron state in Postgres (CronJob table)
  - Deterministic restart: jobs reload from DB on startup
  - Phase 8b migrates to a distributed scheduler if needed (Celery beat,
    Temporal cron workflows, or a dedicated Temporal CronJob)

Sovereignty rules:
  - Cron jobs fire Butler canonical events (ButlerEvent), not Hermes calls
  - Account ID is always in scope — no cross-account triggers
  - TTL: jobs older than 3 years auto-expire; max 50 active jobs per account
  - Pause/resume/delete are the only mutations allowed from tool layer
  - CronService never writes to Memory — memory is Orchestrator's concern

Cron expression format: crontab (5 fields only, no seconds).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


def _now() -> datetime:
    return datetime.now(UTC)


class CronJobStatus(str, Enum):
    ACTIVE    = "active"
    PAUSED    = "paused"
    EXPIRED   = "expired"
    EXECUTING = "executing"   # Locked during execution to prevent double-fire
    FAILED    = "failed"


@dataclass
class CronJob:
    """In-memory representation of a scheduled cron job.

    In Phase 8b this maps 1:1 to a Postgres `cron_jobs` table row.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    account_id: str = ""
    name: str = ""
    description: str = ""
    cron_expression: str = ""     # e.g. "0 9 * * 1-5"  (Mon-Fri 9am)
    timezone: str = "UTC"
    action: str = ""              # Tool name or skill ID to invoke
    payload: dict = field(default_factory=dict)  # Parameters passed to action
    status: CronJobStatus = CronJobStatus.ACTIVE
    created_at: datetime = field(default_factory=_now)
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    run_count: int = 0
    max_runs: int = -1            # -1 = unlimited
    expires_at: datetime | None = None
    error_streak: int = 0         # Consecutive failures; auto-pause at 5


@dataclass
class CronTriggerResult:
    """Result of a cron job trigger attempt."""
    job_id: str
    account_id: str
    action: str
    triggered_at: datetime
    success: bool
    error: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class CreateCronJobRequest:
    account_id: str
    name: str
    cron_expression: str
    action: str
    payload: dict = field(default_factory=dict)
    timezone: str = "UTC"
    description: str = ""
    max_runs: int = -1
    expires_at: datetime | None = None


# ── Schedule validation ────────────────────────────────────────────────────────

_CRON_FIELDS_COUNT = 5

class CronValidationError(ValueError):
    pass


def validate_cron_expression(expr: str) -> bool:
    """Validate a 5-field crontab expression (no seconds, no @ shortcuts).

    Raises CronValidationError if invalid.
    Returns True if valid.
    """
    parts = expr.strip().split()
    if len(parts) != _CRON_FIELDS_COUNT:
        raise CronValidationError(
            f"Cron expression must have exactly 5 fields, got {len(parts)}: '{expr}'"
        )

    # Ranges: minute(0-59), hour(0-23), day(1-31), month(1-12), weekday(0-7)
    _ranges = [
        (0, 59),   # minute
        (0, 23),   # hour
        (1, 31),   # day of month
        (1, 12),   # month
        (0, 7),    # day of week (0 and 7 = Sunday)
    ]

    for i, (part, (lo, hi)) in enumerate(zip(parts, _ranges)):
        if part == "*":
            continue
        if part.startswith("*/"):
            # Step value
            try:
                step = int(part[2:])
                if step < 1:
                    raise CronValidationError(f"Field {i+1}: step must be >= 1, got {step}")
            except ValueError:
                raise CronValidationError(f"Field {i+1}: invalid step in '{part}'")
            continue
        # Range or list — just check all tokens are integers in range
        for token in part.replace("-", ",").split(","):
            try:
                val = int(token)
                if not (lo <= val <= hi):
                    raise CronValidationError(
                        f"Field {i+1}: value {val} out of range [{lo}-{hi}] in '{expr}'"
                    )
            except ValueError:
                raise CronValidationError(
                    f"Field {i+1}: non-integer token '{token}' in '{expr}'"
                )
    return True


# ── ButlerCronService ──────────────────────────────────────────────────────────

_MAX_ACTIVE_JOBS_PER_ACCOUNT = 50
_AUTO_PAUSE_ERROR_STREAK     = 5


class ButlerCronService:
    """Manages the lifecycle of all scheduled cron jobs for Butler accounts.

    Phase 8 implementation: in-process job store (dict).
    Phase 8b: Postgres-backed store + APScheduler with JobStore.

    Usage:
        svc = ButlerCronService()
        job = svc.create(CreateCronJobRequest(...))
        svc.pause(job.id)
        svc.resume(job.id)
        svc.delete(job.id)
        results = svc.trigger_due_jobs(now=datetime.now(UTC))
    """

    def __init__(self) -> None:
        # Phase 8: in-process store.  Phase 8b: injected AsyncSession.
        self._jobs: dict[str, CronJob] = {}

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def create(self, req: CreateCronJobRequest) -> CronJob:
        """Create and register a new cron job for an account."""
        # Validate cron expression
        validate_cron_expression(req.cron_expression)

        # Per-account limit
        active = self._active_for_account(req.account_id)
        if len(active) >= _MAX_ACTIVE_JOBS_PER_ACCOUNT:
            raise ValueError(
                f"Account '{req.account_id}' has reached the maximum of "
                f"{_MAX_ACTIVE_JOBS_PER_ACCOUNT} active cron jobs. "
                "Delete or pause an existing job before creating new ones."
            )

        job = CronJob(
            account_id=req.account_id,
            name=req.name,
            description=req.description,
            cron_expression=req.cron_expression,
            timezone=req.timezone,
            action=req.action,
            payload=req.payload,
            max_runs=req.max_runs,
            expires_at=req.expires_at,
        )
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> CronJob | None:
        return self._jobs.get(job_id)

    def pause(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.status == CronJobStatus.EXPIRED:
            return False
        job.status = CronJobStatus.PAUSED
        return True

    def resume(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.status == CronJobStatus.EXPIRED:
            return False
        if job.status != CronJobStatus.PAUSED:
            return False
        job.status = CronJobStatus.ACTIVE
        job.error_streak = 0
        return True

    def delete(self, job_id: str) -> bool:
        if job_id not in self._jobs:
            return False
        del self._jobs[job_id]
        return True

    def expire(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.status = CronJobStatus.EXPIRED
        return True

    # ── Query ─────────────────────────────────────────────────────────────────

    def list_jobs(self, account_id: str, status: CronJobStatus | None = None) -> list[CronJob]:
        jobs = [j for j in self._jobs.values() if j.account_id == account_id]
        if status is not None:
            jobs = [j for j in jobs if j.status == status]
        return sorted(jobs, key=lambda j: j.created_at)

    def _active_for_account(self, account_id: str) -> list[CronJob]:
        return [
            j for j in self._jobs.values()
            if j.account_id == account_id and j.status == CronJobStatus.ACTIVE
        ]

    # ── Trigger ───────────────────────────────────────────────────────────────

    def record_trigger(
        self,
        job_id: str,
        success: bool,
        now: datetime | None = None,
    ) -> CronTriggerResult | None:
        """Record the outcome of a cron job trigger.

        Called by the scheduler (APScheduler callback in Phase 8b) after
        OrchestratorService.handle_cron_trigger() resolves.
        """
        job = self._jobs.get(job_id)
        if job is None:
            return None

        ts = now or _now()
        job.last_run_at = ts
        job.run_count += 1

        if success:
            job.error_streak = 0
            if job.status == CronJobStatus.EXECUTING:
                job.status = CronJobStatus.ACTIVE
        else:
            job.error_streak += 1
            if job.error_streak >= _AUTO_PAUSE_ERROR_STREAK:
                job.status = CronJobStatus.FAILED
            else:
                job.status = CronJobStatus.ACTIVE

        # Expire on max_runs
        if job.max_runs > 0 and job.run_count >= job.max_runs:
            job.status = CronJobStatus.EXPIRED

        # Expire on expiry date
        if job.expires_at and ts >= job.expires_at:
            job.status = CronJobStatus.EXPIRED

        return CronTriggerResult(
            job_id=job_id,
            account_id=job.account_id,
            action=job.action,
            triggered_at=ts,
            success=success,
        )

    @property
    def job_count(self) -> int:
        return len(self._jobs)
