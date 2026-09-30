"""Persisted task status + cancel-aware TaskManager."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field, asdict
import hashlib
import logging
from pathlib import Path
from typing import Any, AsyncIterator

from app.guardrails.approval import (
    REMOTE_CHANNEL_SOURCES,
    reset_remote_channel,
    set_remote_channel,
)
from app.llm.budget import Budget
from app.llm.budget_context import BudgetRuntime
from app.llm.model_config import ModelConfig, ModelRegistry, model_scope
from app.runtime.graph_runner import run_graph
from app.task_support.admission import Admission
from app.task_support.app_context import AppTaskScope, app_task_scope
from app.skills import find_skill


def _event_task_id(event: dict[str, Any]) -> str:
    """Return the owning task id from a flat or nested bus event."""
    tid = event.get("task_id")
    if isinstance(tid, str) and tid:
        return tid
    payload = event.get("payload")
    if isinstance(payload, dict):
        nested = payload.get("task_id")
        if isinstance(nested, str) and nested:
            return nested
    return ""


def _assistant_skill_prefix(
    assistant_id: str | None, skill_ids: list[str] | None
) -> str:
    """Prepend assistant rules + enabled skill bodies so the agent does not skip load_skill."""
    from app.assistants import get_assistant

    ids = [s for s in (skill_ids or []) if s]
    if not ids and not assistant_id:
        return ""
    blocks: list[str] = []
    if assistant_id:
        blocks.append(f"[assistant:{assistant_id}]")
        assistant = get_assistant(assistant_id)
        rules = str((assistant or {}).get("rules") or "").strip()
        if rules:
            blocks.append(
                f'<assistant_rules id="{assistant_id}">\n{rules}\n</assistant_rules>'
            )
    for sid in ids:
        meta = find_skill(sid)
        if meta is None or not meta.prompt:
            blocks.append(f"[skill:{sid} — not found on disk]")
            continue
        # Cap each skill to keep context bounded.
        body = meta.prompt.strip()
        if len(body) > 12000:
            body = body[:12000] + "\n…(truncated)"
        blocks.append(f"<preloaded_skill name=\"{sid}\">\n{body}\n</preloaded_skill>")
    if not blocks:
        return ""
    return (
        "The following assistant skills are preloaded for this task. "
        "Follow them; you may still call load_skill for extras.\n\n"
        + "\n\n".join(blocks)
        + "\n\n---\nUser request:\n"
    )


@dataclass
class TaskRuntime:
    graph: Any
    planner: Any
    config: ModelConfig


@dataclass
class TaskRequest:
    """Inbound request to run a task."""

    text: str
    task_id: str | None = None
    source: str = "user"
    reply_chat_id: str | None = None
    session_mode: str = "workforce"
    memory_enabled: bool = True
    enabled_mcp: list[str] | None = None
    history: list[dict[str, Any]] | None = None
    space_id: str | None = None
    project_id: str | None = None
    space_root_path: str | None = None
    workdir_mode: str | None = None
    assistant_id: str | None = None
    enabled_skill_ids: list[str] | None = None
    knowledge_bases: list[dict[str, Any]] | None = None
    session_id: str | None = None
    resume_execution: bool = False
    run_started_at: float | None = None
    automation_run_id: str | None = None
    automation_store: Any = None
    model_profile_id: str | None = None
    reasoning: dict | None = None
    task_budget: dict | None = None
    budget_snapshot: dict | None = field(default=None, repr=False)
    runtime: TaskRuntime | None = field(default=None, repr=False)
    app_scope: AppTaskScope | None = None


@dataclass
class _Task:
    """Internal lightweight task object passed to graph_runner."""

    task_id: str
    text: str
    source: str = "user"
    session_mode: str = "workforce"
    memory_enabled: bool = True
    history: list[dict[str, Any]] | None = None
    space_id: str | None = None
    project_id: str | None = None
    space_root_path: str | None = None
    workdir_mode: str | None = None
    assistant_id: str | None = None
    enabled_skill_ids: list[str] | None = None
    knowledge_bases: list[dict[str, Any]] | None = None
    session_id: str | None = None
    resume_execution: bool = False
    run_started_at: float | None = None
    automation_run_id: str | None = None
    automation_store: Any = None


class TaskManager:
    """Manage task lifecycle, submit to graphs, and stream trace events."""

    def __init__(
        self,
        graph: Any,
        tools: list,
        bus: Any,
        *,
        long_term: Any = None,
        metrics: Any = None,
        max_steps: int = 50,
        max_total_tokens: int = 200_000,
        planner_llm: Any = None,
        single_agent_graph: Any | None = None,
        confirm_hub: Any | None = None,
        human_input_hub: Any | None = None,
        notes_root: Path | str | None = None,
        task_store: Any = None,
        short_term: Any = None,
        model_registry: ModelRegistry | None = None,
        runtime_factory: Any = None,
        admission: Admission | None = None,
    ) -> None:
        self.graph = graph
        self.single_agent_graph = single_agent_graph
        self.tools = tools
        self.bus = bus
        self.long_term = long_term
        self.metrics = metrics
        self.max_steps = max_steps
        self.max_total_tokens = max_total_tokens
        self.planner_llm = planner_llm
        self.confirm_hub = confirm_hub
        self.human_input_hub = human_input_hub
        self.notes_root = Path(notes_root) if notes_root else None
        self.task_store = task_store
        if task_store is not None and hasattr(task_store, 'interrupt_app_tasks'):
            task_store.interrupt_app_tasks()
        self.short_term = short_term
        self.compacting_sessions: set[str] = set()
        self.model_registry = model_registry
        self.runtime_factory = runtime_factory
        self.admission = admission or Admission()
        self.app_skills = {}
        self._tasks: dict[str, dict[str, Any]] = {}
        self._model_snapshots: dict[str, ModelConfig] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._graph_tasks: dict[str, asyncio.Task[None]] = {}
        self._budgets: dict[str, BudgetRuntime] = {}

    def budget_settings(self) -> dict:
        if self.task_store is not None:
            return self.task_store.get_budget_settings(self.max_total_tokens)
        return {"max_tokens": self.max_total_tokens}

    def set_budget_settings(self, settings: dict) -> None:
        if self.task_store is not None:
            self.task_store.save_budget_settings(settings)
        self.max_total_tokens = settings["max_tokens"]

    def resume_budget(self, task_id: str, limit: int | None) -> None:
        runtime = self._budgets.get(task_id)
        if runtime is None or not runtime.paused or self.status(task_id) != "PAUSED":
            raise ValueError("原任务已结束或后端已重启，无法原位继续")
        runtime.resume(limit)

    def paused_budgets(self) -> list[dict]:
        return [{"task_id": tid, "text": self._tasks.get(tid, {}).get("text", ""),
                 "source": self._tasks.get(tid, {}).get("source", "user"),
                 "tokens": rt.budget.tokens, "max_tokens": rt.budget.max_total_tokens,
                 "required_tokens": rt.required_tokens}
                for tid, rt in self._budgets.items() if rt.paused]

    def _set_status(self, task_id: str, status: str, *, source: str = "user", text: str = "") -> None:
        if task_id not in self._tasks:
            self._tasks[task_id] = {"status": status, "events": []}
        else:
            self._tasks[task_id]["status"] = status
        if text:
            self._tasks[task_id].update(text=text, source=source)
        if self.task_store is not None:
            try:
                self.task_store.upsert(task_id, status, source=source, text=text)
            except Exception as exc:
                self._tasks[task_id]['storage_error'] = f'任务记录保存失败：{exc}'

    def status(self, task_id: str) -> str:
        """Return NEW|RUNNING|PAUSED|DONE|FAILED|CANCELLED for a task."""
        if task_id in self._tasks:
            return self._tasks[task_id]["status"]
        if self.task_store is not None:
            stored = self.task_store.get_status(task_id)
            if stored is not None:
                return stored
        raise KeyError(task_id)

    def cancel(self, task_id: str) -> bool:
        """Request cancellation of a running task. Returns True if signaled."""
        pending = self._tasks.get(task_id, {})
        if pending.get('app_task') and pending.get('status') == 'NEW':
            event = {'type': 'graph.end', 'task_id': task_id, 'status': 'cancelled'}
            if self.task_store is not None:
                self.task_store.append_event(task_id, event)
            pending['events'].append(event)
            self._set_status(task_id, 'CANCELLED')
            return True
        if self.human_input_hub is not None:
            self.human_input_hub.cancel_task(task_id)
        ev = self._cancel_events.get(task_id)
        signaled = False
        if ev is not None and not ev.is_set():
            ev.set()
            signaled = True
        graph_task = self._graph_tasks.get(task_id)
        if graph_task is not None and not graph_task.done():
            graph_task.cancel()
            signaled = True
        if task_id in self._tasks and self._tasks[task_id]["status"] in {"NEW", "RUNNING", "PAUSED", "CANCELLING"}:
            self._set_status(task_id, "CANCELLING" if self._tasks[task_id].get("app_task") else "CANCELLED")
            signaled = True
        return signaled

    def cancel_all(self) -> int:
        """Cancel every known running task. Returns count signaled."""
        ids = list(self._cancel_events.keys()) + [
            tid
            for tid, meta in self._tasks.items()
            if meta.get("status") == "RUNNING" and tid not in self._cancel_events
        ]
        count = 0
        for tid in dict.fromkeys(ids):
            if self.cancel(tid):
                count += 1
        return count

    def _graph_for(self, session_mode: str) -> Any:
        if session_mode == "single-agent" and self.single_agent_graph is not None:
            return self.single_agent_graph
        return self.graph

    def _seed_short_term(self, task_id: str, task_req: TaskRequest) -> None:
        if self.short_term is None:
            return
        try:
            for turn in task_req.history or []:
                self.short_term.append(task_id, turn)
            self.short_term.append(
                task_id, {"role": "user", "content": task_req.text}
            )
        except Exception:
            pass

    async def submit(self, task_req: TaskRequest) -> str:
        """Enqueue a task in the background and return its id."""
        lease = self.admission.acquire(task_req.text[:60] or "聊天任务")
        try:
            self.prepare_task(task_req)
            task_id = task_req.task_id or str(uuid.uuid4())
            self._set_status(task_id, "NEW", source=task_req.source, text=task_req.text)
            self._tasks[task_id]["session_id"] = task_req.session_id or task_req.project_id
            self._tasks[task_id]['app_task'] = bool(task_req.app_scope)
            child = asyncio.create_task(self._run(task_id, task_req, lease))
            child.add_done_callback(lambda _: self.admission.release(lease))
        except BaseException:
            self.admission.release(lease)
            raise
        return task_id

    async def handle(self, task_req: TaskRequest) -> AsyncIterator[dict[str, Any]]:
        """Run a task synchronously and yield all trace events."""
        with self.admission.work(task_req.text[:60] or "聊天任务"):
            self.prepare_task(task_req)
            task_id = task_req.task_id or str(uuid.uuid4())
            self._set_status(task_id, "NEW", source=task_req.source, text=task_req.text)
            async for event in self._execute(task_id, task_req):
                yield event

    def prepare_task(self, request: TaskRequest) -> None:
        """Resolve before scheduling: subsequent connection edits cannot change this run."""
        sid = request.session_id or request.project_id
        if sid in self.compacting_sessions:
            raise ValueError("会话正在压缩，请稍后发送")
        if request.runtime is not None:
            return
        if request.budget_snapshot is None:
            saved_budget = self.task_store.load_budget_snapshot(request.task_id) if request.resume_execution and self.task_store else None
            if saved_budget and saved_budget.get("paused"):
                raise ValueError("预算暂停期间后端已重启，无法原位继续；请检查已有结果后新建任务")
            request.budget_snapshot = dict(saved_budget or (request.task_budget if request.task_budget is not None else self.budget_settings()))
        request.task_id = request.task_id or str(uuid.uuid4())
        if sid and any(meta.get("session_id") == sid and tid != request.task_id and meta.get("status") in {"NEW", "RUNNING", "PAUSED"} for tid, meta in self._tasks.items()):
            raise ValueError("会话忙碌中，请等待当前任务结束")
        if request.resume_execution and request.task_id in self._model_snapshots:
            request.runtime = self.runtime_factory(self._model_snapshots[request.task_id], request.session_mode)
        elif self.model_registry is not None and self.model_registry.initialized:
            saved = self.task_store.load_model_snapshot(request.task_id) if request.resume_execution and self.task_store and hasattr(self.task_store, "load_model_snapshot") else None
            config = self.model_registry.resolve(saved["id"] if saved else request.model_profile_id)
            if saved:
                expected = saved.pop("credential_fingerprint", "")
                if hashlib.sha256(config.api_key.encode()).hexdigest() != expected or config.base_url != saved.get("base_url"):
                    raise ValueError("原任务的连接已变化，无法安全恢复；请恢复连接配置或重新运行任务")
                config = ModelConfig(**saved, api_key=config.api_key)
            elif request.reasoning is not None:
                config = config.with_reasoning(request.reasoning)
            request.runtime = self.runtime_factory(config, request.session_mode)
            if self.task_store and hasattr(self.task_store, "save_model_snapshot"):
                snapshot = asdict(config)
                snapshot.pop("api_key")
                snapshot["credential_fingerprint"] = hashlib.sha256(config.api_key.encode()).hexdigest()
                self.task_store.save_model_snapshot(request.task_id, snapshot)
        elif request.model_profile_id:
            raise ValueError("模型配置尚未同步，请稍后重试")
        if request.runtime is not None and request.source == "schedule":
            self._model_snapshots[request.task_id] = request.runtime.config
        # Reserve before SSE headers or background scheduling yield to another request.
        self._set_status(request.task_id, "NEW", source=request.source, text=request.text)
        self._tasks[request.task_id]["session_id"] = sid

    def session_busy(self, session_id: str) -> bool:
        return any(meta.get("session_id") == session_id and meta.get("status") in {"NEW", "RUNNING", "PAUSED"}
                   for meta in self._tasks.values())

    async def _run(self, task_id: str, task_req: TaskRequest, lease=None) -> None:
        with self.admission.work(task_id, lease):
            if self._tasks[task_id]['status'] == 'CANCELLED':
                return
            async for _event in self._execute(task_id, task_req):
                pass

    async def _execute(
        self, task_id: str, task_req: TaskRequest | str
    ) -> AsyncIterator[dict[str, Any]]:
        """Shared execution loop: stream bus events until graph.end."""
        if isinstance(task_req, str):
            text = task_req
            session_mode = "workforce"
            memory_enabled = True
            history = None
            space_id = None
            project_id = None
            space_root_path = None
            workdir_mode = None
            source = "user"
            assistant_id = None
            enabled_skill_ids: list[str] = []
            knowledge_bases: list[dict[str, Any]] = []
            session_id = None
            resume_execution = False
            run_started_at = None
            automation_run_id = None
            automation_store = None
            enabled_mcp: list[str] | None = None
            req_obj = TaskRequest(text=text, task_id=task_id)
        else:
            text = task_req.text
            session_mode = task_req.session_mode or "workforce"
            memory_enabled = bool(task_req.memory_enabled)
            history = task_req.history
            space_id = task_req.space_id
            project_id = task_req.project_id
            space_root_path = task_req.space_root_path
            workdir_mode = task_req.workdir_mode
            source = task_req.source
            assistant_id = task_req.assistant_id
            enabled_skill_ids = list(task_req.enabled_skill_ids or [])
            knowledge_bases = list(task_req.knowledge_bases or [])
            session_id = task_req.session_id or task_req.project_id
            resume_execution = task_req.resume_execution
            run_started_at = task_req.run_started_at
            automation_run_id = task_req.automation_run_id
            automation_store = task_req.automation_store
            enabled_mcp = task_req.enabled_mcp
            req_obj = task_req

        # When an assistant is selected but skills omitted, use its defaults.
        if assistant_id and not enabled_skill_ids:
            from app.assistants import get_assistant

            a = get_assistant(assistant_id)
            if a:
                enabled_skill_ids = list(a.get("enabled_skills") or [])

        self._set_status(task_id, "RUNNING", source=source, text=text)
        self._tasks[task_id]["session_id"] = session_id
        self._tasks[task_id]['app_task'] = bool(req_obj.app_scope)
        self._seed_short_term(task_id, req_obj)
        other_running = any(
            tid != task_id and not gt.done()
            for tid, gt in self._graph_tasks.items()
        )
        if (
            not other_running
            and self.confirm_hub is not None
            and hasattr(self.confirm_hub, "clear_officecli_auto")
        ):
            self.confirm_hub.clear_officecli_auto()
        task = _Task(
            task_id=task_id,
            text=text,
            source=source,
            session_mode=session_mode,
            memory_enabled=memory_enabled,
            history=history,
            space_id=space_id,
            project_id=project_id or task_id,
            space_root_path=space_root_path,
            workdir_mode=workdir_mode,
            assistant_id=assistant_id if not isinstance(task_req, str) else None,
            enabled_skill_ids=enabled_skill_ids or None,
            knowledge_bases=knowledge_bases or None,
            session_id=session_id,
            resume_execution=resume_execution,
            run_started_at=run_started_at,
            automation_run_id=automation_run_id,
            automation_store=automation_store,
        )
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        budget_snapshot = req_obj.budget_snapshot or req_obj.task_budget or self.budget_settings()
        budget = Budget(self.max_steps, budget_snapshot["max_tokens"])
        budget.tokens = budget_snapshot.get("tokens", 0)
        budget.steps = budget_snapshot.get("steps", 0)
        budget_runtime = BudgetRuntime(task_id, self.bus, budget)
        self._budgets[task_id] = budget_runtime
        if self.task_store:
            self.task_store.save_budget_snapshot(task_id, {"max_tokens": budget.max_total_tokens, "tokens": budget.tokens, "steps": budget.steps, "paused": False})
        runtime = req_obj.runtime
        graph = runtime.graph if runtime else self._graph_for(session_mode)
        cancel_event = asyncio.Event()
        self._cancel_events[task_id] = cancel_event

        def _on_bus(event: dict[str, Any]) -> None:
            owner = _event_task_id(event)
            if owner and owner != task_id:
                return
            if not owner and any(
                tid != task_id and not gt.done()
                for tid, gt in self._graph_tasks.items()
            ):
                # Unscoped events must not fan out while two chats are live.
                return
            if event.get("type") in {"budget.paused", "budget.resumed"}:
                self._set_status(task_id, "PAUSED" if event["type"] == "budget.paused" else "RUNNING", source=source, text=text)
            if self.task_store and event.get("type") in {"budget.update", "budget.paused", "budget.resumed"} and not event.get("estimated"):
                try:
                    self.task_store.save_budget_snapshot(task_id, {"max_tokens": budget.max_total_tokens,
                        "tokens": budget.tokens, "steps": budget.steps, "paused": budget_runtime.paused})
                except Exception:
                    logging.getLogger(__name__).exception("Failed to persist task budget")
            queue.put_nowait(event)

        unsub = self.bus.subscribe(_on_bus)
        remote_token = set_remote_channel(source in REMOTE_CHANNEL_SOURCES)
        from app.tools.mcp.manager import reset_enabled_mcp, set_enabled_mcp

        mcp_token = set_enabled_mcp(enabled_mcp)

        async def _run_graph() -> None:
            scope_token = app_task_scope.set(req_obj.app_scope)
            from app.skills import bundled_skill_scope
            skill_context = bundled_skill_scope(self.app_skills, selected=req_obj.app_scope.skills if req_obj.app_scope is not None else None)
            skill_context.__enter__()
            try:
                async for _event in run_graph(
                    task,
                    graph,
                    self.bus,
                    budget=budget,
                    budget_runtime=budget_runtime,
                    long_term=self.long_term,
                    metrics=self.metrics,
                    planner_llm=runtime.planner if runtime else self.planner_llm,
                    confirm_hub=self.confirm_hub,
                    human_input_hub=self.human_input_hub,
                    notes_root=self.notes_root,
                    cancel_event=cancel_event,
                ):
                    pass
            except asyncio.CancelledError:
                if not cancel_event.is_set():
                    cancel_event.set()
                # Ensure a terminal event reaches the SSE loop.
                queue.put_nowait(
                    {
                        "type": "graph.end",
                        "status": "cancelled",
                        "task_id": task_id,
                    }
                )
            except Exception as exc:
                queue.put_nowait({"type": "graph.end", "status": "error", "task_id": task_id,
                                 "error": type(exc).__name__})
            finally:
                skill_context.__exit__(None, None, None)
                app_task_scope.reset(scope_token)

        with model_scope(runtime.config if runtime else None):
            graph_task = asyncio.create_task(_run_graph())
        self._graph_tasks[task_id] = graph_task

        try:
            while True:
                event = await queue.get()
                if event.get("type") == "graph.end":
                    owner = _event_task_id(event)
                    if owner and owner != task_id:
                        continue
                self._tasks[task_id]["events"].append(event)
                if req_obj.app_scope and self.task_store is not None:
                    try:
                        self.task_store.append_event(task_id, event)
                    except Exception as exc:
                        # A result that failed to persist must never look saved.
                        self._tasks[task_id]['storage_error'] = f'任务记录保存失败：{exc}'
                        event = {'type': 'graph.end', 'task_id': task_id, 'status': 'error',
                                 'error': f'任务记录保存失败：{exc}'}
                if event.get("type") == "graph.end" and self.short_term is not None:
                    try:
                        summary = str(
                            event.get("summary")
                            or event.get("error")
                            or event.get("status")
                            or ""
                        )
                        if summary:
                            self.short_term.append(
                                task_id,
                                {"role": "assistant", "content": summary},
                            )
                    except Exception:
                        pass
                if event.get("type") == "graph.end":
                    status = event.get("status")
                    if status == "error":
                        final = "FAILED"
                    elif status == "cancelled":
                        final = "CANCELLED"
                    else:
                        final = "DONE"
                    self._set_status(task_id, final, source=source, text=text)
                    if final in {"DONE", "FAILED"}:
                        self._model_snapshots.pop(task_id, None)
                    yield event
                    break
                yield event
        finally:
            if self._tasks[task_id]["status"] in {"NEW", "RUNNING", "PAUSED", "CANCELLING"}:
                self._set_status(task_id, "CANCELLED", source=source, text=text)
            if self.human_input_hub is not None:
                self.human_input_hub.cancel_task(task_id)
            unsub()
            reset_enabled_mcp(mcp_token)
            reset_remote_channel(remote_token)
            self._cancel_events.pop(task_id, None)
            self._graph_tasks.pop(task_id, None)
            self._budgets.pop(task_id, None)
            if not graph_task.done():
                graph_task.cancel()
                try:
                    await graph_task
                except (asyncio.CancelledError, Exception):
                    pass
            else:
                try:
                    await graph_task
                except (asyncio.CancelledError, Exception):
                    pass
