"""Execute each automation as a real TaskManager task with a persisted trace."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from app.orchestrator.task_manager import TaskRequest
from app.guardrails.approval import reset_automation_policy, set_automation_policy

from .models import Automation, AutomationRun
from .store import AutomationStore


class AutomationRunner:
    def __init__(self, store: AutomationStore, task_manager: Any, bus: Any = None) -> None:
        self.store = store
        self.task_manager = task_manager
        self.bus = bus

    def _emit(self, kind: str, task: Automation, run: AutomationRun) -> None:
        if self.bus is not None:
            self.bus.emit({"type": kind, "automation_id": task.id, "run_id": run.run_id,
                           "task_id": run.task_execution_id, "session_id": run.session_id,
                           "status": run.status})

    async def __call__(self, task: Automation, run: AutomationRun) -> AutomationRun:
        self._emit("automation.run_started", task, run)
        if task.workspace:
            from pathlib import Path
            Path(task.workspace).mkdir(parents=True, exist_ok=True)
        opening = (
            f"⏰ 定时任务已触发：{task.title}\n\n"
            "现在执行以下任务并给出结果。定时计划已经创建，请不要再次创建或修改定时任务。\n\n"
            f"{task.instructions}"
        )
        req = TaskRequest(
            text=opening,
            task_id=run.task_execution_id,
            source="schedule",
            session_mode=task.session_mode,
            space_id=task.id if task.workspace else task.space_id,
            project_id=task.id if task.workspace else task.project_id,
            space_root_path=task.workspace,
            workdir_mode="direct-write" if task.workspace else None,
            assistant_id=task.assistant_id,
            enabled_skill_ids=task.enabled_skill_ids or None,
            session_id=run.session_id,
            resume_execution=run.resume_count > 0,
            run_started_at=run.started_at,
            automation_run_id=run.run_id,
            automation_store=self.store,
        )
        final_seen = False
        budget_waiting = False
        artifacts: set[str] = set(run.artifacts)
        def current_grants() -> list[dict[str, str]]:
            current = self.store.get(task.id)
            return current.always_allowed_tools if current is not None else []

        def current_commands() -> list[str]:
            current = self.store.get(task.id)
            return current.always_allowed_commands if current is not None else []

        def current_auto_approve_commands() -> bool:
            current = self.store.get(task.id)
            return bool(current and current.auto_approve_commands)

        policy_token = set_automation_policy(
            task.workspace, task.always_allowed_tools, current_grants=current_grants,
            commands=task.always_allowed_commands, current_commands=current_commands,
            auto_approve_commands=task.auto_approve_commands,
            current_auto_approve_commands=current_auto_approve_commands,
        )
        try:
            async for event in self.task_manager.handle(req):
                self.store.append_event(run.run_id, event)
                kind = str(event.get("type") or "")
                if kind in {"budget.paused", "budget.resumed"}:
                    budget_waiting = kind == "budget.paused"
                if kind in {"human.ask", "tool.confirm_request", "to_sub_tasks", "budget.paused"}:
                    run.status = "waiting_user"
                    self.store.update_run(run)
                    self._emit("automation.needs_input", task, run)
                elif run.status == "waiting_user" and not budget_waiting and kind in {"human.answered", "tool.result", "graph.start", "graph.step", "budget.resumed"}:
                    run.status = "running"
                    self.store.update_run(run)
                if kind == "artifact.file":
                    path = event.get("path") or (event.get("payload") or {}).get("path")
                    if isinstance(path, str) and path:
                        artifacts.add(path)
                if kind == "graph.end":
                    final_seen = True
                    state = str(event.get("status") or "")
                    run.status = "error" if state == "error" else "cancelled" if state == "cancelled" else "ok"
                    run.result_text = str(event.get("summary") or "")
                    run.error = str(event.get("error") or "") or None
            if not final_seen:
                run.status = "error"
                run.error = "Agent execution ended without a completion event"
            current_task = self.store.get(task.id) or task
            if run.status == "ok" and current_task.notify_on_completion and current_task.notify_target:
                try:
                    from app.tools.builtin.lark import send_message as lark_send

                    chat_id = current_task.notify_target.removeprefix("lark:")
                    await lark_send.send(chat_id, f"✓ {current_task.title}\n\n{run.result_text.strip()[:280]}")
                except Exception as exc:
                    run.notification_error = str(exc)
                    self.store.append_event(run.run_id, {
                        "type": "automation.notification_failed", "error": run.notification_error,
                    })
        except asyncio.CancelledError:
            if hasattr(self.task_manager, "cancel"):
                self.task_manager.cancel(run.task_execution_id)
            raise
        except Exception as exc:
            run.status = "error"
            run.error = str(exc)
        finally:
            reset_automation_policy(policy_token)
            run.artifacts = sorted(artifacts)
            if run.status in {"ok", "error", "cancelled", "skipped"}:
                run.finished_at = time.time()
                self.store.finish(run)
                self._emit("automation.run_finished", task, run)
            else:
                self.store.update_run(run)
        return run
