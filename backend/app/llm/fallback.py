"""LLM fallback chain wrapping LangChain BaseChatModel."""

from __future__ import annotations

from typing import Any, Optional, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field, PrivateAttr


def is_retryable_llm_error(exc: BaseException) -> bool:
    """Return True for transient provider failures worth falling back on."""
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    markers = (
        "429",
        "rate limit",
        "timeout",
        "timed out",
        "503",
        "502",
        "500",
        "overloaded",
        "connection",
        "temporarily unavailable",
        "service unavailable",
    )
    if any(m in text for m in markers):
        return True
    if any(k in name for k in ("timeout", "ratelimit", "connection", "apierro")):
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status in {408, 429, 500, 502, 503, 504}:
        return True
    return False


class FallbackChatModel(BaseChatModel):
    """Try models in order; on retryable errors advance to the next."""

    models: list[Any] = Field(default_factory=list)
    _on_fallback: Any = PrivateAttr(default=None)

    def __init__(
        self,
        models: Sequence[BaseChatModel],
        *,
        on_fallback: Any = None,
        **kwargs: Any,
    ) -> None:
        if not models:
            raise ValueError("FallbackChatModel requires at least one model")
        super().__init__(models=list(models), **kwargs)
        self._on_fallback = on_fallback

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FallbackChatModel":
        bound = []
        for m in self.models:
            if hasattr(m, "bind_tools"):
                bound.append(m.bind_tools(tools, **kwargs))
            else:
                bound.append(m)
        return FallbackChatModel(bound, on_fallback=self._on_fallback)

    @property
    def _llm_type(self) -> str:
        return "fallback-chat-model"

    def _try_models(self, fn_name: str, *args: Any, **kwargs: Any) -> Any:
        last_exc: BaseException | None = None
        for idx, model in enumerate(self.models):
            try:
                method = getattr(model, fn_name)
                return method(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if idx + 1 >= len(self.models) or not is_retryable_llm_error(exc):
                    raise
                if self._on_fallback is not None:
                    self._on_fallback(idx, exc)
        assert last_exc is not None
        raise last_exc

    def _generate(
        self,
        messages: Sequence[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._try_models(
            "_generate", messages, stop=stop, run_manager=run_manager, **kwargs
        )

    async def _agenerate(
        self,
        messages: Sequence[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        last_exc: BaseException | None = None
        for idx, model in enumerate(self.models):
            try:
                return await model._agenerate(
                    messages, stop=stop, run_manager=run_manager, **kwargs
                )
            except Exception as exc:
                last_exc = exc
                if idx + 1 >= len(self.models) or not is_retryable_llm_error(exc):
                    raise
                if self._on_fallback is not None:
                    self._on_fallback(idx, exc)
        assert last_exc is not None
        raise last_exc
