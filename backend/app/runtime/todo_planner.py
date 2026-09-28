"""Todo list helpers matching Eigent ObservableTodoToolkit.

Eigent Single Agent does not pre-plan Progress. The executing agent calls
todo_write (schema: content / active_form / status). This module normalizes
that payload, filters Word/officecli steps when the user did not ask for
Office, and keeps a fallback list for tests / offline.

Workforce Progress is the confirmed subtask list, not this planner.
"""

from __future__ import annotations

from typing import Any

from app.task_support.todos import (
    _is_chinese,
    todos_match_user_language,
    normalize_todos,
    _to_active_form,
    parse_todos_json,
    fallback_todos,
    is_office_plan_text,
    without_office_todos,
    _markdown_file_todos,
    _drop_office_plan_if_chat,
    plan_todos,
    advance_todos,
    next_pending_id,
    pick_todo_for_worker,
    apply_todo_write,
)

TODO_WORKFLOW_RULES = None


def _todo_plan_system() -> str:
    global TODO_WORKFLOW_RULES
    if TODO_WORKFLOW_RULES is None:
        from app.agents.factory import load_prompt

        TODO_WORKFLOW_RULES = load_prompt("todo_planner") or ""
    return TODO_WORKFLOW_RULES


_PLAN_SYSTEM = None


def _plan_system() -> str:
    return _todo_plan_system()


async def plan_todos_llm(
    text: str,
    llm: Any | None,
    *,
    session_mode: str = "workforce",
    history: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Plan todos via LLM using Eigent todo_workflow rules."""
    q = (text or "").strip()
    if not q:
        return []
    if llm is None:
        return fallback_todos(q, session_mode=session_mode)

    lang_hint = (
        "重要：用户使用中文。content 与 active_form 必须全部是简体中文，禁止英文标题。"
        if _is_chinese(q)
        else "User wrote in English — use English titles."
    )
    context_bits: list[str] = []
    for turn in (history or [])[-4:]:
        role = str(turn.get("role") or "").strip().lower()
        content = str(turn.get("content") or "").strip()
        if not content or role not in {"user", "assistant", "human", "ai"}:
            continue
        label = "User" if role in {"user", "human"} else "Assistant"
        if len(content) > 1200:
            content = content[:1200] + "…"
        context_bits.append(f"{label}: {content}")
    context_block = ""
    if context_bits:
        context_block = (
            "Prior conversation (follow-up must continue this thread; do not re-ask known topic):\n"
            + "\n".join(context_bits)
            + "\n\n"
        )
    prompt = (
        f"Session mode: {session_mode}\n"
        f"{lang_hint}\n"
        f"{context_block}"
        f"User request:\n{q}\n\n"
        "Return the JSON todo array now."
    )

    async def _once(extra_system: str = "") -> list[dict[str, Any]]:
        system = _plan_system() + (("\n" + extra_system) if extra_system else "")
        if hasattr(llm, "ainvoke"):
            msg = await llm.ainvoke(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ]
            )
            content = getattr(msg, "content", None)
            if isinstance(content, list):
                content = "".join(
                    str(part.get("text", part)) if isinstance(part, dict) else str(part)
                    for part in content
                )
            return parse_todos_json(str(content or ""))
        if hasattr(llm, "invoke"):
            msg = llm.invoke(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ]
            )
            return parse_todos_json(str(getattr(msg, "content", "") or ""))
        return []

    try:
        todos = await _once()
        if todos and not todos_match_user_language(todos, q):
            todos = await _once(
                "上次输出语言错误。请用简体中文重写全部 content/active_form，不要出现英文步骤标题。"
            )
        if todos and todos_match_user_language(todos, q):
            return _drop_office_plan_if_chat(q, todos, session_mode=session_mode)
        if todos and not _is_chinese(q):
            return _drop_office_plan_if_chat(q, todos, session_mode=session_mode)
    except Exception:
        pass
    return fallback_todos(q, session_mode=session_mode)
