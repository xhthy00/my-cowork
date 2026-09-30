"""Per-turn gate: office skills are opt-in (AionUi Cowork / Word Creator split).

Research and chat turns must not see officecli-* in list_skills or preloaded
skill bodies. Document turns (wants_document) keep the full catalog.
"""

from __future__ import annotations

import contextvars
import re
from collections.abc import Iterator
from contextlib import contextmanager

_OFFICE_SKILL_RE = re.compile(
    r"officecli|pitch-deck|word-form|official-document",
    re.IGNORECASE,
)
_OFFICE_EXACT = frozenset({"docx", "pptx", "xlsx", "ppt", "doc"})

_office_skills_allowed: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "office_skills_allowed", default=True
)

OFFICE_WRITE_REFUSE = (
    "[ERROR] The user asked for Markdown (.md) or a chat answer, not an Office file. "
    "Do not run officecli or write .docx/.pptx/.xlsx/.pdf. "
    "If they asked for .md, use fs_write and stop."
)

_OFFICE_WRITE_CMD_RE = re.compile(
    r"\bofficecli(?:\.exe)?\s+(create|add|set|batch|save|close|remove|move|swap)\b",
    re.IGNORECASE,
)
_OFFICE_EXT_RE = re.compile(r"\.(docx?|pptx?|xlsx|pdf)\b", re.IGNORECASE)
_OFFICE_SAVE_RE = re.compile(
    r"\b(create|write|save|document|openpyxl|pptxgen)\b",
    re.IGNORECASE,
)


def is_office_skill(skill_id: str) -> bool:
    key = (skill_id or "").strip()
    if not key:
        return False
    if key.lower() in _OFFICE_EXACT:
        return True
    return bool(_OFFICE_SKILL_RE.search(key))


def office_skills_allowed() -> bool:
    return bool(_office_skills_allowed.get())


def set_office_skills_allowed(allowed: bool) -> contextvars.Token[bool]:
    return _office_skills_allowed.set(bool(allowed))


def reset_office_skills_allowed(token: contextvars.Token[bool]) -> None:
    _office_skills_allowed.reset(token)


@contextmanager
def office_skills_scope(allowed: bool) -> Iterator[None]:
    token = set_office_skills_allowed(allowed)
    try:
        yield
    finally:
        reset_office_skills_allowed(token)


def is_office_write_command(cmd: str) -> bool:
    """True for officecli mutating verbs or scripts that save Office files."""
    q = cmd or ""
    if _OFFICE_WRITE_CMD_RE.search(q):
        return True
    return bool(_OFFICE_EXT_RE.search(q) and _OFFICE_SAVE_RE.search(q))


def office_writes_blocked(user_text: str | None = None) -> bool:
    """Block Word/PPT/Excel writes when office skills are gated or the user asked only for Markdown."""
    if not office_skills_allowed():
        return True
    text = user_text
    if text is None:
        from app.runtime.todo_context import get_todo_runtime

        rt = get_todo_runtime()
        text = rt.user_text if rt is not None else ""
    if not text:
        return False
    from app.graphs.routing import markdown_only

    return markdown_only(text)


def office_path_blocked(path: str) -> bool:
    return office_writes_blocked() and bool(_OFFICE_EXT_RE.search(path or ""))
