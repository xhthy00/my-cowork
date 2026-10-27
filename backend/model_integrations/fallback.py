"""LLM fallback chain wrapping LangChain BaseChatModel."""

from __future__ import annotations

from typing import Any, Optional, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.callbacks.manager import AsyncCallbackManager, AsyncCallbackManagerForLLMRun, CallbackManager
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.messages.utils import count_tokens_approximately
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
        resolved = [getattr(model, "bound", model) for model in models]
        profile = {**(getattr(resolved[0], "profile", None) or {}), **(kwargs.pop('profile', None) or {})}
        for key in ("max_input_tokens", "max_output_tokens"):
            limits = [getattr(model, "profile", None) or {} for model in resolved]
            values = [item[key] for item in limits if isinstance(item.get(key), int) and item[key] > 0]
            if values:
                profile[key] = min(values)
        metadata = {**(getattr(resolved[0], "metadata", None) or {}), **(kwargs.pop('metadata', None) or {}),
                    "cowork_context_limit": profile.get("max_input_tokens")}
        super().__init__(models=list(models), profile=profile or None, metadata=metadata, **kwargs)
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
                self._check_context(model, messages, kwargs)
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
                self._check_context(model, messages, kwargs)
                message = await model.ainvoke(messages, config=self._child_config(run_manager), stop=stop, **kwargs)
                return ChatResult(generations=[ChatGeneration(message=message)])
            except Exception as exc:
                self._advance(idx, exc)
        raise RuntimeError('Fallback chain is empty')

    @staticmethod
    def _check_context(model, messages, kwargs):
        target = getattr(model, "bound", model)
        capacity = (getattr(target, "profile", None) or {}).get("max_input_tokens")
        tools = kwargs.get("tools") or (getattr(model, "kwargs", {}) or {}).get("tools")
        if isinstance(capacity, int) and capacity > 0 and count_tokens_approximately(messages, tools=tools) > capacity * 0.9:
            raise ValueError("当前上下文超过备用模型的可用窗口；请压缩上下文或选择更大窗口的模型")

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
