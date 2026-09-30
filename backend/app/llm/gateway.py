"""LLM gateway: model-agnostic factory returning LangChain BaseChatModel."""

from __future__ import annotations

import hashlib
import math
from typing import Callable

from langchain_core.language_models import BaseChatModel

from app.llm.providers.anthropic import create_anthropic
from app.llm.providers.openai_compat import create_openai_compat

PROVIDERS = {
    "anthropic": create_anthropic,
    "openai_compat": create_openai_compat,
}

EmbedFn = Callable[[str], list[float]]


def create_model(
    provider: str,
    model: str,
    api_key: str,
    **kwargs,
) -> BaseChatModel:
    factory = PROVIDERS.get(provider)
    if factory is None:
        raise ValueError(f"Unknown provider: {provider!r}. Available: {list(PROVIDERS)}")
    return factory(model=model, api_key=api_key, **kwargs)


def create_configured_model(config):
    from app.llm.budget_callback import instrument_model_for_budget
    from app.llm.context_limits import ModelInputBudgetCallback
    from app.llm.reasoning import reasoning_kwargs
    model = create_model(
        config.provider, config.model, config.api_key,
        base_url=config.base_url, max_tokens=config.output_limit,
        thinking=False, request_options=reasoning_kwargs(config),
    )
    model.callbacks = [*(getattr(model, "callbacks", None) or []), ModelInputBudgetCallback(config)]
    return instrument_model_for_budget(model)


def local_embed(text: str, dim: int = 64) -> list[float]:
    """Deterministic bag-of-hash embedding (offline / tests / no API key)."""
    vec = [0.0] * dim
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for i in range(dim):
            b = digest[i % len(digest)]
            vec[i] += (b / 255.0) * 2 - 1
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def embed(text: str, *, dim: int = 64, embed_fn: EmbedFn | None = None) -> list[float]:
    """Return an embedding vector for *text*.

    Prefer an injected *embed_fn*; otherwise use the local deterministic embedder.
    """
    if embed_fn is not None:
        return embed_fn(text)
    return local_embed(text, dim=dim)
