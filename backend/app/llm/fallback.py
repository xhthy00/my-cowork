"""LLM fallback chain wrapping LangChain BaseChatModel."""

from __future__ import annotations

from typing import Any, Optional, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field, PrivateAttr
from app.llm.model_config import ModelConfig, compatible_model_messages, model_scope


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
    _model_configs: list[ModelConfig | None] = PrivateAttr(default_factory=list)

    def __init__(
        self,
        models: Sequence[BaseChatModel],
        *,
        on_fallback: Any = None,
        model_configs: Sequence[ModelConfig | None] | None = None,
        **kwargs: Any,
    ) -> None:
        if not models:
            raise ValueError("FallbackChatModel requires at least one model")
        super().__init__(models=list(models), **kwargs)
        self._on_fallback = on_fallback
        self._model_configs = list(model_configs) if model_configs is not None else [None] * len(models)
        if len(self._model_configs) != len(models):
            raise ValueError("Each fallback model must have its own configuration")

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FallbackChatModel":
        bound = []
        for m in self.models:
            if hasattr(m, "bind_tools"):
                bound.append(m.bind_tools(tools, **kwargs))
            else:
                bound.append(m)
        return FallbackChatModel(bound, on_fallback=self._on_fallback, model_configs=self._model_configs)

    @property
    def _llm_type(self) -> str:
        return "fallback-chat-model"

    def _try_models(self, fn_name: str, *args: Any, **kwargs: Any) -> Any:
        last_exc: BaseException | None = None
        for idx, model in enumerate(self.models):
            try:
                method = getattr(model, fn_name)
                config = self._model_configs[idx]
                with model_scope(config):
                    message = method(compatible_model_messages(args[0], config), *args[1:], **kwargs)
                return self._stamp(message, config)
            except Exception as exc:
                last_exc = exc
                if idx + 1 >= len(self.models) or not is_retryable_llm_error(exc):
                    raise
                if self._on_fallback is not None:
                    self._on_fallback(idx, exc)
        assert last_exc is not None
        raise last_exc

    @staticmethod
    def _stamp(message, config):
        if config:
            message = message.model_copy(update={"response_metadata": {**message.response_metadata,
                "request_model": [config.provider, config.model, config.base_url]}})
        return message

    def _generate(
        self,
        messages: Sequence[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        message = self._try_models(
            "invoke", list(messages), stop=stop,
            config={"callbacks": run_manager.inheritable_handlers} if run_manager else None,
            **kwargs,
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

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
                config = self._model_configs[idx]
                with model_scope(config):
                    message = await model.ainvoke(
                        compatible_model_messages(messages, config), stop=stop,
                        config={"callbacks": run_manager.inheritable_handlers} if run_manager else None,
                        **kwargs,
                    )
                return ChatResult(generations=[ChatGeneration(message=self._stamp(message, config))])
            except Exception as exc:
                last_exc = exc
                if idx + 1 >= len(self.models) or not is_retryable_llm_error(exc):
                    raise
                if self._on_fallback is not None:
                    self._on_fallback(idx, exc)
        assert last_exc is not None
        raise last_exc
