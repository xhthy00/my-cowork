"""Graph execution utilities: stream events, convert to TraceBus events."""

from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from app.agents.workers import WORKER_IDS, WORKER_LABELS
from app.graphs.routing import (
    document_tools_succeeded,
    extract_claimed_office_paths,
    has_office_deliverable,
    wants_document,
    wants_pptx,
)
from app.guardrails.approval import is_remote_channel
from app.llm.token_counter import count_tokens
from app.runtime.attachments import stage_attachments_for_task
from app.runtime.budget import BudgetExhausted
from app.runtime.budget_context import (
    BudgetRuntime,
    reset_budget_runtime,
    set_budget_runtime,
)
from app.runtime.compressor import maybe_compress
from app.runtime.context import inject_memories, looks_like_workspace_dump
from app.runtime.decompose import decompose_subtasks, normalize_subtasks
from app.runtime.memory_context import (
    reset_long_term_runtime,
    set_long_term_runtime,
)
from app.runtime.notes_context import NotesRuntime, reset_notes_runtime, set_notes_runtime
from app.runtime.workspace_context import (
    WorkspaceRuntime,
    reset_workspace_runtime,
    set_workspace_runtime,
)
from app.tools.builtin.docgen.gongwen_format import (
    enable_gongwen_format,
    maybe_apply_gongwen_format,
    reset_gongwen_format,
    task_wants_gongwen_format,
)
from app.workspace.output_files import cleanup_process_files, list_new_deliverables
from app.workspace.resolver import get_workspace_resolver
from app.runtime.todo_context import TodoRuntime, reset_todo_runtime, set_todo_runtime
from app.runtime.todo_planner import (
    advance_todos,
    pick_todo_for_worker,
    plan_todos_llm,
)
from app.runtime.v2.flag import is_v2
from app.runtime.v2.synthesize import (
    is_process_meta as _is_process_meta,
    resolve_workforce_end_summary,
)

_WORKER_NAMES = frozenset(WORKER_IDS)
_AGENT_NODES = _WORKER_NAMES | {"single_agent"}
_SCREENSHOT_RE = re.compile(
    r"(?P<path>(?:[A-Za-z]:)?[^\s\"']+\.(?:png|jpe?g|webp|gif))",
    re.IGNORECASE,
)
_WROTE_PATH_RE = re.compile(
    r"Wrote\s+\d+\s+characters\s+to\s+(?P<path>.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_ABS_FILE_RE = re.compile(
    r"(?P<path>(?:/(?:Users|home|tmp|var|private|Volumes)[^\s\"'`，。；]+"
    r"|[A-Za-z]:\\[^\s\"'`，。；]+)"
    r"\.(?:md|txt|csv|json|html?|docx?|pptx?|xlsx|pdf|png|jpe?g|webp|gif))",
    re.IGNORECASE,
)


def build_initial_state(
    task: Any,
    long_term: Any = None,
    *,
    subtasks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the initial WorkforceState / single-agent state from a task."""
    text = getattr(task, "text", "") or ""
    memory_enabled = getattr(task, "memory_enabled", True)
    history = getattr(task, "history", None)
    if is_v2():
        from langchain_core.messages import HumanMessage

        messages = [HumanMessage(content=text)]
    else:
        messages = inject_memories(
            text,
            long_term if memory_enabled else None,
            history=history,
        )
    state: dict[str, Any] = {
        "messages": messages,
        "task_id": getattr(task, "task_id", ""),
        "session_id": getattr(task, "session_id", None) or getattr(task, "task_id", ""),
        "session_mode": getattr(task, "session_mode", "workforce") or "workforce",
        "user_text": text,
        "assistant_id": getattr(task, "assistant_id", None) or "",
        "enabled_skill_ids": list(getattr(task, "enabled_skill_ids", None) or []),
        "round": 0,
        "assigned_task_id": None,
    }
    if subtasks is not None:
        state["subtasks"] = normalize_subtasks(subtasks)
    return state


def _event(task_id: str, etype: str, **extra: Any) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **extra,
        "type": etype,
    }


def _tokens_from_update(update: Any) -> int:
    if not isinstance(update, dict):
        return 0
    messages = update.get("messages")
    if not messages:
        return 0
    try:
        return count_tokens(messages)
    except Exception:
        return 0


def _emit_agent_roster(
    bus: Any, task_id: str, *, session_mode: str = "workforce"
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if session_mode == "single-agent":
        labels = {"single_agent": "Single Agent"}
    else:
        labels = dict(WORKER_LABELS)
    for wid, name in labels.items():
        ev = _event(
            task_id,
            "agent.create",
            agent_id=wid,
            name=name,
            agent_type=wid,
        )
        bus.emit(ev)
        events.append(ev)
    return events


def _content_blob(update: Any) -> str:
    if not isinstance(update, dict):
        return str(update or "")
    parts: list[str] = []
    for msg in update.get("messages") or []:
        if isinstance(msg, dict):
            parts.append(str(msg.get("content") or ""))
        else:
            parts.append(str(getattr(msg, "content", "") or ""))
    return "\n".join(parts)


def _track_path(
    written_paths: set[str] | None,
    path: str,
    *,
    workdir: Path | None = None,
) -> None:
    if written_paths is None or not path:
        return
    cleaned = path.strip().rstrip("`'\".,;:)")
    if not cleaned:
        return
    if workdir is not None:
        try:
            resolved = Path(cleaned).expanduser().resolve()
            resolved.relative_to(workdir.resolve())
        except (OSError, ValueError):
            return
        written_paths.add(str(resolved))
        return
    written_paths.add(cleaned)


def _existing_file(path: str, *, workdir: Path | None = None) -> str | None:
    """Return resolved path if it points to an existing file; else None."""
    cleaned = path.strip().rstrip("`'\".,;:)")
    if not cleaned:
        return None
    candidates: list[Path] = []
    try:
        candidates.append(Path(cleaned).expanduser())
    except OSError:
        return None
    if workdir is not None and not cleaned.startswith(("/", "~")) and not (
        len(cleaned) > 2 and cleaned[1] == ":"
    ):
        candidates.append(workdir / cleaned)
    if workdir is not None:
        candidates.append(workdir / Path(cleaned).name)
    for cand in candidates:
        try:
            resolved = cand.resolve()
            if resolved.is_file():
                return str(resolved)
        except OSError:
            continue
    return None


def _last_ai_text(messages: list[Any]) -> str:
    from app.agents.sanitize import strip_model_junk

    for msg in reversed(messages or []):
        role = (
            str(msg.get("type") or msg.get("role") or "")
            if isinstance(msg, dict)
            else str(getattr(msg, "type", None) or getattr(msg, "role", None) or "")
        )
        if role not in {"ai", "AIMessage", "assistant"}:
            continue
        content = (
            str(msg.get("content") or "")
            if isinstance(msg, dict)
            else str(getattr(msg, "content", None) or "")
        )
        content = strip_model_junk(content).strip()
        if content:
            return content
    return ""


def _missing_claimed_office_files(
    text: str, *, workdir: Path | None = None
) -> list[str]:
    missing: list[str] = []
    for path in extract_claimed_office_paths(text):
        if _existing_file(path, workdir=workdir) is None:
            missing.append(path)
    return missing


def _emit_artifact_file(
    bus: Any,
    task_id: str,
    agent_id: str,
    path: str,
    *,
    workdir: Path | None = None,
    written_paths: set[str] | None = None,
    min_mtime: float | None = None,
) -> dict[str, Any] | None:
    existing = _existing_file(path, workdir=workdir)
    if not existing:
        return None
    maybe_apply_gongwen_format(existing)
    # A file that predates this run is only a real deliverable when this run
    # wrote it — otherwise the agent merely *mentioned* an old file (e.g. a
    # previous task's pptx) and it must not surface as a new artifact.
    if min_mtime is not None:
        try:
            if Path(existing).stat().st_mtime < min_mtime - 5.0:
                return None
        except OSError:
            return None
    _track_path(written_paths, existing, workdir=workdir)
    art = _event(task_id, "artifact.file", path=existing, agent_id=agent_id)
    bus.emit(art)
    return art


def _maybe_preview_events(
    bus: Any,
    task_id: str,
    agent_id: str,
    update: Any,
    *,
    written_paths: set[str] | None = None,
    workdir: Path | None = None,
    min_mtime: float | None = None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    blob = _content_blob(update)
    if not blob:
        return events

    seen_paths: set[str] = set()
    for m in _WROTE_PATH_RE.finditer(blob):
        path = m.group("path").strip().rstrip("`'\"")
        if path and path not in seen_paths:
            seen_paths.add(path)
            art = _emit_artifact_file(
                bus,
                task_id,
                agent_id,
                path,
                workdir=workdir,
                written_paths=written_paths,
                min_mtime=min_mtime,
            )
            if art:
                events.append(art)
    for m in _ABS_FILE_RE.finditer(blob):
        path = m.group("path").strip().rstrip("`'\".,;:)")
        if path and path not in seen_paths:
            seen_paths.add(path)
            art = _emit_artifact_file(
                bus,
                task_id,
                agent_id,
                path,
                workdir=workdir,
                written_paths=written_paths,
                min_mtime=min_mtime,
            )
            if art:
                events.append(art)

    for m in _SCREENSHOT_RE.finditer(blob):
        path = m.group("path")
        if "screenshot" in path.lower() or path.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            existing = _existing_file(path, workdir=workdir)
            if not existing:
                continue
            if min_mtime is not None:
                try:
                    if Path(existing).stat().st_mtime < min_mtime - 5.0:
                        continue
                except OSError:
                    continue
            _track_path(written_paths, existing, workdir=workdir)
            shot = _event(task_id, "artifact.screenshot", path=existing, agent_id=agent_id)
            bus.emit(shot)
            events.append(shot)
            preview = _event(
                task_id,
                "preview.open",
                kind="file",
                path=existing,
                agent_id=agent_id,
            )
            bus.emit(preview)
            events.append(preview)

    # Terminal preview is emitted from _tool_result_events for bash / exec.bash.
    return events


def _emit_graph_end(
    bus: Any,
    task_id: str,
    status: str,
    *,
    workdir: Path | None,
    written_paths: set[str],
    min_mtime: float | None = None,
    extra_scan_roots: list[Path] | None = None,
    **extra: Any,
) -> list[dict[str, Any]]:
    """Cleanup process files then emit artifact.file for leftovers + graph.end."""
    events: list[dict[str, Any]] = []
    for path in list(written_paths):
        maybe_apply_gongwen_format(path)
    cleaned: list[str] = []
    rescued: list[str] = []
    already: set[str] = set(written_paths)
    if workdir is not None:
        try:
            cleaned, rescued = cleanup_process_files(workdir, written_paths)
        except Exception:
            cleaned, rescued = [], []
        already.update(rescued)
        for path in rescued:
            maybe_apply_gongwen_format(path)
            rescue_ev = _event(task_id, "artifact.file", path=path)
            bus.emit(rescue_ev)
            events.append(rescue_ev)
    scan_dirs: list[Path] = []
    if workdir is not None:
        scan_dirs.append(workdir)
    for root in extra_scan_roots or []:
        if root is None:
            continue
        scan_dirs.append(Path(root))
    if min_mtime is not None:
        seen_extra: set[str] = set()
        for root in scan_dirs:
            try:
                extras = list_new_deliverables(
                    root, min_mtime=min_mtime, already=already
                )
            except Exception:
                extras = []
            for path in extras:
                if path in seen_extra:
                    continue
                seen_extra.add(path)
                already.add(path)
                maybe_apply_gongwen_format(path)
                extra_ev = _event(task_id, "artifact.file", path=path)
                bus.emit(extra_ev)
                events.append(extra_ev)
    if cleaned:
        cleanup_ev = _event(
            task_id,
            "artifact.cleanup",
            paths=cleaned[:50],
            count=len(cleaned),
        )
        bus.emit(cleanup_ev)
        events.append(cleanup_ev)
    end_event = _event(
        task_id,
        "graph.end",
        status=status,
        cleaned_paths=cleaned[:50],
        cleaned_count=len(cleaned),
        **extra,
    )
    bus.emit(end_event)
    events.append(end_event)
    return events


def _subtasks_to_todos(subtasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    todos: list[dict[str, Any]] = []
    for i, t in enumerate(subtasks, start=1):
        status = str(t.get("status") or "waiting")
        if status == "completed":
            mapped = "completed"
        elif status == "failed":
            mapped = "failed"
        elif status == "running":
            mapped = "in_progress"
        else:
            mapped = "pending"
        content = str(t.get("content") or "")
        todos.append(
            {
                "id": str(t.get("id") or f"todo_{i}"),
                "content": content,
                "active_form": f"正在执行：{content[:40]}",
                "status": mapped,
                "agent": str(t.get("assignee") or ""),
            }
        )
    in_prog = [t for t in todos if t["status"] == "in_progress"]
    if not in_prog:
        for t in todos:
            if t["status"] == "pending":
                t["status"] = "in_progress"
                break
    return todos


_THINK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


def _strip_think(text: str) -> str:
    return _THINK_RE.sub("", text or "").strip()


async def run_graph(
    task: Any,
    graph: Any,
    bus: Any,
    budget: Any = None,
    long_term: Any = None,
    metrics: Any = None,
    *,
    compress_threshold: int = 120_000,
    planner_llm: Any = None,
    confirm_hub: Any = None,
    notes_root: Path | str | None = None,
    cancel_event: Any = None,
) -> AsyncIterator[dict[str, Any]]:
    """Run a compiled graph, emit trace events to *bus*, and yield them.

    If *cancel_event* is an ``asyncio.Event`` that becomes set, the run stops
    and emits ``graph.end`` with ``status=cancelled``.
    """
    task_id = getattr(task, "task_id", "")
    session_mode = getattr(task, "session_mode", "workforce") or "workforce"
    agent_id = "single_agent" if session_mode == "single-agent" else "coordinator"
    user_ask = getattr(task, "text", "") or ""
    # Decompose / plan against the raw user text — workspace hints must not
    # change trivial-greeting detection or assignee heuristics.
    plan_ask = user_ask

    def _cancelled() -> bool:
        return cancel_event is not None and cancel_event.is_set()

    notes_token = None
    memory_token = None
    gongwen_token = None
    if notes_root is not None:
        notes_token = set_notes_runtime(
            NotesRuntime(task_id=task_id, root=Path(notes_root))
        )
    if getattr(task, "memory_enabled", True) and long_term is not None:
        memory_token = set_long_term_runtime(long_term)

    budget_token = None
    if budget is not None:
        budget_token = set_budget_runtime(
            BudgetRuntime(task_id=task_id, bus=bus, budget=budget)
        )

    workspace_token = None
    space_id = getattr(task, "space_id", None) or "space-local"
    project_id = getattr(task, "project_id", None) or task_id
    frozen = None
    try:
        frozen = get_workspace_resolver().freeze_task_directories(
            space_id=space_id,
            project_id=project_id,
            task_id=task_id,
            workdir_mode=getattr(task, "workdir_mode", None),
            space_root_path=getattr(task, "space_root_path", None),
        )
        workspace_token = set_workspace_runtime(
            WorkspaceRuntime(
                space_id=space_id,
                project_id=project_id,
                task_id=task_id,
                working_directory=frozen.working_directory,
                task_output_root=frozen.task_output_root,
                workdir_mode=frozen.workdir_mode,
                base_snapshot_id=frozen.base_snapshot_id,
                space_root=frozen.space_root,
            )
        )
        # Ensure tools may touch workdir / run output / space root
        try:
            from app.tools.builtin.fs import get_guard

            guard = get_guard()
            guard.add_whitelist(str(frozen.working_directory))
            guard.add_whitelist(str(frozen.task_output_root))
            if frozen.space_root is not None:
                guard.add_whitelist(str(frozen.space_root))
            user_ask = stage_attachments_for_task(
                user_ask, frozen.working_directory, guard
            )
            scratch = frozen.working_directory / "_scratch"
            scratch.mkdir(parents=True, exist_ok=True)
            user_ask = (
                f"{user_ask.rstrip()}\n\n"
                f"[工作空间约束]\n"
                f"- 最终产出目录: `{frozen.working_directory}`\n"
                f"- 过程/临时文件目录: `{scratch}`\n"
                f"- 最终交付（docx/pptx/xlsx/pdf/图等）必须写在最终产出目录下，"
                f"**禁止**放在 `_scratch/`；任务结束会清空 `_scratch`。\n"
                f"- 除非用户明确要求桌面，否则不要写入 Desktop/桌面。\n"
                f"- 最终交付只保留完整成品（报告/图/文档），不要把 part/skeleton/"
                f"script 等中间文件当作最终结果。"
            )
            # Keep task.text in sync for build_initial_state / planners.
            try:
                task.text = user_ask
            except Exception:
                pass
        except Exception:
            pass
    except Exception:
        # Freeze failure should not block chat; tools fall back to PathGuard only.
        workspace_token = None
        frozen = None

    todo_rt = TodoRuntime(task_id=task_id, bus=bus, agent_id=agent_id)
    todo_token = set_todo_runtime(todo_rt)
    workers_ran = 0
    run_messages: list[Any] = []
    todos: list[dict[str, Any]] = []
    confirmed: list[dict[str, Any]] | None = None
    live_subtasks: list[dict[str, Any]] = []
    written_paths: set[str] = set()
    # Files older than this timestamp were not produced by the current run —
    # merely mentioning their path must not surface them as new deliverables.
    run_started_at = time.time()
    workdir: Path | None = (
        Path(frozen.working_directory) if frozen is not None else None
    )
    gongwen_token = enable_gongwen_format(task_wants_gongwen_format(task))

    start_event = _event(task_id, "graph.start")
    bus.emit(start_event)
    yield start_event

    for roster_ev in _emit_agent_roster(bus, task_id, session_mode=session_mode):
        yield roster_ev

    try:
        if session_mode == "workforce":
            subtasks = await decompose_subtasks(plan_ask, planner_llm)
            if subtasks:
                decomp = _event(
                    task_id,
                    "decompose_text",
                    text=f"拆解为 {len(subtasks)} 个子任务",
                )
                bus.emit(decomp)
                yield decomp
                if confirm_hub is not None and hasattr(confirm_hub, "request_plan"):
                    confirmed = await confirm_hub.request_plan(task_id, subtasks)
                    confirmed = normalize_subtasks(confirmed) or subtasks
                else:
                    to_sub = _event(
                        task_id,
                        "to_sub_tasks",
                        subtasks=subtasks,
                        needs_confirm=False,
                    )
                    bus.emit(to_sub)
                    yield to_sub
                    confirmed = subtasks
                live_subtasks = list(confirmed)
                todos = _subtasks_to_todos(confirmed)
                todo_rt.todos = todos
                plan_ev = _event(task_id, "todo_state", agent_id=agent_id, todos=todos)
                bus.emit(plan_ev)
                yield plan_ev
            else:
                for ev in _emit_graph_end(
                    bus,
                    task_id,
                    "ok",
                    workdir=workdir,
                    written_paths=written_paths,
                    min_mtime=run_started_at,
                ):
                    yield ev
                return
        else:
            todos = await plan_todos_llm(
                plan_ask,
                planner_llm,
                session_mode=session_mode,
                history=getattr(task, "history", None),
            )
            todo_rt.todos = todos
            if todos:
                plan_ev = _event(task_id, "todo_state", agent_id=agent_id, todos=todos)
                bus.emit(plan_ev)
                yield plan_ev

        state = build_initial_state(
            task,
            long_term=long_term,
            subtasks=confirmed if session_mode == "workforce" else None,
        )

        class _Ctx:
            def __init__(self, messages: list) -> None:
                self.messages = messages

        ctx = _Ctx(state["messages"])
        await maybe_compress(ctx, threshold=compress_threshold)
        state["messages"] = ctx.messages
        run_messages = list(state.get("messages") or [])

        if getattr(task, "memory_enabled", True) and long_term is not None:
            injected = 0
            for msg in state["messages"]:
                content = getattr(msg, "content", "") or ""
                if isinstance(content, str) and content.startswith("相关长期记忆"):
                    injected = max(0, content.count(". "))
                    break
            if injected:
                mem_ev = _event(task_id, "memory.injected", count=injected)
                bus.emit(mem_ev)
                yield mem_ev

        run_config = {
            "configurable": {
                "thread_id": getattr(task, "session_id", None) or task_id
            }
        }
        async for chunk in graph.astream(
            state, config=run_config, stream_mode="updates"
        ):
            if _cancelled():
                for ev in _emit_graph_end(
                    bus,
                    task_id,
                    "cancelled",
                    workdir=workdir,
                    written_paths=written_paths,
                    min_mtime=run_started_at,
                ):
                    yield ev
                return
            for node, update in (chunk or {}).items():
                if isinstance(update, dict):
                    extra_msgs = update.get("messages") or []
                    if extra_msgs:
                        run_messages.extend(extra_msgs)
                    if session_mode == "workforce" and update.get("subtasks"):
                        from app.graphs.state import merge_subtasks

                        live_subtasks = merge_subtasks(
                            live_subtasks, list(update["subtasks"])
                        )
                        todos = _subtasks_to_todos(live_subtasks)
                        todo_rt.todos = todos
                        todo_ev = _event(
                            task_id, "todo_state", agent_id=node, todos=todos
                        )
                        bus.emit(todo_ev)
                        yield todo_ev
                        for st in update["subtasks"]:
                            st_status = str(st.get("status") or "")
                            if st_status in {"completed", "failed", "running"}:
                                ts = _event(
                                    task_id,
                                    "task_state",
                                    sub_task_id=str(st.get("id")),
                                    status=st_status,
                                    agent_id=str(st.get("assignee") or node),
                                    content=str(
                                        st.get("result") or st.get("content") or ""
                                    ),
                                )
                                bus.emit(ts)
                                yield ts

                if todo_rt.todos:
                    todos = list(todo_rt.todos)

                focus_id = None
                if node in _AGENT_NODES and todos and session_mode != "workforce":
                    focus_id = pick_todo_for_worker(todos, node)
                    if focus_id:
                        prev = next(
                            (t for t in todos if t.get("status") == "in_progress"),
                            None,
                        )
                        completed_ids = (
                            [prev["id"]] if prev and prev["id"] != focus_id else []
                        )
                        todos = advance_todos(
                            todos,
                            mark_completed_ids=completed_ids,
                            next_in_progress_id=focus_id,
                        )
                        todo_rt.todos = todos
                        todo_ev = _event(
                            task_id,
                            "todo_state",
                            agent_id=node,
                            todos=todos,
                        )
                        bus.emit(todo_ev)
                        yield todo_ev

                if node in _AGENT_NODES:
                    workers_ran += 1
                    act = _event(task_id, "agent.activate", agent_id=node)
                    bus.emit(act)
                    yield act
                    assign_content = f"正在运行 · {node}"
                    assign_id = f"{task_id}:{node}"
                    if isinstance(update, dict) and update.get("subtasks"):
                        for st in update["subtasks"]:
                            assign_content = str(st.get("content") or assign_content)
                            assign_id = str(st.get("id") or assign_id)
                            waiting = _event(
                                task_id,
                                "assign_task",
                                agent_id=node,
                                sub_task_id=assign_id,
                                content=assign_content,
                                status="running",
                            )
                            bus.emit(waiting)
                            yield waiting
                    assign = _event(
                        task_id,
                        "agent.assign",
                        agent_id=node,
                        assign_id=assign_id,
                        content=assign_content,
                        status="running",
                    )
                    bus.emit(assign)
                    yield assign

                step_event = _event(
                    task_id, "graph.step", node=node, update=_serialize(update)
                )
                bus.emit(step_event)
                yield step_event

                for tool_ev in _tool_result_events(
                    bus,
                    task_id,
                    update,
                    agent_id=node,
                    written_paths=written_paths,
                    workdir=workdir,
                    min_mtime=run_started_at,
                ):
                    yield tool_ev

                if todo_rt.todos:
                    todos = list(todo_rt.todos)

                if node in _AGENT_NODES:
                    for extra in _maybe_preview_events(
                        bus,
                        task_id,
                        node,
                        update,
                        written_paths=written_paths,
                        workdir=workdir,
                        min_mtime=run_started_at,
                    ):
                        yield extra
                    done = _event(
                        task_id,
                        "agent.assign",
                        agent_id=node,
                        assign_id=f"{task_id}:{node}",
                        content=f"已完成 · {node}",
                        status="completed",
                    )
                    bus.emit(done)
                    yield done
                    deact = _event(task_id, "agent.deactivate", agent_id=node)
                    bus.emit(deact)
                    yield deact

                if budget is not None:
                    budget.consume_step()
                    # Live totals come from BudgetTokenCallback during LLM calls.
                    # Fallback: count node messages when no callback fired (e.g. tests).
                    if budget.tokens == 0:
                        n = _tokens_from_update(update)
                        if n:
                            budget.consume_tokens(n)
                    budget_event = _event(
                        task_id,
                        "budget.update",
                        tokens=budget.tokens,
                        max_tokens=budget.max_total_tokens,
                        steps=budget.steps,
                    )
                    bus.emit(budget_event)
                    yield budget_event

        if metrics is not None and budget is not None:
            import os

            metrics.log(task_id, tokens_in=budget.tokens, tokens_out=0, usd=budget.tokens * 1e-6)
            metrics.check_daily_threshold(
                float(os.environ.get("MY_COWORK_DAILY_USD", "10")),
                bus,
            )

        if todo_rt.todos:
            todos = list(todo_rt.todos)
        need_pptx = wants_pptx(plan_ask)
        doc_ok = document_tools_succeeded(
            {"messages": run_messages},
            require_pptx=need_pptx,
        )
        if not doc_ok:
            doc_ok = has_office_deliverable(written_paths, require_pptx=need_pptx)
        scan_roots: list[Path] = []
        if workdir is not None:
            scan_roots.append(workdir)
        if frozen is not None and getattr(frozen, "space_root", None) is not None:
            space_root = Path(frozen.space_root)
            if all(space_root.resolve() != r.resolve() for r in scan_roots):
                scan_roots.append(space_root)
        if not doc_ok:
            extras: list[str] = []
            for root in scan_roots:
                try:
                    extras.extend(
                        list_new_deliverables(
                            root, min_mtime=run_started_at, already=written_paths
                        )
                    )
                except Exception:
                    continue
            doc_ok = has_office_deliverable(extras, require_pptx=need_pptx)
        claimed_missing = _missing_claimed_office_files(
            _last_ai_text(run_messages), workdir=workdir
        )
        can_complete = workers_ran > 0 and (
            not wants_document(plan_ask) or doc_ok or session_mode == "workforce"
        )
        if is_v2() and session_mode != "workforce" and can_complete:
            from app.runtime.v2.critic import heuristic_critic

            can_complete = heuristic_critic(plan_ask, run_messages).next == "answer"
        # For workforce, prefer subtask completion over mass-complete.
        if session_mode == "workforce" and todos:
            if all(t.get("status") == "completed" for t in todos):
                pass
            elif workers_ran > 0:
                todos = advance_todos(todos, complete_all=can_complete and doc_ok if wants_document(plan_ask) else can_complete)
            todo_rt.todos = todos
            done_plan = _event(task_id, "todo_state", agent_id=agent_id, todos=todos)
            bus.emit(done_plan)
            yield done_plan
        elif todos and can_complete:
            todos = advance_todos(todos, complete_all=True)
            todo_rt.todos = todos
            done_plan = _event(task_id, "todo_state", agent_id=agent_id, todos=todos)
            bus.emit(done_plan)
            yield done_plan
        elif todos:
            todo_rt.todos = todos
            plan_ev = _event(task_id, "todo_state", agent_id=agent_id, todos=todos)
            bus.emit(plan_ev)
            yield plan_ev

        end_status = "ok"
        end_extra: dict[str, Any] = {}
        # IM channels have no desktop confirm UI (AionUi YOLO). Keep the
        # agent reply instead of a "click Allow" harness error.
        if is_remote_channel() and wants_document(plan_ask) and (
            not doc_ok or claimed_missing
        ):
            last = _strip_think(_last_ai_text(run_messages))
            if last and not looks_like_workspace_dump(last) and not claimed_missing:
                end_extra["summary"] = last
            else:
                end_status = "error"
                end_extra["error"] = (
                    "未生成 PPTX 文件。"
                    if wants_pptx(plan_ask)
                    else "未生成文档文件。"
                )
        elif wants_document(plan_ask) and not doc_ok:
            end_status = "error"
            end_extra["error"] = (
                "未生成 PPTX 文件。请重试；若弹出写入确认，请点击允许。"
                if wants_pptx(plan_ask)
                else "未生成文档文件。请重试；若弹出写入确认，请点击允许。"
            )
        elif wants_document(plan_ask) and claimed_missing and not doc_ok:
            end_status = "error"
            shown = claimed_missing[0]
            end_extra["error"] = (
                f"回复中列出了交付文件，但磁盘上不存在：{shown}。"
                "请重试并真正写入文件；若弹出写入确认，请点击允许。"
            )
        if session_mode == "workforce":
            summary = ""
            if is_v2():
                last = _strip_think(_last_ai_text(run_messages))
                if last and not looks_like_workspace_dump(last):
                    summary = last
            if not summary:
                summary = resolve_workforce_end_summary(live_subtasks)
            if summary:
                end_extra["summary"] = summary
        elif is_v2():
            from app.runtime.v2.synthesize import best_user_facing_text

            last = _strip_think(
                best_user_facing_text(run_messages) or _last_ai_text(run_messages)
            )
            if last and not looks_like_workspace_dump(last):
                end_extra["summary"] = last
        for ev in _emit_graph_end(
            bus,
            task_id,
            end_status,
            workdir=workdir,
            written_paths=written_paths,
            min_mtime=run_started_at,
            extra_scan_roots=scan_roots[1:],
            **end_extra,
        ):
            yield ev
    except BudgetExhausted as exc:
        exhausted_event = _event(
            task_id,
            "budget.exhausted",
            error=str(exc),
            tokens=getattr(budget, "tokens", None),
            max_tokens=getattr(budget, "max_total_tokens", None),
        )
        bus.emit(exhausted_event)
        yield exhausted_event
        for ev in _emit_graph_end(
            bus,
            task_id,
            "error",
            workdir=workdir,
            written_paths=written_paths,
            min_mtime=run_started_at,
            error=str(exc),
        ):
            yield ev
        raise
    except (asyncio.CancelledError, Exception) as exc:
        if isinstance(exc, asyncio.CancelledError) or _cancelled():
            for ev in _emit_graph_end(
                bus,
                task_id,
                "cancelled",
                workdir=workdir,
                written_paths=written_paths,
                min_mtime=run_started_at,
            ):
                yield ev
            return
        for ev in _emit_graph_end(
            bus,
            task_id,
            "error",
            workdir=workdir,
            written_paths=written_paths,
            min_mtime=run_started_at,
            error=str(exc),
        ):
            yield ev
        raise
    finally:
        reset_todo_runtime(todo_token)
        if notes_token is not None:
            reset_notes_runtime(notes_token)
        if memory_token is not None:
            reset_long_term_runtime(memory_token)
        if workspace_token is not None:
            reset_workspace_runtime(workspace_token)
        if budget_token is not None:
            reset_budget_runtime(budget_token)
        reset_gongwen_format(gongwen_token)


def _serialize(value: Any) -> Any:
    try:
        messages = value.get("messages") if isinstance(value, dict) else None
        if messages:
            value = dict(value)
            value["messages"] = [_serialize_message(m) for m in messages]
        return value
    except Exception:
        return str(value)


def _serialize_message(message: Any) -> dict[str, Any]:
    return {
        "type": getattr(message, "type", message.__class__.__name__),
        "content": getattr(message, "content", str(message)),
        "tool_calls": getattr(message, "tool_calls", []) or [],
        "name": getattr(message, "name", None),
        "tool_call_id": getattr(message, "tool_call_id", None),
    }


def _tool_result_events(
    bus: Any,
    task_id: str,
    update: Any,
    *,
    agent_id: str | None = None,
    written_paths: set[str] | None = None,
    workdir: Path | None = None,
    min_mtime: float | None = None,
) -> list[dict[str, Any]]:
    """Emit ``tool.result`` for ToolMessages present in a graph update."""
    if not isinstance(update, dict):
        return []
    events: list[dict[str, Any]] = []
    for msg in update.get("messages") or []:
        mtype = getattr(msg, "type", None) or (
            msg.get("type") if isinstance(msg, dict) else None
        )
        # LangChain ToolMessage.type == "tool"; class name fallback for mocks.
        cls_name = msg.__class__.__name__ if not isinstance(msg, dict) else ""
        if mtype not in {"tool", "ToolMessage"} and cls_name != "ToolMessage":
            if not (isinstance(msg, dict) and msg.get("type") == "tool"):
                continue
        if isinstance(msg, dict):
            tool_name = str(msg.get("name") or "tool")
            call_id = str(msg.get("tool_call_id") or msg.get("id") or "")
            content = msg.get("content")
        else:
            tool_name = str(getattr(msg, "name", None) or "tool")
            call_id = str(
                getattr(msg, "tool_call_id", None) or getattr(msg, "id", "") or ""
            )
            content = getattr(msg, "content", None)
        result_text = content if isinstance(content, str) else str(content)
        if written_paths is not None:
            for m in _WROTE_PATH_RE.finditer(result_text):
                _track_path(written_paths, m.group("path"), workdir=workdir)
            for m in _ABS_FILE_RE.finditer(result_text):
                _track_path(written_paths, m.group("path"), workdir=workdir)
        # Successful docgen / write tools return a concrete path — surface as artifact
        # only when the file actually exists (avoid phantom chips from failed gens).
        candidate_paths: list[str] = []
        if tool_name in {
            "docx_gen",
            "pptx_gen",
            "xlsx_gen",
            "pdf_gen",
            "fs.write",
        } or result_text.strip().endswith(
            (".docx", ".pptx", ".xlsx", ".pdf", ".md", ".csv", ".html")
        ):
            candidate_paths.append(
                result_text.strip().splitlines()[-1]
                if result_text.strip()
                else result_text
            )
        # officecli via bash returns JSON; scrape absolute office paths from stdout.
        if tool_name in {"bash", "exec.bash"}:
            for m in _ABS_FILE_RE.finditer(result_text):
                p = m.group("path").strip().rstrip("`'\".,;:)")
                if p.lower().endswith(
                    (".pptx", ".docx", ".xlsx", ".ppt", ".doc", ".xls", ".pdf")
                ):
                    candidate_paths.append(p)

        seen_art: set[str] = set()
        for cand in candidate_paths:
            art = _emit_artifact_file(
                bus,
                task_id,
                agent_id or "tool",
                cand,
                workdir=workdir,
                written_paths=written_paths,
                min_mtime=min_mtime,
            )
            if not art:
                continue
            art_path = str(art.get("path") or "")
            if art_path in seen_art:
                continue
            seen_art.add(art_path)
            events.append(art)
            lower = art_path.lower()
            if lower.endswith((".pptx", ".docx", ".xlsx", ".ppt", ".doc", ".xls")):
                preview = _event(
                    task_id,
                    "preview.open",
                    kind="file",
                    path=art_path,
                    agent_id=agent_id,
                )
                bus.emit(preview)
                events.append(preview)
        if len(result_text) > 4000:
            result_text = result_text[:4000] + "…"
        ev = _event(
            task_id,
            "tool.result",
            call_id=call_id,
            tool=tool_name,
            result=result_text,
            agent_id=agent_id,
            payload={
                "call_id": call_id,
                "tool": tool_name,
                "result": result_text,
            },
        )
        bus.emit(ev)
        events.append(ev)
        # Surface bash stdout/stderr in the preview terminal for any worker.
        if agent_id and tool_name in {"bash", "exec.bash"}:
            assign_id = f"{task_id}:{agent_id}"
            term = _event(
                task_id,
                "agent.terminal",
                agent_id=agent_id,
                assign_id=assign_id,
                output=result_text,
            )
            bus.emit(term)
            events.append(term)
            preview = _event(
                task_id,
                "preview.open",
                kind="terminal",
                agent_id=agent_id,
                assign_id=assign_id,
            )
            bus.emit(preview)
            events.append(preview)
    return events

