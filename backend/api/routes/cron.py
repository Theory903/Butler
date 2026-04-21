"""Cron Routes — Phase 8b Hardened.

HTTP interface for ButlerCronService.
Aligned with Oracle-Grade reliability:
- Uses persistent SQLAlchemy models.
- Uses APScheduler with JobStore.
- RFC 9457 error compliance.
"""

from __future__ import annotations

import time
import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.deps import get_cron_service, get_db
from services.cron.cron_service import ButlerCronService
from domain.cron.models import ButlerCronJob, ButlerCronRun, CronJobStatus, CronDeliveryMode

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/cron", tags=["cron"])

# ── Request / Response schemas ────────────────────────────────────────────────

class CreateJobRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    cron_expression: str = Field(..., description="5-field crontab expression")
    delivery_mode: CronDeliveryMode = Field(default=CronDeliveryMode.ORCHESTRATOR)
    delivery_meta: dict = Field(default_factory=dict, description="action/payload or url/payload")
    timezone: str = "UTC"
    description: str = ""


class ValidateRequest(BaseModel):
    cron_expression: str


def _serialize_job(job: ButlerCronJob) -> dict:
    return {
        "id": str(job.id),
        "account_id": job.account_id,
        "name": job.name,
        "description": job.description,
        "cron_expression": job.expression,
        "timezone": job.timezone,
        "delivery_mode": job.delivery_mode.value,
        "delivery_meta": job.delivery_meta,
        "status": job.status.value,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
        "next_run_at": job.next_run_at.isoformat() if job.next_run_at else None,
    }


def _bad_request(title: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "type": "https://butler.lasmoid.ai/problems/bad-request",
            "title": title,
            "status": 400,
            "detail": detail,
        },
    )


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


# ── GET /cron/jobs ────────────────────────────────────────────────────────────

@router.get("/jobs", summary="List all cron jobs for the account")
async def list_jobs(
    account_id: str = "demo", 
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
) -> dict:
    query = select(ButlerCronJob).where(ButlerCronJob.account_id == account_id)
    if status:
        query = query.where(ButlerCronJob.status == status)
    
    result = await db.execute(query)
    jobs = result.scalars().all()
    
    return {
        "jobs": [_serialize_job(j) for j in jobs],
        "count": len(jobs),
        "ts": int(time.time()),
    }


# ── POST /cron/jobs ───────────────────────────────────────────────────────────

@router.post("/jobs", status_code=201, summary="Create a new cron job")
async def create_job(
    body: CreateJobRequest, 
    account_id: str = "demo",
    db: AsyncSession = Depends(get_db),
    svc: ButlerCronService = Depends(get_cron_service)
) -> dict:
    try:
        job = await svc.create_job(
            db=db,
            account_id=account_id,
            name=body.name,
            expression=body.cron_expression,
            delivery_mode=body.delivery_mode,
            delivery_meta=body.delivery_meta,
            description=body.description,
            timezone_str=body.timezone
        )
        await db.commit()
    except ValueError as e:
        raise _bad_request("Cron Creation Error", str(e))
    except Exception as e:
        logger.error("cron_create_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal Server Error")

    return _serialize_job(job)


# ── GET /cron/jobs/{job_id} ───────────────────────────────────────────────────

@router.get("/jobs/{job_id}", summary="Get a single cron job")
async def get_job(
    job_id: str, 
    account_id: str = "demo",
    db: AsyncSession = Depends(get_db)
) -> dict:
    job = await db.get(ButlerCronJob, uuid.UUID(job_id))
    if job is None or job.account_id != account_id:
        raise _not_found(job_id)
    return _serialize_job(job)


# ── POST /cron/jobs/{job_id}/pause ────────────────────────────────────────────

@router.post("/jobs/{job_id}/pause", summary="Pause a cron job")
async def pause_job(
    job_id: str, 
    account_id: str = "demo",
    db: AsyncSession = Depends(get_db),
    svc: ButlerCronService = Depends(get_cron_service)
) -> dict:
    uid = uuid.UUID(job_id)
    job = await db.get(ButlerCronJob, uid)
    if job is None or job.account_id != account_id:
        raise _not_found(job_id)
    
    await svc.pause_job(db, uid)
    await db.commit()
    
    return {"job_id": job_id, "status": "paused", "ts": int(time.time())}


# ── POST /cron/jobs/{job_id}/resume ───────────────────────────────────────────

@router.post("/jobs/{job_id}/resume", summary="Resume a paused cron job")
async def resume_job(
    job_id: str, 
    account_id: str = "demo",
    db: AsyncSession = Depends(get_db),
    svc: ButlerCronService = Depends(get_cron_service)
) -> dict:
    uid = uuid.UUID(job_id)
    job = await db.get(ButlerCronJob, uid)
    if job is None or job.account_id != account_id:
        raise _not_found(job_id)
    
    await svc.resume_job(db, uid)
    await db.commit()
    
    return {"job_id": job_id, "status": "active", "ts": int(time.time())}


# ── DELETE /cron/jobs/{job_id} ────────────────────────────────────────────────

@router.delete("/jobs/{job_id}", status_code=200, summary="Delete a cron job")
async def delete_job(
    job_id: str, 
    account_id: str = "demo",
    db: AsyncSession = Depends(get_db),
    svc: ButlerCronService = Depends(get_cron_service)
) -> dict:
    uid = uuid.UUID(job_id)
    job = await db.get(ButlerCronJob, uid)
    if job is None or job.account_id != account_id:
        raise _not_found(job_id)
    
    await svc.delete_job(db, uid)
    await db.commit()
    
    return {"job_id": job_id, "deleted": True, "ts": int(time.time())}


# ── GET /cron/jobs/{job_id}/history ──────────────────────────────────────────

@router.get("/jobs/{job_id}/history", summary="Run history for a cron job")
async def job_history(
    job_id: str, 
    account_id: str = "demo",
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
) -> dict:
    uid = uuid.UUID(job_id)
    job = await db.get(ButlerCronJob, uid)
    if job is None or job.account_id != account_id:
        raise _not_found(job_id)
        
    query = select(ButlerCronRun).where(ButlerCronRun.job_id == uid).order_by(ButlerCronRun.triggered_at.desc()).limit(limit)
    res = await db.execute(query)
    runs = res.scalars().all()
    
    return {
        "job_id": job_id,
        "runs": [
            {
                "id": str(r.id),
                "triggered_at": r.triggered_at.isoformat(),
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "status": r.status,
                "error": r.error_message,
                "result": r.result_meta
            } for r in runs
        ],
        "ts": int(time.time()),
    }


def create_cron_router() -> APIRouter:
    """Legacy support for main.py router inclusion."""
    return router
