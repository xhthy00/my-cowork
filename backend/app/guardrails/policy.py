"""Skill-level policy guardrails."""

from collections.abc import Mapping
from fnmatch import fnmatch
from typing import Any


def check_tool_allowed(skill_meta: Mapping[str, Any] | object, tool_name: str) -> bool:
    """Return ``True`` if *tool_name* is allowed by the skill whitelist.

    *skill_meta* is expected to provide ``allowed_tools`` as a list of glob-style
    patterns (e.g. ``mcp.github.*``). A missing or empty whitelist denies all
    tools.
    """
    allowed_tools: list[str] | None = None
    if isinstance(skill_meta, Mapping):
        allowed_tools = skill_meta.get("allowed_tools")
    else:
        allowed_tools = getattr(skill_meta, "allowed_tools", None)

    if not allowed_tools:
        return False

    return any(fnmatch(tool_name, pattern) for pattern in allowed_tools)


def _tool_requires_confirm(tool_pattern: str) -> bool:
    """Heuristic: fs/exec/docgen writes need a desktop confirm gate."""
    lower = tool_pattern.lower()
    markers = (
        "fs.write",
        "fs.",
        ".fs.",
        "exec.",
        ".exec.",
        "docx",
        "pptx",
        "xlsx",
        "pdf.gen",
        "pdf_gen",
    )
    # bare "fs" / "exec" segments in dotted names
    parts = lower.replace("*", "").split(".")
    if any(p in ("fs", "exec") for p in parts if p):
        return True
    return any(m in lower for m in markers)


def skill_usable_via_remote(skill_meta: Mapping[str, Any] | object) -> bool:
    """Return ``True`` if the skill can run from Feishu without desktop confirm.

    Skills that whitelist confirm-gated tools (fs/exec/docgen) must run in the
    desktop client where ConfirmHub can pop a modal. Bundled office example
    skills (docx/pptx/xlsx/pdf) are always desktop-only.
    """
    if isinstance(skill_meta, Mapping):
        skill_id = str(skill_meta.get("id") or skill_meta.get("name") or "")
        allowed = list(skill_meta.get("allowed_tools") or [])
    else:
        skill_id = str(getattr(skill_meta, "id", "") or getattr(skill_meta, "name", "") or "")
        allowed = list(getattr(skill_meta, "allowed_tools", None) or [])
    if skill_id.lower() in {"docx", "pptx", "xlsx", "pdf"}:
        return False
    if not allowed:
        return True
    return not any(_tool_requires_confirm(t) for t in allowed)
