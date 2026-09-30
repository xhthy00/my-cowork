"""Adapted from eigent: ObservableTodoToolkit.todo_write → SSE todo_state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.task_support.todo_context import get_todo_runtime, get_current_agent_id, get_current_subtask_id
from app.task_support.todos import (
    apply_todo_write,
    reconcile_todos,
    todos_match_user_language,
    without_office_todos,
)
from app.guardrails.office_gate import office_skills_allowed


class TodoSubstepModel(BaseModel):
    content: str = Field(description="Short, actionable substep title.")
    active_form: str = Field(default="", description="Optional in-progress label.")
    status: str = Field(default="pending", description='pending|in_progress|completed')


class TodoItemModel(BaseModel):
    content: str = Field(
        description=(
            "Brief actionable title. If the user wrote in Chinese, this MUST be "
            "Simplified Chinese (e.g. 加载 officecli 技能), never English-only "
            "titles like 'Loading officecli skill'."
        )
    )
    active_form: str = Field(
        description=(
            "In-progress UI label. Chinese users: 「正在…」. "
            "Do not use English present-continuous titles."
        )
    )
    status: str = Field(
        description='One of "pending", "in_progress", "completed".'
    )
    substeps: list[TodoSubstepModel] = Field(
        default_factory=list,
        description="2–4 concrete substeps for this global step when known.",
    )


class TodoWriteArgs(BaseModel):
    todos: list[TodoItemModel] = Field(
        description="Full ordered todo list to store (replaces previous list)."
    )
    revision_reason: str = Field(
        default="",
        description="Explain a genuine change to global step titles or structure; omit for status updates.",
    )


class SubstepUpdateArgs(BaseModel):
    index: int = Field(description="One-based index of a planned substep under the assigned task.")
    status: str = Field(description='"in_progress", "completed", or "failed".')


def _emit_todo_state(runtime, todos: list[dict[str, Any]], *, changed: bool = False, reason: str = "") -> None:
    event = {
        "task_id": runtime.task_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": get_current_agent_id() or runtime.agent_id,
        "todos": todos,
        "revision": runtime.plan_revision,
        "plan_changed": changed,
        "revision_reason": reason,
        "type": "todo_state",
    }
    runtime.bus.emit(event)


def todo_write(
    todos: list[dict[str, Any]] | list[TodoItemModel],
    revision_reason: str = "",
) -> str:
    """Create or update the current task todo list (Eigent TodoToolkit).

    For any multi-step task, call this before substantial work. Keep todos
    short and actionable. Mark exactly one todo as in_progress.
    """
    runtime = get_todo_runtime()
    if runtime is None:
        return "[ERROR] todo_write unavailable: no active task runtime"

    raw: list[Any] = []
    for item in todos:
        if isinstance(item, TodoItemModel):
            raw.append(item.model_dump())
        elif isinstance(item, dict):
            raw.append(item)
        else:
            raw.append(dict(item))  # type: ignore[arg-type]

    normalized = apply_todo_write(raw)
    if not todos_match_user_language(normalized, runtime.user_text):
        return (
            "[ERROR] 用户使用中文。每条 todo 的 content 与 active_form 必须是简体中文，"
            "禁止英文步骤标题（例如 Loading officecli skill）。请用中文重写全部 todos 后再调用。"
        )
    from app.task_support.documents import wants_document, wants_markdown_file

    md_only = wants_markdown_file(runtime.user_text) and not wants_document(
        runtime.user_text
    )
    if (not office_skills_allowed()) or md_only:
        filtered = without_office_todos(normalized)
        if len(filtered) < len(normalized):
            if not filtered:
                return (
                    "[ERROR] 用户只要 Markdown / 对话回答，不要规划 officecli / Word。"
                    "请改为写入 .md 或在对话中回答。"
                )
            normalized = filtered
            normalized, changed = reconcile_todos(runtime.todos, normalized, revision_reason=revision_reason)
            runtime.plan_revision += int(changed)
            runtime.todos = normalized
            _emit_todo_state(runtime, normalized, changed=changed, reason=revision_reason)
            return (
                f"Updated todo list ({len(normalized)} items). "
                "Office/Word steps were dropped because this is not a Word task."
            )
    if not normalized:
        return "[ERROR] todo list is empty or invalid"
    normalized, changed = reconcile_todos(runtime.todos, normalized, revision_reason=revision_reason)
    runtime.plan_revision += int(changed)
    runtime.todos = normalized
    _emit_todo_state(runtime, normalized, changed=changed, reason=revision_reason)
    return f"Updated todo list ({len(normalized)} items)."


def make_todo_write_tool() -> StructuredTool:
    return StructuredTool.from_function(
        func=todo_write,
        name="todo_write",
        description=(
            "Create or update the Progress todo list before substantial work. "
            "Each todo needs content, active_form, and status "
            "(pending|in_progress|completed). Mark exactly one in_progress. "
            "Include 2–4 substeps for each global step when useful, and update their statuses. "
            "Keep existing titles stable; use revision_reason when genuinely changing the plan. "
            "If the user wrote in Chinese, content and active_form MUST be "
            "Simplified Chinese — never English titles."
        ),
        args_schema=TodoWriteArgs,
    )


def substep_update(index: int, status: str) -> str:
    """Report one worker substep without rewriting the global workforce plan."""
    runtime = get_todo_runtime()
    parent_id = get_current_subtask_id()
    if runtime is None or not parent_id:
        return "[ERROR] substep_update is available only inside an assigned workforce task"
    parent = next((row for row in runtime.todos if str(row.get("id")) == parent_id), None)
    children = list(parent.get("substeps") or []) if parent else []
    if index < 1 or index > len(children):
        return f"[ERROR] substep index must be between 1 and {len(children)}"
    if status not in {"in_progress", "completed", "failed"}:
        return "[ERROR] status must be in_progress, completed, or failed"
    child = children[index - 1]
    substep_id = str(child["id"])
    runtime.substep_status.setdefault(parent_id, {})[substep_id] = status
    runtime.bus.emit({
        "type": "substep_state",
        "task_id": runtime.task_id,
        "agent_id": get_current_agent_id() or runtime.agent_id,
        "parent_id": parent_id,
        "substep_id": substep_id,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    return f"Updated substep {index} to {status}."


def make_substep_update_tool() -> StructuredTool:
    return StructuredTool.from_function(
        func=substep_update,
        name="substep_update",
        description="Update the status of a planned substep in your assigned workforce task. "
                    "Call when starting and completing a concrete substep; use its one-based index.",
        args_schema=SubstepUpdateArgs,
    )
