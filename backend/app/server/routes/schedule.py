"""Schedule job management API (SkillScheduler)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()


class JobPatch(BaseModel):
    enabled: bool | None = None


class JobCreate(BaseModel):
    skill_id: str = Field(..., min_length=1)
    schedule: str = Field(..., min_length=1)
    prompt: str | None = None
    params: dict[str, Any] | None = None


@router.get("/api/schedule/jobs")
async def list_jobs(request: Request) -> dict[str, Any]:
    sched = getattr(request.app.state, "scheduler", None)
    if sched is None:
        return {"jobs": []}
    jobs = []
    for job in sched.scheduler.get_jobs():
        skill_id = str(job.kwargs.get("skill_id") or job.id.replace("skill:", ""))
        trigger = str(job.trigger)
        jobs.append(
            {
                "id": job.id,
                "skill_id": skill_id,
                "schedule": trigger,
                "enabled": job.next_run_time is not None,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            }
        )
    return {"jobs": jobs}


@router.post("/api/schedule/jobs")
async def create_job(body: JobCreate, request: Request) -> dict[str, Any]:
    sched = getattr(request.app.state, "scheduler", None)
    if sched is None:
        raise HTTPException(status_code=503, detail="scheduler unavailable")
    job_id = sched.register_skill(
        {
            "id": body.skill_id,
            "schedule": body.schedule,
            "prompt": body.prompt or body.skill_id,
            "params": body.params or {},
        }
    )
    if not job_id:
        raise HTTPException(status_code=400, detail="failed to register job")
    return {"ok": True, "id": job_id}


@router.post("/api/schedule/jobs/{job_id:path}/run")
async def run_job(job_id: str, request: Request) -> dict[str, Any]:
    sched = getattr(request.app.state, "scheduler", None)
    if sched is None:
        raise HTTPException(status_code=503, detail="scheduler unavailable")
    job = sched.scheduler.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    kwargs = dict(job.kwargs or {})
    await sched.run_skill(
        str(kwargs.get("skill_id") or job_id),
        params=kwargs.get("params"),
        prompt=kwargs.get("prompt"),
    )
    return {"ok": True}


@router.patch("/api/schedule/jobs/{job_id:path}")
async def patch_job(job_id: str, body: JobPatch, request: Request) -> dict[str, Any]:
    sched = getattr(request.app.state, "scheduler", None)
    if sched is None:
        raise HTTPException(status_code=503, detail="scheduler unavailable")
    job = sched.scheduler.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if body.enabled is False:
        sched.scheduler.pause_job(job_id)
    elif body.enabled is True:
        sched.scheduler.resume_job(job_id)
    return {"ok": True, "id": job_id, "enabled": body.enabled}
