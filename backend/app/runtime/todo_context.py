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
    user_text: str = ""


_todo_runtime: ContextVar[TodoRuntime | None] = ContextVar("todo_runtime", default=None)


def set_todo_runtime(runtime: TodoRuntime | None):
    return _todo_runtime.set(runtime)


def reset_todo_runtime(token) -> None:
    _todo_runtime.reset(token)


def get_todo_runtime() -> TodoRuntime | None:
    return _todo_runtime.get()


@contextmanager
def todo_agent_scope(agent_id: str) -> Iterator[None]:
    """Tag TraceBus events with the worker currently running (Eigent: per-agent log)."""
    rt = get_todo_runtime()
    if rt is None:
        yield
        return
    prev = rt.agent_id
    rt.agent_id = agent_id
    try:
        yield
    finally:
        rt.agent_id = prev
