"""Manage persistent scheduled tasks and inspect every execution."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.automation.models import Automation, Schedule

router = APIRouter(prefix="/api/automations")


class ScheduleBody(BaseModel):
    kind: Literal["cron", "once", "interval"]
    cron: str | None = None
    fire_at: str | None = None
    interval_seconds: int | None = None
    timezone: str = "local"


class AutomationCreate(BaseModel):
    title: str = Field(min_length=1)
    instructions: str = Field(min_length=1)
    schedule: ScheduleBody
    workspace: str | None = None
    space_id: str | None = None
    project_id: str | None = None
    assistant_id: str | None = None
    session_mode: Literal["single-agent", "workforce"] = "single-agent"
    enabled_skill_ids: list[str] = Field(default_factory=list)
    notify_on_completion: bool = True
    notify_target: str | None = None
    permissions: list[dict[str, str]] = Field(default_factory=list)
    always_allowed_commands: list[str] = Field(default_factory=list)
    auto_approve_commands: bool = False
    max_runs: int | None = Field(default=None, ge=1)


class AutomationPatch(BaseModel):
    title: str | None = None
    instructions: str | None = None
    schedule: ScheduleBody | None = None
    enabled: bool | None = None
    notify_on_completion: bool | None = None
    notify_target: str | None = None
    workspace: str | None = None
    space_id: str | None = None
    project_id: str | None = None
    assistant_id: str | None = None
    session_mode: Literal["single-agent", "workforce"] | None = None
    enabled_skill_ids: list[str] | None = None
    max_runs: int | None = Field(default=None, ge=1)
    revoke_permission: str | None = None
    always_allowed_commands: list[str] | None = None
    auto_approve_commands: bool | None = None
    add_command: str | None = None
    revoke_command: str | None = None


def _services(request: Request):
    store = getattr(request.app.state, "automations", None)
    scheduler = getattr(request.app.state, "automation_scheduler", None)
    if store is None or scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduled tasks are unavailable")
    return store, scheduler


def _task_or_404(store, task_id: str) -> Automation:
    task = store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return task


@router.get("")
def list_automations(request: Request) -> dict[str, Any]:
    store, _ = _services(request)
    rows = []
    for task in store.list():
        runs = store.runs(task.id)
        unseen = [r for r in runs if r.started_at > task.seen_runs_at]
        active = next((r for r in runs if r.status in {"running", "waiting_user", "recovery_review"}), None)
        rows.append({**task.to_dict(), "unseen_runs": len(unseen),
                     "unseen_failed": any(run.status in {"error", "interrupted"} for run in unseen),
                     "active_run": active.to_dict() if active else None})
    return {"tasks": rows}


@router.post("", status_code=201)
def create_automation(body: AutomationCreate, request: Request) -> dict[str, Any]:
    store, _ = _services(request)
    task = Automation(
        title=body.title.strip(), instructions=body.instructions.strip(),
        schedule=Schedule(**body.schedule.model_dump()),
        workspace=body.workspace, space_id=body.space_id, project_id=body.project_id,
        assistant_id=body.assistant_id, session_mode=body.session_mode,
        enabled_skill_ids=body.enabled_skill_ids,
        notify_on_completion=body.notify_on_completion, notify_target=body.notify_target,
        always_allowed_commands=body.always_allowed_commands,
        auto_approve_commands=body.auto_approve_commands,
        max_runs=body.max_runs,
    )
    from app.guardrails.approval import valid_automation_grants
    task.always_allowed_tools = valid_automation_grants(body.permissions)
    try:
        store.save(task)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if task.next_run is None:
        store.delete(task.id)
        raise HTTPException(status_code=422, detail="The first scheduled time must be in the future")
    return {"ok": True, "task": task.to_dict()}


@router.get("/{task_id}")
def get_automation(task_id: str, request: Request) -> dict[str, Any]:
    store, _ = _services(request)
    task = _task_or_404(store, task_id)
    return {"task": task.to_dict(), "runs": [run.to_dict() for run in store.runs(task_id)]}


@router.patch("/{task_id}")
def patch_automation(task_id: str, body: AutomationPatch, request: Request) -> dict[str, Any]:
    store, _ = _services(request)
    task = _task_or_404(store, task_id)
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        if key == "schedule":
            task.schedule = Schedule(**value)
        elif key == "revoke_permission":
            task.always_allowed_tools = [g for g in task.always_allowed_tools
                                         if f"{g['tool']} {g['target']}" != value]
        elif key == "add_command":
            task.always_allowed_commands = [*task.always_allowed_commands, value]
        elif key == "revoke_command":
            task.always_allowed_commands = [command for command in task.always_allowed_commands
                                            if command != value]
        elif hasattr(task, key):
            setattr(task, key, value)
    try:
        store.save(task)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "task": task.to_dict()}


@router.delete("/{task_id}")
def delete_automation(task_id: str, request: Request) -> dict[str, Any]:
    store, _ = _services(request)
    task = _task_or_404(store, task_id)
    if any(run.status in {"running", "waiting_user", "recovery_review"} for run in store.runs(task_id)):
        raise HTTPException(status_code=409, detail="Stop the active run before deleting this task")
    if task.source == "skill":
        store.set_meta(f"deleted:{task_id}", "1")
    return {"ok": store.delete(task_id)}


@router.post("/{task_id}/run", status_code=202)
async def run_automation(task_id: str, request: Request) -> dict[str, Any]:
    store, scheduler = _services(request)
    _task_or_404(store, task_id)
    run = scheduler.run_now(task_id)
    if run is None:
        raise HTTPException(status_code=409, detail="This task is already running")
    return {"ok": True, "run": run.to_dict()}


@router.post("/{task_id}/seen")
def seen_automation(task_id: str, request: Request) -> dict[str, Any]:
    store, _ = _services(request)
    if not store.mark_seen(task_id):
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return {"ok": True}


@router.get("/{task_id}/runs")
def list_runs(task_id: str, request: Request) -> dict[str, Any]:
    store, _ = _services(request)
    _task_or_404(store, task_id)
    return {"runs": [run.to_dict() for run in store.runs(task_id)]}


@router.get("/{task_id}/runs/{run_id}")
def get_run(task_id: str, run_id: str, request: Request) -> dict[str, Any]:
    store, _ = _services(request)
    _task_or_404(store, task_id)
    run = store.get_run(run_id)
    if run is None or run.task_id != task_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run": run.to_dict(), "events": store.events(run_id)}


@router.post("/{task_id}/runs/{run_id}/cancel")
async def cancel_run(task_id: str, run_id: str, request: Request) -> dict[str, Any]:
    store, scheduler = _services(request)
    run = store.get_run(run_id)
    if run is None or run.task_id != task_id:
        raise HTTPException(status_code=404, detail="Run not found")
    if not await scheduler.cancel_run(run_id):
        raise HTTPException(status_code=409, detail="Run is no longer active")
    return {"ok": True}


@router.post("/{task_id}/runs/{run_id}/resume", status_code=202)
async def resume_run(task_id: str, run_id: str, request: Request) -> dict[str, Any]:
    store, scheduler = _services(request)
    run = store.get_run(run_id)
    if run is None or run.task_id != task_id:
        raise HTTPException(status_code=404, detail="Run not found")
    resumed = scheduler.resume_reviewed(run_id)
    if resumed is None:
        raise HTTPException(status_code=409, detail="Run is not awaiting recovery review")
    return {"ok": True, "run": resumed.to_dict()}
