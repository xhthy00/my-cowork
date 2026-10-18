"""LLM fallback chain wrapping LangChain BaseChatModel."""

from __future__ import annotations

from typing import Any, Optional, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.callbacks.manager import AsyncCallbackManager, AsyncCallbackManagerForLLMRun, CallbackManager
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field, PrivateAttr


def is_retryable_llm_error(exc: BaseException) -> bool:
    """Return True for transient provider failures worth falling back on."""
    status = getattr(exc, 'status_code', None) or getattr(exc, 'status', None)
    if status is not None:
        return status in {408, 429, 500, 502, 503, 504}
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

    def _generate(
        self,
        messages: Sequence[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        for idx, model in enumerate(self.models):
            try:
                message = model.invoke(messages, config=self._child_config(run_manager), stop=stop, **kwargs)
                return ChatResult(generations=[ChatGeneration(message=message)])
            except Exception as exc:
                self._advance(idx, exc)
        raise RuntimeError('Fallback chain is empty')

    async def _agenerate(
        self,
        messages: Sequence[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        for idx, model in enumerate(self.models):
            try:
                message = await model.ainvoke(messages, config=self._child_config(run_manager), stop=stop, **kwargs)
                return ChatResult(generations=[ChatGeneration(message=message)])
            except Exception as exc:
                self._advance(idx, exc)
        raise RuntimeError('Fallback chain is empty')

    @staticmethod
    def _child_config(run_manager):
        if run_manager is None:
            return None
        manager = AsyncCallbackManager if isinstance(run_manager, AsyncCallbackManagerForLLMRun) else CallbackManager
        callbacks = manager(handlers=run_manager.inheritable_handlers,
            inheritable_handlers=run_manager.inheritable_handlers, parent_run_id=run_manager.run_id,
            tags=run_manager.inheritable_tags, inheritable_tags=run_manager.inheritable_tags,
            metadata=run_manager.inheritable_metadata, inheritable_metadata=run_manager.inheritable_metadata)
        return {'callbacks': callbacks}

    def _advance(self, index, exc):
        if index + 1 >= len(self.models) or not is_retryable_llm_error(exc):
            raise exc
        if self._on_fallback is not None:
            self._on_fallback(index, exc)
