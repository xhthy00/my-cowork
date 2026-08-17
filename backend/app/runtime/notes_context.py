"""Runtime context for shared notes (per task)."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path


@dataclass
class NotesRuntime:
    task_id: str
    root: Path


_notes_runtime: ContextVar[NotesRuntime | None] = ContextVar(
    "notes_runtime", default=None
)


def set_notes_runtime(runtime: NotesRuntime) -> Token:
    return _notes_runtime.set(runtime)


def reset_notes_runtime(token: Token) -> None:
    _notes_runtime.reset(token)


def get_notes_runtime() -> NotesRuntime | None:
    return _notes_runtime.get()
