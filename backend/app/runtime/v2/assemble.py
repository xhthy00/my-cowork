"""Assemble v2 system + skill + memory + session transcript context."""

from __future__ import annotations

import platform
from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.factory import load_prompt
from app.graphs.routing import wants_document
from app.runtime.context import format_memory_block
from app.runtime.v2.office_gate import is_office_skill
from app.runtime.v2.session import load_thread
from app.runtime.workspace_context import get_workspace_runtime
from app.skills import find_skill

_SKILL_CAP = 32_000


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:00")


def _path_hints() -> str:
    from pathlib import Path

    from app.sandbox.path_guard import desktop_dir

    home = Path.home()
    desk = desktop_dir()
    return (
        f"- User home: `{home}`\n"
        f"- Desktop (only if the user explicitly asks): `{desk}`\n"
        f"- Default: write deliverables under the task working directory "
        f"injected in each run (see [工作空间约束])."
    )


def _env_placeholders() -> dict[str, str]:
    rt = get_workspace_runtime()
    workdir = str(rt.working_directory) if rt is not None else "."
    return {
        "platform_system": platform.system(),
        "platform_machine": platform.machine(),
        "working_directory": workdir,
        "now_str": _now_str(),
        "path_hints": _path_hints(),
        "external_browser_notice": "",
        "user_text": "",
        "deps": "",
        "task_id": "",
        "content": "",
        "subtasks": "",
        "notes": "",
        "transcript": "",
        "blob": "",
    }


def render_agent_prompt(name: str, **extra: str) -> str:
    placeholders = _env_placeholders()
    placeholders.update({k: str(v) for k, v in extra.items()})
    body = load_prompt(name, **placeholders)
    local = load_prompt("local_constraints", **placeholders)
    skills = load_prompt("skills_system", **placeholders)
    return f"{body.rstrip()}\n\n{skills.rstrip()}\n\n{local.rstrip()}\n"


def _skill_block(skill_id: str) -> str:
    meta = find_skill(skill_id)
    if meta is None or not meta.prompt:
        return f"[skill:{skill_id} — not found on disk]"
    from app.skills import format_loaded_skill

    body = format_loaded_skill(meta)
    if len(body) > _SKILL_CAP:
        listing = ""
        base = meta.base_dir
        if base is not None and base.is_dir():
            names = [p.name for p in sorted(base.iterdir()) if not p.name.startswith(".")]
            listing = "\n".join(f"- {n}" for n in names[:40])
        body = (
            body[:_SKILL_CAP]
            + "\n…(truncated; read remaining files from Base directory)\n"
            + listing
        )
    return f'<preloaded_skill name="{skill_id}">\n{body}\n</preloaded_skill>'


def assemble_system_messages(
    *,
    agent_prompt_name: str = "single_agent",
    assistant_id: str | None = None,
    enabled_skill_ids: list[str] | None = None,
    long_term: Any = None,
    user_text: str = "",
    extra_placeholders: dict[str, str] | None = None,
) -> list[Any]:
    """Build the durable system prefix for a v2 run (not truncated history)."""
    if long_term is None:
        from app.runtime.memory_context import get_long_term_runtime

        long_term = get_long_term_runtime()
    messages: list[Any] = [
        SystemMessage(
            content=render_agent_prompt(
                agent_prompt_name, **(extra_placeholders or {})
            )
        )
    ]
    if assistant_id:
        from app.assistants import get_assistant

        assistant = get_assistant(assistant_id)
        rules = str((assistant or {}).get("rules") or "").strip()
        if rules:
            messages.append(
                SystemMessage(
                    content=f'<assistant_rules id="{assistant_id}">\n{rules}\n</assistant_rules>'
                )
            )
    skill_ids = list(enabled_skill_ids or [])
    if user_text and not wants_document(user_text):
        skill_ids = [sid for sid in skill_ids if not is_office_skill(sid)]
    for sid in skill_ids:
        if not sid:
            continue
        messages.append(SystemMessage(content=_skill_block(sid)))
    if long_term is not None:
        from app.memory.long_term import extract_remember_content

        remember = extract_remember_content(user_text)
        if remember:
            try:
                long_term.write(remember, kind="user_note")
            except Exception:
                pass
        if getattr(long_term, "semantic_enabled", False):
            try:
                hits = long_term.query(user_text, k=3)
            except Exception:
                hits = []
            block = format_memory_block(hits)
            if block:
                messages.append(SystemMessage(content=block))
    # MiniMax (and other strict OpenAI-compat APIs) reject multiple `system`
    # messages with 400 / 2013. Keep a single leading system block.
    if len(messages) <= 1:
        return messages
    parts = [str(m.content).strip() for m in messages if str(getattr(m, "content", "") or "").strip()]
    return [SystemMessage(content="\n\n".join(parts))]


def assemble_messages(
    *,
    user_text: str,
    session_id: str | None,
    agent_prompt_name: str = "single_agent",
    assistant_id: str | None = None,
    enabled_skill_ids: list[str] | None = None,
    long_term: Any = None,
    extra_placeholders: dict[str, str] | None = None,
    compact: Any | None = None,
) -> list[Any]:
    """System prefix + prior session tool-aware transcript + new user turn."""
    prefix = assemble_system_messages(
        agent_prompt_name=agent_prompt_name,
        assistant_id=assistant_id,
        enabled_skill_ids=enabled_skill_ids,
        long_term=long_term,
        user_text=user_text,
        extra_placeholders=extra_placeholders,
    )
    prior: list[Any] = []
    if session_id:
        prior = [
            m
            for m in load_thread(session_id)
            if not isinstance(m, SystemMessage)
        ]
    if compact is not None and prior:
        prior = compact(prior)
    return [*prefix, *prior, HumanMessage(content=user_text)]
