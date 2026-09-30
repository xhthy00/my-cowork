"""Agent-facing automation tools; mutating calls require a user confirmation."""

from __future__ import annotations

import uuid

from langchain_core.tools import BaseTool, tool

from app.guardrails.approval import ConfirmHub
from app.guardrails.approval import valid_automation_commands, valid_automation_grants
from app.runtime.todo_context import get_todo_runtime

from .models import Automation, Schedule, next_fire_time
from .store import AutomationStore


def make_automation_tools(store: AutomationStore, confirm_hub: ConfirmHub) -> list[BaseTool]:
    async def approve(name: str, args: dict) -> bool:
        return await confirm_hub.request(uuid.uuid4().hex, name, args)

    def origin() -> dict:
        runtime = get_todo_runtime()
        if runtime is None:
            raise ValueError("No active conversation")
        if runtime.source == "schedule":
            raise ValueError("A scheduled run cannot create or change scheduled tasks")
        return {
            "project_id": runtime.project_id,
            "space_id": runtime.space_id,
            "workspace": runtime.workspace,
            "assistant_id": runtime.assistant_id,
        }

    @tool
    async def create_scheduled_task(
        title: str, instructions: str, cron: str | None = None,
        fire_at: str | None = None, timezone: str = "local",
        notify_target: str | None = None,
        permissions: list[dict[str, str]] | None = None,
        always_allowed_commands: list[str] | None = None,
        auto_approve_commands: bool = False,
    ) -> dict:
        """Create a recurring or one-time task. Convert the user's requested time to a
        five-field cron or ISO fire_at. Instructions say what to execute, without
        repeating the schedule. Show the proposal for user confirmation first.
        """
        context = origin()
        if bool(cron) == bool(fire_at):
            return {"error": "Provide exactly one of cron or fire_at"}
        schedule = Schedule(kind="cron" if cron else "once", cron=cron,
                            fire_at=fire_at, timezone=timezone)
        schedule.validate()
        if next_fire_time(schedule) is None:
            return {"error": "The first scheduled time must be in the future"}
        if notify_target and (not notify_target.startswith("lark:")
                              or not notify_target.removeprefix("lark:").strip()):
            return {"error": "Notification target must be lark:<chat_id>"}
        grants = valid_automation_grants(permissions or [])
        try:
            commands = valid_automation_commands(always_allowed_commands or [])
        except ValueError as exc:
            return {"error": str(exc)}
        proposal = {"title": title, "instructions": instructions,
                    "schedule": schedule.__dict__, "notify_target": notify_target,
                    "permissions": grants,
                    "always_allowed_commands": commands,
                    "auto_approve_commands": auto_approve_commands}
        if not await approve("create_scheduled_task", proposal):
            return {"error": "User rejected scheduled task creation"}
        task = Automation(title=title, instructions=instructions, schedule=schedule,
                          source="agent", notify_target=notify_target, **context)
        task.always_allowed_tools = grants
        task.always_allowed_commands = commands
        task.auto_approve_commands = auto_approve_commands
        store.save(task)
        return {"ok": True, "id": task.id, "next_run": task.next_run,
                "schedule": task.schedule.label()}

    @tool
    def list_scheduled_tasks() -> dict:
        """List scheduled tasks and their next runs and most recent results."""
        origin()
        return {"tasks": [{"id": t.id, "title": t.title, "schedule": t.schedule.label(),
                           "next_run": t.next_run, "enabled": t.enabled,
                           "last_status": t.last_status} for t in store.list()]}

    @tool
    async def update_scheduled_task(
        id: str, title: str | None = None, instructions: str | None = None,
        cron: str | None = None, enabled: bool | None = None,
    ) -> dict:
        """Edit or pause a scheduled task after showing the change for confirmation."""
        origin()
        task = store.get(id)
        if task is None:
            return {"error": "Scheduled task not found"}
        changes = {k: v for k, v in {"title": title, "instructions": instructions,
                                     "cron": cron, "enabled": enabled}.items() if v is not None}
        if cron is not None:
            Schedule(kind="cron", cron=cron, timezone=task.schedule.timezone).validate()
        if not await approve("update_scheduled_task", {"id": id, "changes": changes}):
            return {"error": "User rejected scheduled task update"}
        if title is not None:
            task.title = title
        if instructions is not None:
            task.instructions = instructions
        if cron is not None:
            task.schedule = Schedule(kind="cron", cron=cron, timezone=task.schedule.timezone)
        if enabled is not None:
            task.enabled = enabled
        store.save(task)
        return {"ok": True, "task": task.to_dict()}

    @tool
    async def delete_scheduled_task(id: str) -> dict:
        """Delete a scheduled task and its run history after user confirmation."""
        origin()
        task = store.get(id)
        if task is None:
            return {"error": "Scheduled task not found"}
        if not await approve("delete_scheduled_task", {"id": id, "title": task.title}):
            return {"error": "User rejected scheduled task deletion"}
        if any(run.status in {"running", "waiting_user"} for run in store.runs(id)):
            return {"error": "Cannot delete while a run is active"}
        if task.source == "skill":
            store.set_meta(f"deleted:{id}", "1")
        return {"ok": store.delete(id)}

    return [create_scheduled_task, list_scheduled_tasks,
            update_scheduled_task, delete_scheduled_task]
