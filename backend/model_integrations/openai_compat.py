"""OpenAI-compatible provider via langchain_openai.

Supports OpenRouter, local vLLM, and GLM via base_url.
Thinking/reasoning is enabled by default for known vendors.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek
from .context import with_context_metadata


# Model families that emit a burst of tokens and then stall while "thinking"
# (DeepSeek-R1, GLM-thinking, Qwen / QwQ, Kimi, MiniMax-M*, OpenAI o-series,
# GPT-5, ...). langchain_openai defaults ``stream_chunk_timeout`` to 120s,
# which is too short for these models. The tags below are matched against
# the lower-cased model name and used to pick a longer default in
# ``_resolve_stream_chunk_timeout``.
_REASONING_MODEL_TAGS: tuple[str, ...] = (
    "deepseek",
    "qwen",
    "qwq",
    "kimi",
    "glm",
    "minimax",
    "o1",
    "o3",
    "o4",
    "gpt-5",
    "reasoning",
    "r1",
)

# Default per-chunk wall-clock timeout (seconds) for reasoning models.
# langchain measures the gap between *parsed* content chunks (SSE keep-alives
# do NOT reset the timer), so this needs to comfortably outlive the longest
# "thinking" pause observed on long-context / heavy reasoning prompts.
_REASONING_STREAM_CHUNK_TIMEOUT_S: float = 600.0  # 10 minutes

# Sentinels used by ``_resolve_stream_chunk_timeout`` to distinguish
# "leave the kwarg unset (langchain keeps its 120s default)" from
# "explicitly disable the wrapper (pass None to ChatOpenAI)".
_UNSET: object = object()
_DISABLE: object = object()


def is_native_deepseek(base_url: str | None) -> bool:
    return urlsplit(str(base_url or '')).hostname == 'api.deepseek.com'


def endpoint_family(base_url: str | None) -> str:
    """Endpoint protocol takes precedence over model-name guesses."""
    host = urlsplit(str(base_url or '')).hostname
    if host is None or host == 'api.openai.com':
        return 'openai'
    endpoints = {
        'api.deepseek.com': 'deepseek',
        'api.moonshot.ai': 'moonshot', 'api.moonshot.cn': 'moonshot',
        'open.bigmodel.cn': 'glm', 'api.z.ai': 'glm',
        'dashscope.aliyuncs.com': 'qwen', 'dashscope-intl.aliyuncs.com': 'qwen',
        'dashscope-us.aliyuncs.com': 'qwen',
        'api.minimax.io': 'minimax', 'api.minimaxi.com': 'minimax',
        'openrouter.ai': 'openrouter',
    }
    return endpoints.get(host, 'custom')


def has_thinking_toggle(family: str, model: str) -> bool:
    name = model.lower().rsplit('/', 1)[-1]
    if family == 'deepseek':
        return True
    if family == 'moonshot':
        return name.startswith(('kimi-k2.5', 'kimi-k2.6'))
    if family == 'glm':
        return name.startswith(('glm-4.5', 'glm-4.6', 'glm-4.7', 'glm-5')) and not name.startswith('glm-5.3')
    if family == 'qwen':
        return name.startswith(('qwen-plus', 'qwen-turbo', 'qwen-flash', 'qwen3')) and not (
            'coder' in name or 'thinking' in name)
    return False


def _resolve_stream_chunk_timeout(
    explicit: object,
    low_model: str,
) -> object:
    """Return the value to pass as ``stream_chunk_timeout`` to ChatOpenAI.

    Resolution order:
      1. ``explicit`` if provided by the caller (already-parsed value).
      2. ``MY_COWORK_STREAM_CHUNK_TIMEOUT_S`` env var.
      3. Heuristic default based on model family.

    Returns ``_UNSET`` when neither the caller nor the env var supplied a
    value *and* the model is not a known reasoning family, so we do not pass
    the kwarg at all and langchain_openai keeps its own 120s default.

    Returns ``None`` (the literal value) when the env var is a sentinel like
    ``"0"`` / ``"none"`` / ``"off"`` / ``"disabled"``, matching langchain's
    own semantics for the kwarg.
    """
    if explicit is not None and explicit is not _UNSET:
        return explicit

    raw = os.environ.get("MY_COWORK_STREAM_CHUNK_TIMEOUT_S")
    if raw is not None:
        stripped = raw.strip()
        if stripped:
            if stripped.lower() in {"0", "none", "off", "disable", "disabled", "false", "no"}:
                return None
            try:
                return float(stripped)
            except ValueError:
                # Fall through to heuristic default.
                pass

    if any(tag in low_model for tag in _REASONING_MODEL_TAGS):
        return _REASONING_STREAM_CHUNK_TIMEOUT_S
    return _UNSET


def create_openai_compat(
    model: str,
    api_key: str,
    base_url: str | None = None,
    default_headers: dict[str, str] | None = None,
    max_tokens: int | None = None,
    thinking: bool = True,
    stream_chunk_timeout: float | None | object = _UNSET,
) -> BaseChatModel:
    kwargs: dict = {"model": model, "api_key": api_key or "ollama"}
    if base_url is not None:
        kwargs["base_url"] = base_url
    headers = dict(default_headers or {})
    family = endpoint_family(base_url)
    if family == 'openrouter':
        headers.setdefault("HTTP-Referer", "https://my-cowork.local")
        headers.setdefault("X-Title", "my-cowork")
    if headers:
        kwargs["default_headers"] = headers
    # Omit max_tokens unless the caller set a positive cap. A default of
    # 8192 was cutting MiniMax / long HTML writes mid-file ("文件被截断了").
    # ChatOpenAI then leaves max_tokens=None and the vendor/model max applies.
    if isinstance(max_tokens, int) and max_tokens > 0:
        kwargs["max_tokens"] = max_tokens
    extra_body: dict = {}
    low = (model or "").lower()
    if has_thinking_toggle(family, model):
        if family == 'qwen':
            extra_body['enable_thinking'] = thinking
        else:
            extra_body['thinking'] = {'type': 'enabled' if thinking else 'disabled'}
    elif family == 'openai' and thinking and low.startswith(('o1', 'o3', 'o4', 'gpt-5')):
        kwargs['reasoning_effort'] = 'medium'
    if extra_body:
        kwargs["extra_body"] = extra_body

    resolved_timeout = _resolve_stream_chunk_timeout(stream_chunk_timeout, low)
    if family == 'openrouter':
        # Its SDK has its own request timeout and preserves reasoning signatures.
        from langchain_openrouter import ChatOpenRouter
        return with_context_metadata(ChatOpenRouter(**kwargs))
    if family == 'qwen' and (thinking or not has_thinking_toggle(family, model)):
        # Older thinking models require streaming, including internal summaries.
        kwargs['streaming'] = True
    if resolved_timeout is _UNSET:
        pass  # let langchain_openai keep its 120s default
    elif resolved_timeout is _DISABLE:
        kwargs["stream_chunk_timeout"] = None
    else:
        kwargs["stream_chunk_timeout"] = resolved_timeout

    # These native endpoints share the reasoning_content Chat Completions wire
    # format; the official parser preserves it for both JSON and SSE responses.
    provider_model = ChatDeepSeek if family in {'deepseek', 'moonshot', 'glm', 'qwen', 'minimax'} else ChatOpenAI
    return with_context_metadata(provider_model(**kwargs), model_name=model, base_url=base_url)
