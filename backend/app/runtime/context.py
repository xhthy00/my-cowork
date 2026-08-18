"""Build per-task runtime context (memory injection into prompts)."""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.memory.long_term import LongTermStore, extract_remember_content

# Cap prior turns so follow-ups stay in context without blowing the window.
_HISTORY_MAX_TURNS = 16
_HISTORY_MAX_CHARS = 8_000

_THINK_BLOCK_RE = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)
_THINK_OPEN_RE = re.compile(r"<think>[\s\S]*$", re.IGNORECASE)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_PLAN_MARKERS = (
    "i will generate",
    "i'll generate",
    "plan the task",
    "plan first",
    "load the document skill",
    "load_skill",
    "先规划",
    "先拆解",
    "将生成一份",
    "将生成",
    "我会生成",
    "计划如下",
    "先按规范",
)
_QUESTION_MARKERS = ("哪些", "什么", "如何", "为什么", "注意", "？", "?")
_WORKSPACE_DUMP_MARKERS_ZH = (
    "最终产出目录",
    "工作空间约束",
    "过程/临时文件",
)
_WORKSPACE_DUMP_MARKERS_EN = (
    "working directory",
    "final output directory",
    "preloaded_skill",
)
_FOLLOWUP_NOTE = (
    "This is a follow-up in an existing conversation. "
    "Answer the LATEST user message completely in Chinese in the message body. "
    "Do not stop after a plan or outline. "
    "Do not generate a .docx/.xlsx unless the user explicitly asked for a file. "
    "Files listed as [已生成文件] are already done — do not redo them unless asked."
)


def format_memory_block(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return ""
    lines = ["相关长期记忆："]
    for i, m in enumerate(memories, 1):
        lines.append(f"{i}. {m.get('content', '')}")
    return "\n".join(lines)


def strip_think_blocks(content: str) -> str:
    """Drop <think>…</think> (and unclosed think) so history is the formal answer."""
    text = _THINK_BLOCK_RE.sub("\n", content or "")
    text = _THINK_OPEN_RE.sub("\n", text)
    return text.replace("<think>", "").replace("</think>", "").strip()


def looks_like_workspace_dump(text: str) -> bool:
    """True when the model echoed harness/officecli status instead of a user reply."""
    blob = text or ""
    if any(marker in blob for marker in _WORKSPACE_DUMP_MARKERS_ZH):
        return True
    low = blob.lower()
    if any(marker in low for marker in _WORKSPACE_DUMP_MARKERS_EN):
        return True
    return "officecli" in low and "is ready" in low


def looks_like_plan_only(user_text: str, ai_text: str) -> bool:
    """True when the model stopped after a plan instead of answering."""
    body = strip_think_blocks(ai_text)
    if looks_like_workspace_dump(body):
        return True
    cjk = len(_CJK_RE.findall(body))
    if cjk >= 150:
        return False
    blob = f"{body}\n{ai_text}".lower()
    if any(marker in blob for marker in _PLAN_MARKERS):
        return True
    asked = any(token in (user_text or "") for token in _QUESTION_MARKERS)
    return asked and cjk < 80


def last_ai_text(messages: list[Any] | None) -> str:
    for msg in reversed(messages or []):
        role = (
            str(msg.get("type") or msg.get("role") or "")
            if isinstance(msg, dict)
            else str(getattr(msg, "type", None) or getattr(msg, "role", None) or "")
        )
        if role not in {"ai", "AIMessage", "assistant"}:
            continue
        content = (
            str(msg.get("content") or "")
            if isinstance(msg, dict)
            else str(getattr(msg, "content", None) or "")
        ).strip()
        if content:
            return content
    return ""


def _history_messages(
    history: list[dict[str, Any]] | None,
    *,
    current_text: str,
) -> list[Any]:
    """Convert prior chat turns to LangChain messages (excludes current user text)."""
    if not history:
        return []
    out: list[Any] = []
    current = (current_text or "").strip()
    turns = list(history)[-_HISTORY_MAX_TURNS:]
    for turn in turns:
        role = str(turn.get("role") or "").strip().lower()
        content = str(turn.get("content") or "").strip()
        if not content:
            continue
        if role in {"assistant", "ai"}:
            content = strip_think_blocks(content)
            if not content:
                continue
        if len(content) > _HISTORY_MAX_CHARS:
            content = content[:_HISTORY_MAX_CHARS] + "…"
        if role in {"user", "human"}:
            # Avoid duplicating the just-sent user message if the client included it.
            if content == current:
                continue
            out.append(HumanMessage(content=content))
        elif role in {"assistant", "ai"}:
            out.append(AIMessage(content=content))
    return out


def inject_memories(
    task_text: str,
    long_term: LongTermStore | None,
    *,
    k: int = 3,
    history: list[dict[str, Any]] | None = None,
) -> list[Any]:
    """Return initial chat messages with optional memory + conversation history."""
    messages: list[Any] = []
    if long_term is not None:
        # Persist 「记住 / 以后」 before querying so the same turn can recall it.
        remember = extract_remember_content(task_text)
        if remember:
            long_term.write(remember, kind="user_note")
        hits = long_term.query(task_text, k=k)
        block = format_memory_block(hits)
        if block:
            messages.append(SystemMessage(content=block))
    hist = _history_messages(history, current_text=task_text)
    if hist:
        messages.append(SystemMessage(content=_FOLLOWUP_NOTE))
        messages.extend(hist)
    messages.append(HumanMessage(content=task_text))
    return messages
