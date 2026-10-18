"""Anthropic provider via langchain_anthropic."""

import re
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from .context import with_context_metadata


def create_anthropic(
    model: str,
    api_key: str,
    max_tokens: int | None = 8192,
    thinking: bool = True,
    base_url: str | None = None,
) -> BaseChatModel:
    kwargs: dict = {"model": model, "api_key": api_key}
    if base_url:
        kwargs['base_url'] = base_url
    token_limit = max_tokens if max_tokens is not None else 8192
    if token_limit <= 0:
        raise ValueError('max_tokens 必须为正整数')
    kwargs['max_tokens'] = token_limit
    low = (model or "").lower()
    version = re.match(r'claude-(?:sonnet|opus|haiku)-(\d+)(?:-(\d)(?:-|$))?', low)
    adaptive = bool(version and (int(version[1]) >= 5 or (int(version[1]) == 4 and int(version[2] or 0) >= 6)))
    manual = low.startswith('claude-3-7') or bool(version and int(version[1]) == 4 and not adaptive)
    if thinking and adaptive:
        kwargs['thinking'] = {'type': 'adaptive'}
    elif thinking and manual:
        if token_limit <= 1024:
            raise ValueError('手动思考模式的 max_tokens 必须大于 1024；请提高输出上限或关闭思考模式')
        kwargs['thinking'] = {'type': 'enabled', 'budget_tokens': min(4096, token_limit - 1)}
    return with_context_metadata(ChatAnthropic(**kwargs), model_name=model, base_url=base_url)
