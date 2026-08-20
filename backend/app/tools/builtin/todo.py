"""Adapted from eigent: ObservableTodoToolkit.todo_write → SSE todo_state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.runtime.todo_context import get_todo_runtime
from app.runtime.todo_planner import apply_todo_write, without_office_todos
from app.runtime.v2.office_gate import office_skills_allowed


class TodoItemModel(BaseModel):
    content: str = Field(description="Brief actionable title (imperative).")
    active_form: str = Field(
        description="Present-continuous label shown while in progress."
    )
    status: str = Field(
        description='One of "pending", "in_progress", "completed".'
    )


class TodoWriteArgs(BaseModel):
    todos: list[TodoItemModel] = Field(
        description="Full ordered todo list to store (replaces previous list)."
    )


def _emit_todo_state(runtime, todos: list[dict[str, Any]]) -> None:
    event = {
        "task_id": runtime.task_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": runtime.agent_id,
        "todos": todos,
        "type": "todo_state",
    }
    runtime.bus.emit(event)


def todo_write(todos: list[dict[str, Any]] | list[TodoItemModel]) -> str:
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
    if not office_skills_allowed():
        filtered = without_office_todos(normalized)
        if len(filtered) < len(normalized):
            if not filtered:
                return (
                    "[ERROR] 当前任务是对话回答，不要规划 officecli / Word / 文档文件。"
                    "请改为检索、核对来源、在对话中回答。"
                )
            normalized = filtered
            runtime.todos = normalized
            _emit_todo_state(runtime, normalized)
            return (
                f"Updated todo list ({len(normalized)} items). "
                "Office/Word steps were dropped because this is a chat answer."
            )
    if not normalized:
        return "[ERROR] todo list is empty or invalid"
    runtime.todos = normalized
    _emit_todo_state(runtime, normalized)
    return f"Updated todo list ({len(normalized)} items)."


def make_todo_write_tool() -> StructuredTool:
    return StructuredTool.from_function(
        func=todo_write,
        name="todo_write",
        description=(
            "Create or update the Progress todo list before substantial work. "
            "Each todo needs content (imperative), active_form (present continuous), "
            "and status (pending|in_progress|completed). Mark exactly one in_progress."
        ),
        args_schema=TodoWriteArgs,
    )
