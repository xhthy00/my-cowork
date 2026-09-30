"""Per-task todo runtime (Eigent ObservableTodoToolkit equivalent)."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class TodoRuntime:
    task_id: str
    bus: Any
    agent_id: str = "single_agent"
    todos: list[dict[str, Any]] = field(default_factory=list)
    plan_revision: int = 0
    substep_status: dict[str, dict[str, str]] = field(default_factory=dict)
    user_text: str = ""
    human_input_hub: Any = None
    source: str = "user"
    project_id: str | None = None
    space_id: str | None = None
    workspace: str | None = None
    memory_root: str | None = None
    assistant_id: str | None = None
    session_id: str | None = None
    resume_execution: bool = False
    automation_run_id: str | None = None
    automation_store: Any = None
    checkpoint_canonical_prefix: list[Any] | None = None
    checkpoint_outbound_prefix_len: int = 0


_todo_runtime: ContextVar[TodoRuntime | None] = ContextVar("todo_runtime", default=None)
_current_agent: ContextVar[str | None] = ContextVar("todo_current_agent", default=None)
_current_subtask: ContextVar[str | None] = ContextVar("todo_current_subtask", default=None)
_checkpoint_key: ContextVar[str | None] = ContextVar("automation_checkpoint_key", default=None)


def set_todo_runtime(runtime: TodoRuntime | None):
    return _todo_runtime.set(runtime)


def reset_todo_runtime(token) -> None:
    _todo_runtime.reset(token)


def get_todo_runtime() -> TodoRuntime | None:
    return _todo_runtime.get()


def get_current_agent_id() -> str | None:
    """Agent for this async branch, including parallel workforce workers."""
    return _current_agent.get()


def get_current_subtask_id() -> str | None:
    return _current_subtask.get()


@contextmanager
def todo_subtask_scope(subtask_id: str) -> Iterator[None]:
    token = _current_subtask.set(subtask_id)
    try:
        yield
    finally:
        _current_subtask.reset(token)


def get_automation_checkpoint_key() -> str | None:
    return _checkpoint_key.get()


@contextmanager
def automation_checkpoint_scope(key: str) -> Iterator[None]:
    token = _checkpoint_key.set(key)
    try:
        yield
    finally:
        _checkpoint_key.reset(token)


@contextmanager
def todo_agent_scope(agent_id: str) -> Iterator[None]:
    """Tag TraceBus events with the worker currently running (Eigent: per-agent log)."""
    token = _current_agent.set(agent_id)
    rt = get_todo_runtime()
    if rt is None:
        try:
            yield
        finally:
            _current_agent.reset(token)
        return
    prev = rt.agent_id
    rt.agent_id = agent_id
    try:
        yield
    finally:
        rt.agent_id = prev
        _current_agent.reset(token)
