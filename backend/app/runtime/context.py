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
_THINK_TAG_RE = re.compile(r"</?think(?:ing)?>", re.IGNORECASE)
_ORPHAN_CLOSE_THINK_RE = re.compile(r"^[\s\S]*?</think(?:ing)?>", re.IGNORECASE)
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
    "操作记录",
    "交付摘要",
    "文件规格",
    "schema 校验",
)
_WORKSPACE_DUMP_MARKERS_EN = (
    "working directory",
    "final output directory",
    "preloaded_skill",
    "page layout",
    "pagebreakbefore",
    "fldchar",
)
_INTERNAL_TRACE_MARKERS = (
    "paraId",
    "para_id",
    "Heading1",
    "Heading2",
    "Heading3",
    "001000",
)
_PROCESS_NARRATION_RE = re.compile(
    r"(Now let me |Let me (?:add|set|close|build|create|set up|convert|fix|update|write)|"
    r"I notice |I need to |I'll (?:need|convert|fix|update|write)|"
    r"Unicode escape|"
    r"page layout|pageBreakBefore|fldChar|schema 校验|交付摘要|"
    r"文件规格|Word 版.{0,16}已写入|通过 schema|"
    r"我来用\s*officecli|生成正式的\s*Word|生成\s*Word\s*文档)",
    re.IGNORECASE,
)
_PREAMBLE_RE = re.compile(
    r"(我先搜|先并行搜索|让我(?:再|来|获取|补充)|正在检索|"
    r"Now let me |Let me |I notice |I need to )",
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
    """Drop <think>…</think> (and MiniMax orphan </think>) so history is the formal answer."""
    text = content or ""
    # AionUI MiniMax: reasoning then a lone </think> before the answer.
    if not re.search(r"<think\b", text, re.I) and re.search(r"</think", text, re.I):
        text = _ORPHAN_CLOSE_THINK_RE.sub("\n", text, count=1)
    text = _THINK_BLOCK_RE.sub("\n", text)
    text = _THINK_OPEN_RE.sub("\n", text)
    text = _THINK_TAG_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def looks_like_workspace_dump(text: str) -> bool:
    """True when the model echoed harness/officecli internals instead of a user reply."""
    blob = text or ""
    if any(marker in blob for marker in _WORKSPACE_DUMP_MARKERS_ZH):
        return True
    if any(marker in blob for marker in _INTERNAL_TRACE_MARKERS):
        return True
    low = blob.lower()
    if any(marker in low for marker in _WORKSPACE_DUMP_MARKERS_EN):
        return True
    if "transcript" in low and any(
        token in blob for token in ("可见", "操作", "tool", "Heading", "paraId")
    ):
        return True
    return "officecli" in low and "is ready" in low


def looks_like_process_narration(text: str) -> bool:
    """True for officecli / layout chatter that must not be the chat answer."""
    body = strip_think_blocks(text or "")
    if not body:
        return False
    if looks_like_workspace_dump(body):
        return True
    return bool(_PROCESS_NARRATION_RE.search(body))


def is_user_facing_answer(text: str) -> bool:
    """True when *text* is a real chat answer, not a tool preamble or file log."""
    body = strip_think_blocks(text or "")
    if not body or looks_like_process_narration(body):
        return False
    cjk = len(_CJK_RE.findall(body))
    if _PREAMBLE_RE.search(body) and cjk < 80:
        return False
    return bool(body.strip())


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
    # Chinese question answered only in short English (no CJK) is not an answer.
    asked = any(token in (user_text or "") for token in _QUESTION_MARKERS)
    if asked and cjk < 20 and body.strip() and not _CJK_RE.search(body):
        return True
    return False


def last_ai_text(messages: list[Any] | None) -> str:
    from app.agents.sanitize import strip_model_junk

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
        )
        content = strip_model_junk(content).strip()
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
        if getattr(long_term, "semantic_enabled", True):
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
