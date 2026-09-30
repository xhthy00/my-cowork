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


def notes_excerpt(*, limit: int = 4000) -> str:
    """Read shared notes for the coordinator without importing the tools layer."""
    rt = get_notes_runtime()
    if rt is None:
        return "(no notes runtime)"
    folder = rt.root / rt.task_id
    if not folder.is_dir():
        return "(no notes yet)"
    names = sorted(p.stem for p in folder.glob("*.md"))
    listing = "\n".join(names) if names else "(no notes yet)"
    parts = [f"list:\n{listing}"]
    for name in ("findings", "shared_files"):
        path = folder / f"{name}.md"
        if path.is_file():
            body = path.read_text(encoding="utf-8")
        else:
            body = f"(note {name!r} not found)"
        parts.append(f"{name}:\n{body}")
    blob = "\n\n".join(parts)
    return blob if len(blob) <= limit else blob[:limit]
