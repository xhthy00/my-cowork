"""Tool-aware context compaction (v2)."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from app.agents.factory import load_prompt
from app.llm.token_counter import count_tokens
from app.runtime.compressor import DEFAULT_THRESHOLD, KEEP_LAST, SummarizeFn

KEEP_FULL_TURNS = 3


def _is_human(msg: Any) -> bool:
    role = str(getattr(msg, "type", None) or getattr(msg, "role", None) or "")
    return role in {"human", "user", "HumanMessage"}


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
