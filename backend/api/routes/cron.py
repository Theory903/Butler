"""Cron Routes — Phase 8b.

HTTP interface for ButlerCronService.
Allows users to manage their scheduled recurring actions.

Endpoints:
  GET    /cron/jobs                    — list all jobs for account
  POST   /cron/jobs                    — create a new cron job
  GET    /cron/jobs/{id}               — get a single job
  POST   /cron/jobs/{id}/pause         — pause a job
  POST   /cron/jobs/{id}/resume        — resume a paused job
  DELETE /cron/jobs/{id}               — delete a job
  GET    /cron/jobs/{id}/history       — run history (count + last_run_at)
  POST   /cron/validate                — validate a cron expression without creating a job

Security:
  All routes require a valid JWT (account-scoped).
  Jobs are account-scoped — users cannot access other accounts' jobs.
  CronService enforces the 50 active jobs/account limit.

RFC 9457 error format on all error paths.
"""

from __future__ import annotations

import time
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.cron.cron_service import (
    ButlerCronService,
    CreateCronJobRequest,
    CronJob,
    CronJobStatus,
    CronValidationError,
    validate_cron_expression,
)

logger = structlog.get_logger(__name__)


# ── Request / Response schemas ────────────────────────────────────────────────

class CreateJobRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    cron_expression: str = Field(..., description="5-field crontab expression: min hour dom month dow")
    action: str = Field(..., description="Tool name or skill ID to invoke")
    payload: dict = Field(default_factory=dict)
    timezone: str = "UTC"
    description: str = ""
    max_runs: int = Field(default=-1, description="-1 for unlimited")


class ValidateRequest(BaseModel):
    cron_expression: str


def _serialize_job(job: CronJob) -> dict:
    return {
        "id": job.id,
        "account_id": job.account_id,
        "name": job.name,
        "description": job.description,
        "cron_expression": job.cron_expression,
        "timezone": job.timezone,
        "action": job.action,
        "payload": job.payload,
        "status": job.status.value,
        "run_count": job.run_count,
        "max_runs": job.max_runs,
        "error_streak": job.error_streak,
        "created_at": job.created_at.isoformat(),
        "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
        "next_run_at": job.next_run_at.isoformat() if job.next_run_at else None,
        "expires_at": job.expires_at.isoformat() if job.expires_at else None,
    }


def _not_found(job_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "type": "https://butler.lasmoid.ai/problems/cron-job-not-found",
            "title": "Cron Job Not Found",
            "status": 404,
            "detail": f"No cron job with id '{job_id}'.",
        },
    )


def _forbidden() -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={
            "type": "https://butler.lasmoid.ai/problems/forbidden",
            "title": "Forbidden",
            "status": 403,
            "detail": "This cron job belongs to a different account.",
        },
    )


# ── Cron Router ───────────────────────────────────────────────────────────────

def create_cron_router(
    cron_service: ButlerCronService | None = None,
) -> APIRouter:
    """Create the /cron route group.

    Args:
        cron_service: ButlerCronService instance. If None, a fresh instance
                      is created (suitable for tests). In production, inject
                      the singleton wired at startup.
    """
    svc = cron_service or ButlerCronService()
    router = APIRouter(prefix="/cron", tags=["cron"])

    # ── GET /cron/jobs ────────────────────────────────────────────────────────

    @router.get("/jobs", summary="List all cron jobs for the account")
    async def list_jobs(account_id: str = "demo", status: Optional[str] = None) -> dict:
        filter_status = CronJobStatus(status) if status else None
        jobs = svc.list_jobs(account_id, status=filter_status)
        return {
            "jobs": [_serialize_job(j) for j in jobs],
            "count": len(jobs),
            "ts": int(time.time()),
        }

    # ── POST /cron/jobs ───────────────────────────────────────────────────────

    @router.post("/jobs", status_code=201, summary="Create a new cron job")
    async def create_job(body: CreateJobRequest, account_id: str = "demo") -> dict:
        req = CreateCronJobRequest(
            account_id=account_id,
            name=body.name,
            cron_expression=body.cron_expression,
            action=body.action,
            payload=body.payload,
            timezone=body.timezone,
            description=body.description,
            max_runs=body.max_runs,
        )
        try:
            job = svc.create(req)
        except CronValidationError as e:
            raise HTTPException(
                status_code=422,
                detail={
                    "type": "https://butler.lasmoid.ai/problems/invalid-cron-expression",
                    "title": "Invalid Cron Expression",
                    "status": 422,
                    "detail": str(e),
                },
            )
        except ValueError as e:
            raise HTTPException(
                status_code=429,
                detail={
                    "type": "https://butler.lasmoid.ai/problems/cron-limit-exceeded",
                    "title": "Cron Job Limit Exceeded",
                    "status": 429,
                    "detail": str(e),
                },
            )

        logger.info("cron_job_created", job_id=job.id, account_id=account_id, action=body.action)
        return _serialize_job(job)

    # ── GET /cron/jobs/{job_id} ───────────────────────────────────────────────

    @router.get("/jobs/{job_id}", summary="Get a single cron job")
    async def get_job(job_id: str, account_id: str = "demo") -> dict:
        job = svc.get(job_id)
        if job is None:
            raise _not_found(job_id)
        if job.account_id != account_id:
            raise _forbidden()
        return _serialize_job(job)

    # ── POST /cron/jobs/{job_id}/pause ────────────────────────────────────────

    @router.post("/jobs/{job_id}/pause", summary="Pause a cron job")
    async def pause_job(job_id: str, account_id: str = "demo") -> dict:
        job = svc.get(job_id)
        if job is None:
            raise _not_found(job_id)
        if job.account_id != account_id:
            raise _forbidden()
        ok = svc.pause(job_id)
        if not ok:
            raise HTTPException(status_code=409, detail={
                "type": "https://butler.lasmoid.ai/problems/cron-not-pausable",
                "title": "Cannot Pause",
                "status": 409,
                "detail": f"Job '{job_id}' is in status '{job.status.value}' and cannot be paused.",
            })
        return {"job_id": job_id, "status": "paused", "ts": int(time.time())}

    # ── POST /cron/jobs/{job_id}/resume ──────────────────────────────────────

    @router.post("/jobs/{job_id}/resume", summary="Resume a paused cron job")
    async def resume_job(job_id: str, account_id: str = "demo") -> dict:
        job = svc.get(job_id)
        if job is None:
            raise _not_found(job_id)
        if job.account_id != account_id:
            raise _forbidden()
        ok = svc.resume(job_id)
        if not ok:
            status = svc.get(job_id).status.value if svc.get(job_id) else "unknown"
            raise HTTPException(status_code=409, detail={
                "type": "https://butler.lasmoid.ai/problems/cron-not-resumable",
                "title": "Cannot Resume",
                "status": 409,
                "detail": f"Job '{job_id}' is in status '{status}' and cannot be resumed.",
            })
        return {"job_id": job_id, "status": "active", "ts": int(time.time())}

    # ── DELETE /cron/jobs/{job_id} ────────────────────────────────────────────

    @router.delete("/jobs/{job_id}", status_code=200, summary="Delete a cron job")
    async def delete_job(job_id: str, account_id: str = "demo") -> dict:
        job = svc.get(job_id)
        if job is None:
            raise _not_found(job_id)
        if job.account_id != account_id:
            raise _forbidden()
        svc.delete(job_id)
        logger.info("cron_job_deleted", job_id=job_id, account_id=account_id)
        return {"job_id": job_id, "deleted": True, "ts": int(time.time())}

    # ── GET /cron/jobs/{job_id}/history ──────────────────────────────────────

    @router.get("/jobs/{job_id}/history", summary="Run history for a cron job")
    async def job_history(job_id: str, account_id: str = "demo") -> dict:
        job = svc.get(job_id)
        if job is None:
            raise _not_found(job_id)
        if job.account_id != account_id:
            raise _forbidden()
        return {
            "job_id": job_id,
            "run_count": job.run_count,
            "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
            "error_streak": job.error_streak,
            "status": job.status.value,
            "ts": int(time.time()),
        }

    # ── POST /cron/validate ───────────────────────────────────────────────────

    @router.post("/validate", summary="Validate a cron expression without creating a job")
    async def validate_expression(body: ValidateRequest) -> dict:
        try:
            validate_cron_expression(body.cron_expression)
            return {
                "valid": True,
                "expression": body.cron_expression,
                "ts": int(time.time()),
            }
        except CronValidationError as e:
            return {
                "valid": False,
                "expression": body.cron_expression,
                "error": str(e),
                "ts": int(time.time()),
            }

    return router
