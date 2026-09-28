"""Compatibility imports; implementation lives in app.guardrails.office_gate."""

from app.guardrails.office_gate import (
    OFFICE_WRITE_REFUSE,
    is_office_skill,
    office_skills_allowed,
    set_office_skills_allowed,
    reset_office_skills_allowed,
    office_skills_scope,
    is_office_write_command,
    office_writes_blocked,
    office_path_blocked,
)
