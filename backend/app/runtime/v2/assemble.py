"""Assemble v2 system + skill + memory + session transcript context."""

from __future__ import annotations

import platform
import re
from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.factory import load_prompt
from app.task_support.documents import wants_document, wants_pptx
from app.guardrails.office_gate import is_office_skill
from app.runtime.v2.session import load_thread
from app.task_support.workspace_context import get_workspace_runtime
from app.skills import find_skill

_SKILL_CAP = 32_000
_UNRELATED_SKIP = (
    "coding, UI, generating files, scheduling, or small talk"
)


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


def normalize_knowledge_bases(raw: Any) -> list[dict[str, str]]:
    """Keep {id,name,source} rows the composer sent; drop empty junk."""
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        kid = str(item.get("id") or item.get("knowledge_base_id") or "").strip()
        name = str(item.get("name") or "").strip()
        source = str(item.get("source") or "ima").strip() or "ima"
        if not kid and not name:
            continue
        key = kid or name
        if key in seen:
            continue
        seen.add(key)
        rows.append({"id": kid, "name": name or kid, "source": source})
        if len(rows) >= 8:
            break
    return rows


def format_bound_knowledge_block(raw: Any) -> str:
    """System block: bound libraries are the default search corpus."""
    rows = normalize_knowledge_bases(raw)
    if not rows:
        return ""
    lines = [
        "<bound_knowledge>",
        "The user bound these knowledge bases in the composer. For this turn,",
        "search them by default with ima_search_knowledge — do NOT wait for",
        "「在知识库里搜」or similar wording. Skip ima_list_knowledge_bases;",
        "use the knowledge_base_id below. Then ima_get_media_content and summarize.",
        "Do not start with web_search when these libraries can answer.",
        f"Skip only if the ask is clearly {_UNRELATED_SKIP}.",
        "Cite library names and document titles; never read ids aloud.",
    ]
    for row in rows:
        lines.append(
            f"- source={row['source']} name={row['name']} "
            f"knowledge_base_id={row['id']}"
        )
    lines.append("</bound_knowledge>")
    return "\n".join(lines)


def render_agent_prompt(name: str, **extra: str) -> str:
    placeholders = _env_placeholders()
    placeholders.update({k: str(v) for k, v in extra.items()})
    body = load_prompt(name, **placeholders)
    local = load_prompt("local_constraints", **placeholders)
    skills = load_prompt("skills_system", **placeholders)
    return f"{body.rstrip()}\n\n{skills.rstrip()}\n\n{local.rstrip()}\n"


def default_office_skill_ids(user_text: str) -> list[str]:
    """Preload officecli-* so the model does not fall back to pandoc."""
    if not wants_document(user_text):
        return []
    q = user_text or ""
    ids = ["officecli"]
    if wants_pptx(q):
        ids.append("officecli-pptx")
    elif re.search(r"xlsx|\bexcel\b|估算表|明细表|测算表", q, re.I):
        ids.append("officecli-xlsx")
    else:
        ids.append("officecli-docx")
    return ids


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
    knowledge_bases: list[dict[str, Any]] | None = None,
    long_term: Any = None,
    session_id: str | None = None,
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
    bound = format_bound_knowledge_block(knowledge_bases)
    if bound:
        messages.append(SystemMessage(content=bound))
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
    else:
        for sid in default_office_skill_ids(user_text):
            if sid not in skill_ids:
                skill_ids.append(sid)
    for sid in skill_ids:
        if not sid:
            continue
        messages.append(SystemMessage(content=_skill_block(sid)))
    if long_term is not None and hasattr(long_term, "prompt_block"):
        from app.memory.scoped import project_memory_key
        from app.task_support.todo_context import get_todo_runtime

        runtime = get_todo_runtime()
        workspace = project_memory_key(
            runtime.memory_root if runtime else None,
            runtime.project_id if runtime else None,
        )
        block = long_term.prompt_block(workspace=workspace, session_id=session_id)
        if block:
            messages.append(SystemMessage(content=block))
        settings = getattr(long_term, "memory_settings", None)
        if settings is not None and not settings.enabled:
            messages.append(SystemMessage(content=(
                "保存新记忆已关闭。你仍可使用已知记忆，但 remember、memory_update 和 "
                "memory_forget 无法写入；不要声称已记住新内容。"
            )))
        else:
            messages.append(SystemMessage(content=(
                "记忆：长期有效的用户偏好与纠正用 remember(scope='global') 保存；"
                "当前项目中无法从代码重建的事实用 scope='workspace'。"
                "用户明确要求记住时保存；模糊的一次性信息不要保存。"
                "健康、财务、关系、信仰等敏感信息先征得同意。"
                "已有相同记忆时用 memory_update，过时或错误时用 memory_forget；"
                "不要把代码、Git 历史或当前任务细节当作长期记忆。"
                "保存后在回复中简短告知用户。"
            )))
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
    knowledge_bases: list[dict[str, Any]] | None = None,
    long_term: Any = None,
    extra_placeholders: dict[str, str] | None = None,
    compact: Any | None = None,
) -> list[Any]:
    """System prefix + prior session tool-aware transcript + new user turn."""
    prefix = assemble_system_messages(
        agent_prompt_name=agent_prompt_name,
        assistant_id=assistant_id,
        enabled_skill_ids=enabled_skill_ids,
        knowledge_bases=knowledge_bases,
        long_term=long_term,
        session_id=session_id,
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
