"""Compatibility routes for the original skill-ID scheduling API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.automation.migration import parse_legacy_schedule
from app.automation.models import Automation

router = APIRouter()


class JobPatch(BaseModel):
    enabled: bool | None = None


class JobCreate(BaseModel):
    skill_id: str = Field(..., min_length=1)
    schedule: str = Field(..., min_length=1)
    prompt: str | None = None
    params: dict[str, Any] | None = None


def _services(request: Request):
    store = getattr(request.app.state, "automations", None)
    scheduler = getattr(request.app.state, "automation_scheduler", None)
    if store is None or scheduler is None:
        raise HTTPException(status_code=503, detail="scheduler unavailable")
    return store, scheduler


@router.get("/api/schedule/jobs")
async def list_jobs(request: Request) -> dict[str, Any]:
    store = getattr(request.app.state, "automations", None)
    if store is None:
        return {"jobs": []}
    return {"jobs": [
        {"id": task.id, "skill_id": task.skill_id or task.id,
         "schedule": task.schedule.label(), "enabled": task.enabled,
         "next_run": task.next_run, "title": task.title, "last_status": task.last_status}
        for task in store.list()
    ]}


@router.post("/api/schedule/jobs")
async def create_job(body: JobCreate, request: Request) -> dict[str, Any]:
    store, _ = _services(request)
    task_id = f"skill:{body.skill_id.strip()}"
    task = store.get(task_id)
    text = body.prompt or body.skill_id
    try:
        text = text.format(**(body.params or {}))
    except (KeyError, ValueError):
        pass
    if task is None:
        task = Automation(id=task_id, title=body.skill_id, instructions=text,
                          schedule=parse_legacy_schedule(body.schedule), source="legacy",
                          skill_id=body.skill_id, enabled_skill_ids=[body.skill_id])
    else:
        task.instructions = text
        task.schedule = parse_legacy_schedule(body.schedule)
        task.enabled = True
    try:
        store.save(task)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "id": task_id}


@router.post("/api/schedule/jobs/{job_id:path}/run")
async def run_job(job_id: str, request: Request) -> dict[str, Any]:
    store, scheduler = _services(request)
    if store.get(job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    run = scheduler.run_now(job_id)
    if run is None:
        raise HTTPException(status_code=409, detail="job already running")
    return {"ok": True, "run_id": run.run_id}


@router.patch("/api/schedule/jobs/{job_id:path}")
async def patch_job(job_id: str, body: JobPatch, request: Request) -> dict[str, Any]:
    store, _ = _services(request)
    task = store.get(job_id)
    if task is None:
        raise HTTPException(status_code=404, detail="job not found")
    if body.enabled is not None:
        task.enabled = body.enabled
        store.save(task)
    return {"ok": True, "id": job_id, "enabled": task.enabled}
