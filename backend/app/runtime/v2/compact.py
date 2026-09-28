"""Tool-aware context compaction (v2)."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from app.agents.factory import load_prompt
from app.llm.token_counter import count_tokens
from app.runtime.compressor import DEFAULT_THRESHOLD, KEEP_LAST, SummarizeFn
from app.llm.budget_context import context_window_limit

KEEP_FULL_TURNS = 3
COMPACTION_CAP_TOKENS = 250_000


def _is_human(msg: Any) -> bool:
    role = str(getattr(msg, "type", None) or getattr(msg, "role", None) or "")
    return role in {"human", "user", "HumanMessage"} and not _text(msg).startswith("[Instruction]")


def _text(msg: Any) -> str:
    content = getattr(msg, "content", None)
    if isinstance(content, str):
        return content
    return str(content or "")[:400]


def _summarize_tools(messages: list[Any]) -> str:
    lines: list[str] = ["Earlier work (compacted):"]
    searches: list[str] = []
    files: list[str] = []
    for msg in messages:
        name = str(getattr(msg, "name", "") or "")
        body = _text(msg)
        if name in {"web_search", "web_fetch"} or "http" in body[:200]:
            searches.append(body[:400])
        if isinstance(msg, ToolMessage) or name:
            for token in body.split():
                if token.startswith("/") and "." in token:
                    files.append(token.strip("`'\".,;:"))
    if searches:
        lines.append("Sources / search:")
        lines.extend(f"- {s}" for s in searches[-8:])
    if files:
        lines.append("Files:")
        lines.extend(f"- {p}" for p in list(dict.fromkeys(files))[-12:])
    facts = [ _text(m)[:240] for m in messages if _is_human(m) or str(getattr(m, "type", "")) in {"ai", "AIMessage"} ]
    if facts:
        lines.append("Decisions / answers:")
        lines.extend(f"- {f}" for f in facts[-6:] if f.strip())
    return "\n".join(lines)[:4000]


def split_keep_recent(messages: list[Any], keep_turns: int = KEEP_FULL_TURNS) -> tuple[list[Any], list[Any]]:
    """Keep the last *keep_turns* human-started turns fully; compact the rest."""
    human_idx = [i for i, m in enumerate(messages) if _is_human(m)]
    if len(human_idx) <= keep_turns:
        return [], list(messages)
    cut = human_idx[-keep_turns]
    return list(messages[:cut]), list(messages[cut:])


async def compact_messages(
    messages: list[Any],
    *,
    threshold: int = DEFAULT_THRESHOLD,
    keep_turns: int = KEEP_FULL_TURNS,
    summarize: SummarizeFn | None = None,
    llm: Any | None = None,
) -> list[Any]:
    if len(messages) <= KEEP_LAST:
        return list(messages)
    try:
        tokens = count_tokens(messages)
    except Exception:
        tokens = 0
    older, recent = split_keep_recent(messages, keep_turns=keep_turns)
    if not older:
        return list(messages)
    if tokens <= threshold and len(older) < 8:
        return list(messages)

    summary = ""
    if summarize is not None:
        try:
            summary = await summarize(older)
        except Exception:
            summary = ""
    elif llm is not None:
        blob = "\n".join(_text(m) for m in older)[:12_000]
        prompt = load_prompt("compact", blob=blob)
        try:
            msg = await llm.ainvoke(
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": blob or "(empty)"},
                ]
            )
            summary = str(getattr(msg, "content", None) or msg)
        except Exception:
            summary = ""
    if not summary:
        summary = _summarize_tools(older)
    return [SystemMessage(content=summary), *recent]


async def compact_session_history(
    canonical: list[Any],
    state: dict[str, Any] | None = None,
    *,
    llm: Any | None = None,
    threshold: int | None = None,
    summarize: SummarizeFn | None = None,
) -> tuple[list[Any], dict[str, Any] | None]:
    """Compact only the model view; keep the complete session transcript intact.

    A persisted boundary points into the canonical transcript. Later compactions
    summarize the previous summary plus the newly aged span, never the recent tail.
    """
    trigger = threshold or min(int(context_window_limit() * 0.8), COMPACTION_CAP_TOKENS)
    boundary = int((state or {}).get("boundary_index") or 0)
    if boundary < 0 or boundary > len(canonical):
        state, boundary = None, 0
    previous = str((state or {}).get("summary_text") or "")
    if boundary and not previous:
        state, boundary = None, 0
    visible: list[Any] = (
        [SystemMessage(content=previous), *canonical[boundary:]]
        if state and boundary else list(canonical)
    )
    if count_tokens(visible) < trigger:
        return visible, state

    # A token budget retains useful recent work even when one turn contains many tools.
    keep_budget = max(1, int(trigger * 0.25))
    candidates = [i for i, message in enumerate(canonical)
                  if i > boundary and _is_human(message)]
    cut = next((i for i in candidates if count_tokens(canonical[i:]) <= keep_budget), None)
    if cut is None and candidates:
        # A single tool-heavy turn may exceed the whole recent budget. Keep
        # an assistant iteration rather than starting the model view on a tool.
        assistant_candidates = [
            i for i, message in enumerate(canonical)
            if i > candidates[-1] and str(getattr(message, "type", "")) == "ai"
        ]
        cut = next((i for i in assistant_candidates
                    if count_tokens(canonical[i:]) <= keep_budget), None)
        if cut is None:
            cut = assistant_candidates[-1] if assistant_candidates else candidates[-1]
    if cut is None and not candidates:
        assistant_candidates = [
            i for i, message in enumerate(canonical)
            if i > boundary and str(getattr(message, "type", "")) == "ai"
        ]
        cut = next((i for i in assistant_candidates
                    if count_tokens(canonical[i:]) <= keep_budget), None)
        if cut is None and assistant_candidates:
            cut = assistant_candidates[-1]
    if cut is None or cut <= boundary:
        return visible, state

    older = canonical[boundary:cut]
    summary_input = ([SystemMessage(content=previous)] if previous else []) + older
    summary = ""
    if summarize is not None:
        try:
            summary = str(await summarize(summary_input) or "")
        except Exception:
            summary = ""
    elif llm is not None:
        blob = "\n".join(_text(message)[:800] for message in summary_input)[:40_000]
        try:
            response = await llm.ainvoke([
                {"role": "system", "content": load_prompt("compact", blob=blob)},
                {"role": "user", "content": blob or "(empty)"},
            ])
            summary = str(getattr(response, "content", None) or "").strip()
        except Exception:
            summary = ""
        required = ("用户目标", "关键事实", "文件与产物", "错误与修复",
                    "用户消息", "未完成事项", "当前进度", "下一步")
        if len(summary) < 400 or any(title not in summary for title in required):
            summary = ""
    if not summary:
        summary = _summarize_tools(summary_input)
    # User intent is retained mechanically, independently of summary quality.
    user_messages = [_text(message) for message in canonical[:cut] if _is_human(message)]
    if user_messages:
        first = user_messages[0][:16_000]
        recent_users = user_messages[1:][-20:]
        omitted = max(0, len(user_messages) - 1 - len(recent_users))
        user_block = ["首条用户请求（原文）：", first, "", "较早用户消息（原文节选）："]
        if omitted:
            user_block.append(f"中间有 {omitted} 条用户消息未逐字列出，可回查原文记录。")
        user_block.extend(f"- {message[:800]}" for message in recent_users)
        summary = "\n".join(user_block) + "\n\n" + summary
    mechanical = _summarize_tools(older)
    if mechanical and mechanical not in summary:
        summary += "\n\n可核对的工具与文件线索：\n" + mechanical
    new_state = {"boundary_index": cut, "summary_text": summary}
    return [SystemMessage(content=summary), *canonical[cut:]], new_state
