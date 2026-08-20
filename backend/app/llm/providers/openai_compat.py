"""OpenAI-compatible provider via langchain_openai.

Supports OpenRouter, local vLLM, and GLM via base_url.
Thinking/reasoning is enabled by default for known vendors.
"""

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI


def create_openai_compat(
    model: str,
    api_key: str,
    base_url: str | None = None,
    default_headers: dict[str, str] | None = None,
    max_tokens: int | None = None,
    thinking: bool = True,
) -> BaseChatModel:
    kwargs: dict = {"model": model, "api_key": api_key or "ollama"}
    if base_url is not None:
        kwargs["base_url"] = base_url
    headers = dict(default_headers or {})
    if base_url and "openrouter.ai" in base_url:
        headers.setdefault("HTTP-Referer", "https://my-cowork.local")
        headers.setdefault("X-Title", "my-cowork")
    if headers:
        kwargs["default_headers"] = headers
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    else:
        kwargs["max_tokens"] = 8192
    extra_body: dict = {}
    low = (model or "").lower()
    if thinking:
        if "deepseek" in low:
            extra_body["chat_template_kwargs"] = {"thinking": True}
        elif any(tag in low for tag in ("glm", "qwen", "qwq", "kimi")):
            extra_body["enable_thinking"] = True
        elif any(tag in low for tag in ("o1", "o3", "o4", "gpt-5")):
            kwargs["reasoning_effort"] = "medium"
    if extra_body:
        kwargs["extra_body"] = extra_body
    return ChatOpenAI(**kwargs)
