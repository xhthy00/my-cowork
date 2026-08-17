"""OpenAI-compatible provider via langchain_openai.

Supports OpenRouter, local vLLM, and GLM via base_url.
"""

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI


def create_openai_compat(
    model: str,
    api_key: str,
    base_url: str | None = None,
    default_headers: dict[str, str] | None = None,
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
    return ChatOpenAI(**kwargs)
