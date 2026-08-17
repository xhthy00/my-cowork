"""Eigent-aligned task split planner.

Eigent Single Agent does NOT use keyword heuristics. It follows CAMEL TodoToolkit:
  - schema: content / active_form / status (pending|in_progress|completed)
  - prompt: <todo_workflow> — call todo_write before substantial work
  - wire: todo_state with id todo_1..N

This module plans via LLM with the same workflow rules, then falls back to a
minimal generic list only when the model is unavailable.
"""

from __future__ import annotations

import json
import re
from typing import Any

# Adapted from eigent: backend/app/agent/prompt.py — SINGLE_AGENT_SYS_PROMPT <todo_workflow>
TODO_WORKFLOW_RULES = """
<todo_workflow>
- For any multi-step task, produce a todo list before doing substantial work.
- Keep todos short and actionable (imperative titles).
- Mark exactly one todo as in_progress while actively working on it.
- Mark a todo completed immediately after it is done.
- Update todos when the plan changes.
- For simple conversational answers, a todo list is optional (return []).
</todo_workflow>

Each todo MUST have:
- content: brief actionable title (imperative), e.g. "Research filing policy"
- active_form: present-continuous UI label, e.g. "Researching filing policy"
- status: one of "pending" | "in_progress" | "completed"
"""

_PLAN_SYSTEM = f"""你是 Eigent 风格的任务规划器，负责生成右侧 Progress 步骤列表。
请严格遵循下列规则拆分用户请求：

{TODO_WORKFLOW_RULES}

输出要求：
- 只输出 JSON 数组，不要 markdown 代码块，不要解释。
- **语言强制**：若用户请求含中文，则每条 todo 的 content 与 active_form 必须全部使用简体中文，禁止英文单词作标题。
- 若用户请求是英文，则用英文。
- 多步任务通常 3–6 步，短小可执行；简单寒暄可返回 []。
- active_form 用进行时，例如 content「检索恩施景点」→ active_form「正在检索恩施景点」。
"""


def _is_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _todos_match_user_language(todos: list[dict[str, Any]], user_text: str) -> bool:
    if not todos:
        return True
    if not _is_chinese(user_text):
        return True
    # Require majority of contents to contain Chinese
    zh = sum(1 for t in todos if _is_chinese(str(t.get("content") or "")))
    return zh >= max(1, (len(todos) + 1) // 2)


def normalize_todos(raw: Any) -> list[dict[str, Any]]:
    """Normalize to Eigent serialized_todos shape; enforce one in_progress."""
    if not isinstance(raw, list):
        return []

    todos: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        active = str(item.get("active_form") or item.get("activeForm") or "").strip()
        if not active:
            active = _to_active_form(content)
        status = str(item.get("status") or "pending").strip().lower()
        if status not in ("pending", "in_progress", "completed"):
            status = "pending"
        todos.append(
            {
                "id": f"todo_{index}",
                "content": content,
                "active_form": active,
                "status": status,
            }
        )

    if not todos:
        return []

    # Exactly one in_progress (Eigent rule); prefer first non-completed.
    in_prog = [t for t in todos if t["status"] == "in_progress"]
    if len(in_prog) == 0:
        for t in todos:
            if t["status"] != "completed":
                t["status"] = "in_progress"
                break
    elif len(in_prog) > 1:
        keep = in_prog[0]["id"]
        for t in todos:
            if t["status"] == "in_progress" and t["id"] != keep:
                t["status"] = "pending"
    return todos


def _to_active_form(content: str) -> str:
    """Best-effort present-continuous for Chinese / English titles."""
    c = content.strip()
    if not c:
        return c
    # Chinese: prefix 正在 if not already
    if re.search(r"[\u4e00-\u9fff]", c):
        if c.startswith("正在"):
            return c
        return f"正在{c}"
    # English: naive -ing
    lower = c[0].lower() + c[1:] if c else c
    first, *rest = lower.split(" ", 1)
    if first.endswith("e") and not first.endswith("ee"):
        first = first[:-1] + "ing"
    elif not first.endswith("ing"):
        first = first + "ing"
    return (first + (" " + rest[0] if rest else "")).capitalize()


def parse_todos_json(text: str) -> list[dict[str, Any]]:
    """Extract JSON array from model output."""
    raw = (text or "").strip()
    if not raw:
        return []
    # Strip markdown fences
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()
    # Find array bounds
    start = raw.find("[")
    end = raw.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return []
    return normalize_todos(data)


def fallback_todos(text: str, *, session_mode: str = "workforce") -> list[dict[str, Any]]:
    """Minimal generic plan when LLM is unavailable — NOT a fixed domain template."""
    q = (text or "").strip()
    if not q:
        return []
    # Simple conversational → no todos (Eigent rule)
    if len(q) < 8 and not any(ch in q for ch in ("写", "生成", "做", "帮", "create", "write", "make")):
        return []
    if session_mode == "single-agent":
        steps = [
            ("Break down the user request", "Breaking down the user request"),
            ("Execute the main work", "Executing the main work"),
            ("Deliver the result", "Delivering the result"),
        ]
        if re.search(r"[\u4e00-\u9fff]", q):
            steps = [
                ("拆解用户需求", "正在拆解用户需求"),
                ("执行主要工作", "正在执行主要工作"),
                ("交付结果", "正在交付结果"),
            ]
    else:
        steps = [
            ("Assign workers", "Assigning workers"),
            ("Execute subtasks", "Executing subtasks"),
            ("Summarize results", "Summarizing results"),
        ]
        if re.search(r"[\u4e00-\u9fff]", q):
            steps = [
                ("分配合适的 Worker", "正在分配 Worker"),
                ("执行子任务", "正在执行子任务"),
                ("汇总结果", "正在汇总结果"),
            ]
    raw = [
        {
            "content": c,
            "active_form": a,
            "status": "in_progress" if i == 0 else "pending",
        }
        for i, (c, a) in enumerate(steps)
    ]
    return normalize_todos(raw)


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
        system = _PLAN_SYSTEM + (("\n" + extra_system) if extra_system else "")
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
        if todos and not _todos_match_user_language(todos, q):
            todos = await _once(
                "上次输出语言错误。请用简体中文重写全部 content/active_form，不要出现英文步骤标题。"
            )
        if todos and _todos_match_user_language(todos, q):
            return todos
        if todos and not _is_chinese(q):
            return todos
    except Exception:
        pass
    return fallback_todos(q, session_mode=session_mode)


# Back-compat sync entry used by tests / offline
def plan_todos(text: str, *, session_mode: str = "workforce") -> list[dict[str, Any]]:
    return fallback_todos(text, session_mode=session_mode)


def advance_todos(
    todos: list[dict[str, Any]],
    *,
    mark_completed_ids: list[str] | None = None,
    next_in_progress_id: str | None = None,
    complete_all: bool = False,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    done_ids = set(mark_completed_ids or [])
    for t in todos:
        item = dict(t)
        if complete_all or item["id"] in done_ids:
            item["status"] = "completed"
        elif next_in_progress_id and item["id"] == next_in_progress_id:
            item["status"] = "in_progress"
        elif (
            next_in_progress_id
            and item["status"] == "in_progress"
            and item["id"] != next_in_progress_id
        ):
            item["status"] = "completed"
        out.append(item)
    return normalize_todos(out) if out else out


def next_pending_id(todos: list[dict[str, Any]]) -> str | None:
    for t in todos:
        if t.get("status") == "pending":
            return str(t["id"])
    for t in todos:
        if t.get("status") == "in_progress":
            return str(t["id"])
    return None


def pick_todo_for_worker(todos: list[dict[str, Any]], worker: str) -> str | None:
    """Advance plan sequentially when workers run (no keyword domain templates)."""
    _ = worker
    return next_pending_id(todos) or next(
        (str(t["id"]) for t in todos if t.get("status") == "in_progress"),
        None,
    )


def apply_todo_write(todos_input: Any) -> list[dict[str, Any]]:
    """Eigent todo_write semantics: replace full ordered list."""
    return normalize_todos(todos_input)
