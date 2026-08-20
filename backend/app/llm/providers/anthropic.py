"""Anthropic provider via langchain_anthropic."""

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel


def create_anthropic(
    model: str,
    api_key: str,
    max_tokens: int | None = 8192,
    thinking: bool = True,
) -> BaseChatModel:
    kwargs: dict = {"model": model, "api_key": api_key}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    low = (model or "").lower()
    if thinking and any(tag in low for tag in ("sonnet", "opus", "4-")):
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": 4096}
    return ChatAnthropic(**kwargs)
