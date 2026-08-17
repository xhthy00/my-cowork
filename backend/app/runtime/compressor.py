"""Context compression for long message histories."""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable, Protocol

from langchain_core.messages import HumanMessage, SystemMessage

from app.llm.token_counter import count_tokens

SummarizeFn = Callable[[list[Any]], Awaitable[str]]

DEFAULT_THRESHOLD = 120_000
KEEP_LAST = 5


class _HasMessages(Protocol):
    messages: list


def _message_text(m: Any) -> str:
    content = getattr(m, "content", m) if not isinstance(m, dict) else m.get("content", "")
    return content.strip() if isinstance(content, str) else str(content)[:200]


async def _default_summarize(old_messages: list[Any]) -> str:
    """Offline fallback when no API key / summarize fn is available."""
    texts = [_message_text(m) for m in old_messages if _message_text(m)]
    joined = " | ".join(texts[:20])
    return f"摘要（自动压缩）：{joined[:1500]}"


def make_llm_summarize(
    *,
    api_key: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> SummarizeFn:
    """Build a summarize fn that calls the cheap ``compress`` model."""

    async def _summarize(old_messages: list[Any]) -> str:
        key = api_key if api_key is not None else os.environ.get("MY_COWORK_API_KEY")
        if not key:
            return await _default_summarize(old_messages)

        from app.llm.gateway import create_model
        from app.llm.router import model_picker

        prov, mod = (provider, model) if provider and model else model_picker("compress")
        kwargs: dict[str, Any] = {}
        base_url = os.environ.get("MY_COWORK_BASE_URL")
        if base_url and prov == "openai_compat":
            kwargs["base_url"] = base_url
        llm = create_model(prov, mod, key, **kwargs)
        blob = "\n".join(_message_text(m) for m in old_messages if _message_text(m))[:12000]
        prompt = [
            SystemMessage(content="用简体中文把下列对话压缩成一段精炼摘要，保留关键事实与决策。"),
            HumanMessage(content=blob or "(empty)"),
        ]
        result = await llm.ainvoke(prompt)
        text = getattr(result, "content", None) or str(result)
        return f"摘要（模型压缩）：{text.strip()}"

    return _summarize


async def maybe_compress(
    ctx: _HasMessages | list,
    *,
    threshold: int = DEFAULT_THRESHOLD,
    keep: int = KEEP_LAST,
    summarize: SummarizeFn | None = None,
) -> bool:
    """Compress *ctx* messages when token count exceeds *threshold*.

    Replaces older messages with a single system summary and keeps the last
    *keep* messages intact. Returns ``True`` if compression ran.

    When *summarize* is omitted, uses the cheap ``model_picker("compress")``
    model if ``MY_COWORK_API_KEY`` is set; otherwise the offline fallback.
    """
    if isinstance(ctx, list):
        messages = ctx
    else:
        messages = list(ctx.messages)

    tokens = count_tokens(messages)
    if tokens <= threshold:
        return False

    if len(messages) <= keep:
        return False

    older = messages[:-keep]
    recent = messages[-keep:]
    fn = summarize or make_llm_summarize()
    summary = await fn(older)
    new_messages: list[Any] = [SystemMessage(content=summary), *recent]

    if isinstance(ctx, list):
        ctx[:] = new_messages
    else:
        ctx.messages = new_messages
    return True
