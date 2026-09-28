"""Compatibility imports; implementation lives in app.task_support.todo_context."""

from app.task_support.todo_context import (
    TodoRuntime,
    set_todo_runtime,
    reset_todo_runtime,
    get_todo_runtime,
    get_current_agent_id,
    get_automation_checkpoint_key,
    automation_checkpoint_scope,
    todo_agent_scope,
)
