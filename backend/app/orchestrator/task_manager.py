"""Persisted task status + cancel-aware TaskManager."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator

from app.guardrails.approval import (
    REMOTE_CHANNEL_SOURCES,
    reset_remote_channel,
    set_remote_channel,
)
from app.runtime.budget import Budget
from app.runtime.graph_runner import run_graph
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
    session_id: str | None = None


@dataclass
class _Task:
    """Internal lightweight task object passed to graph_runner."""

    task_id: str
    text: str
    session_mode: str = "workforce"
    memory_enabled: bool = True
    history: list[dict[str, Any]] | None = None
    space_id: str | None = None
    project_id: str | None = None
    space_root_path: str | None = None
    workdir_mode: str | None = None
    assistant_id: str | None = None
    enabled_skill_ids: list[str] | None = None
    session_id: str | None = None


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
        notes_root: Path | str | None = None,
        task_store: Any = None,
        short_term: Any = None,
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
        self.notes_root = Path(notes_root) if notes_root else None
        self.task_store = task_store
        self.short_term = short_term
        self._tasks: dict[str, dict[str, Any]] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._graph_tasks: dict[str, asyncio.Task[None]] = {}

    def _set_status(self, task_id: str, status: str, *, source: str = "user", text: str = "") -> None:
        if task_id not in self._tasks:
            self._tasks[task_id] = {"status": status, "events": []}
        else:
            self._tasks[task_id]["status"] = status
        if self.task_store is not None:
            try:
                self.task_store.upsert(task_id, status, source=source, text=text)
            except Exception:
                pass

    def status(self, task_id: str) -> str:
        """Return NEW|RUNNING|DONE|FAILED|CANCELLED for a task."""
        if task_id in self._tasks:
            return self._tasks[task_id]["status"]
        if self.task_store is not None:
            stored = self.task_store.get_status(task_id)
            if stored is not None:
                return stored
        raise KeyError(task_id)

    def cancel(self, task_id: str) -> bool:
        """Request cancellation of a running task. Returns True if signaled."""
        ev = self._cancel_events.get(task_id)
        signaled = False
        if ev is not None and not ev.is_set():
            ev.set()
            signaled = True
        graph_task = self._graph_tasks.get(task_id)
        if graph_task is not None and not graph_task.done():
            graph_task.cancel()
            signaled = True
        if task_id in self._tasks and self._tasks[task_id]["status"] == "RUNNING":
            self._set_status(task_id, "CANCELLED")
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

    def _new_budget(self) -> Budget:
        return Budget(max_steps=self.max_steps, max_total_tokens=self.max_total_tokens)

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
        task_id = task_req.task_id or str(uuid.uuid4())
        self._set_status(task_id, "NEW", source=task_req.source, text=task_req.text)
        asyncio.create_task(self._run(task_id, task_req))
        return task_id

    async def handle(self, task_req: TaskRequest) -> AsyncIterator[dict[str, Any]]:
        """Run a task synchronously and yield all trace events."""
        task_id = task_req.task_id or str(uuid.uuid4())
        self._set_status(task_id, "NEW", source=task_req.source, text=task_req.text)
        async for event in self._execute(task_id, task_req):
            yield event

    async def _run(self, task_id: str, task_req: TaskRequest) -> None:
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
            session_id = None
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
            session_id = task_req.session_id or task_req.project_id
            enabled_mcp = task_req.enabled_mcp
            req_obj = task_req

        # When an assistant is selected but skills omitted, use its defaults.
        if assistant_id and not enabled_skill_ids:
            from app.assistants import get_assistant

            a = get_assistant(assistant_id)
            if a:
                enabled_skill_ids = list(a.get("enabled_skills") or [])

        from app.runtime.v2.flag import is_v2

        if not is_v2():
            prefix = _assistant_skill_prefix(assistant_id, enabled_skill_ids or None)
            if prefix:
                text = prefix + text

        self._set_status(task_id, "RUNNING", source=source, text=text)
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
            session_mode=session_mode,
            memory_enabled=memory_enabled,
            history=history,
            space_id=space_id,
            project_id=project_id or task_id,
            space_root_path=space_root_path,
            workdir_mode=workdir_mode,
            assistant_id=assistant_id if not isinstance(task_req, str) else None,
            enabled_skill_ids=enabled_skill_ids or None,
            session_id=session_id,
        )
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        budget = self._new_budget()
        graph = self._graph_for(session_mode)
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
            queue.put_nowait(event)

        unsub = self.bus.subscribe(_on_bus)
        remote_token = set_remote_channel(source in REMOTE_CHANNEL_SOURCES)
        from app.tools.mcp.manager import reset_enabled_mcp, set_enabled_mcp

        mcp_token = set_enabled_mcp(enabled_mcp)

        async def _run_graph() -> None:
            try:
                async for _event in run_graph(
                    task,
                    graph,
                    self.bus,
                    budget=budget,
                    long_term=self.long_term,
                    metrics=self.metrics,
                    planner_llm=self.planner_llm,
                    confirm_hub=self.confirm_hub,
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
            except Exception:
                pass

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
                yield event
                if event.get("type") == "graph.end":
                    status = event.get("status")
                    if status == "error":
                        final = "FAILED"
                    elif status == "cancelled":
                        final = "CANCELLED"
                    else:
                        final = "DONE"
                    self._set_status(task_id, final, source=source, text=text)
                    break
        finally:
            unsub()
            reset_enabled_mcp(mcp_token)
            reset_remote_channel(remote_token)
            self._cancel_events.pop(task_id, None)
            self._graph_tasks.pop(task_id, None)
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
