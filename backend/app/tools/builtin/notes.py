"""Shared note-taking toolkit (Eigent NoteTaking style, minimal)."""

from __future__ import annotations

import re
from pathlib import Path

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.runtime.notes_context import get_notes_runtime

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_\-.]+$")


def _dir() -> Path | None:
    rt = get_notes_runtime()
    if rt is None:
        return None
    path = rt.root / rt.task_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe(name: str) -> str | None:
    n = (name or "").strip()
    if not n or not _SAFE_NAME.match(n):
        return None
    return n


def list_note() -> str:
    """List note names for the current task."""
    d = _dir()
    if d is None:
        return "[ERROR] notes unavailable: no active task runtime"
    names = sorted(p.stem for p in d.glob("*.md"))
    if not names:
        return "(no notes yet)"
    return "\n".join(names)


class _ReadArgs(BaseModel):
    name: str = Field(description="Note name, e.g. shared_files")


def read_note(name: str) -> str:
    """Read a note by name."""
    d = _dir()
    if d is None:
        return "[ERROR] notes unavailable: no active task runtime"
    safe = _safe(name)
    if not safe:
        return "[ERROR] invalid note name"
    path = d / f"{safe}.md"
    if not path.is_file():
        return f"(note {safe!r} not found)"
    return path.read_text(encoding="utf-8")


class _CreateArgs(BaseModel):
    name: str = Field(description="Note name")
    content: str = Field(description="Initial note body")


def create_note(name: str, content: str) -> str:
    """Create or overwrite a note."""
    d = _dir()
    if d is None:
        return "[ERROR] notes unavailable: no active task runtime"
    safe = _safe(name)
    if not safe:
        return "[ERROR] invalid note name"
    path = d / f"{safe}.md"
    path.write_text(content or "", encoding="utf-8")
    return f"Created note {safe}"


class _AppendArgs(BaseModel):
    name: str = Field(description="Note name")
    content: str = Field(description="Text to append")


def append_note(name: str, content: str) -> str:
    """Append to a note (create if missing)."""
    d = _dir()
    if d is None:
        return "[ERROR] notes unavailable: no active task runtime"
    safe = _safe(name)
    if not safe:
        return "[ERROR] invalid note name"
    path = d / f"{safe}.md"
    prev = path.read_text(encoding="utf-8") if path.is_file() else ""
    sep = "" if not prev or prev.endswith("\n") else "\n"
    path.write_text(prev + sep + (content or "") + "\n", encoding="utf-8")
    return f"Appended to note {safe}"


def make_note_tools() -> list[StructuredTool]:
    return [
        StructuredTool.from_function(
            func=list_note,
            name="list_note",
            description="List shared note names for this task. Call before work.",
        ),
        StructuredTool.from_function(
            func=read_note,
            name="read_note",
            description="Read a shared note (e.g. shared_files).",
            args_schema=_ReadArgs,
        ),
        StructuredTool.from_function(
            func=create_note,
            name="create_note",
            description="Create or overwrite a shared note.",
            args_schema=_CreateArgs,
        ),
        StructuredTool.from_function(
            func=append_note,
            name="append_note",
            description="Append to a shared note (use shared_files for output paths).",
            args_schema=_AppendArgs,
        ),
    ]
