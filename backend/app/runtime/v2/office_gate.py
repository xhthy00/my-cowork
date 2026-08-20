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
