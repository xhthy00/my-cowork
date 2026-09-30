"""Immutable model settings, resolved once per task, never via mutable process env."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from typing import Iterator


@dataclass(frozen=True)
class ModelConfig:
    id: str
    provider: str
    model: str
    api_key: str = field(repr=False)
    base_url: str | None = None
    context_window: int = 200_000
    input_limit: int | None = None
    output_limit: int = 8192
    compaction_ratio: float = 0.8
    # Validated adapter options; internal data, not arbitrary client kwargs.
    reasoning_mode: str = "default"
    reasoning_effort: str | None = None
    thinking_enabled: bool | None = None
    thinking_budget: int | None = None
    allowed_efforts: tuple[str, ...] = ()
    allow_thinking_toggle: bool = False
    budget_min: int | None = None
    budget_max: int | None = None

    def __post_init__(self):
        object.__setattr__(self, "allowed_efforts", tuple(self.allowed_efforts))
        if not self.id or not self.model or self.provider not in {"anthropic", "openai_compat"}:
            raise ValueError("模型配置无效")
        if self.context_window < 1024 or self.output_limit < 1 or not 0.1 <= self.compaction_ratio <= 0.95:
            raise ValueError("上下文或压缩设置无效")
        if self.reasoning_mode not in {"default", "openai", "openai-responses", "anthropic", "deepseek", "moonshot", "qwen", "openrouter", "thinking", "google", "minimax"}:
            raise ValueError("思考参数协议无效")

    def with_reasoning(self, selection: dict) -> ModelConfig:
        effort, enabled, budget = selection.get("effort"), selection.get("enabled"), selection.get("budgetTokens")
        if effort is not None and effort not in self.allowed_efforts:
            raise ValueError("此模型不支持所选思考强度")
        if enabled is not None and (not isinstance(enabled, bool) or not self.allow_thinking_toggle):
            raise ValueError("此模型不支持切换思考模式")
        if budget is not None and (type(budget) is not int or self.budget_min is None or not self.budget_min <= budget < min((self.budget_max or self.output_limit) + 1, self.output_limit)):
            raise ValueError("思考预算超出模型支持范围")
        if self.reasoning_mode == "default" and any(v is not None for v in (effort, enabled, budget)):
            raise ValueError("请先配置此服务的思考参数协议")
        if enabled is False and ((effort is not None and self.reasoning_mode != "anthropic") or budget is not None):
            raise ValueError("关闭思考时不能同时指定强度或预算")
        if self.reasoning_mode in {"google", "openrouter"} and effort is not None and budget is not None:
            raise ValueError("此服务的思考强度和预算不能同时指定")
        if budget is not None and self.reasoning_mode not in {"anthropic", "qwen", "google", "openrouter"}:
            raise ValueError("此参数协议不支持思考预算")
        if enabled is not None and self.reasoning_mode in {"openai", "openai-responses"}:
            raise ValueError("此参数协议不支持思考开关")
        return replace(self, reasoning_effort=effort, thinking_enabled=enabled, thinking_budget=budget)

    @property
    def input_budget(self) -> int:
        return max(1, min(self.input_limit or self.context_window,
                          self.context_window - self.output_limit - 1024))

    @property
    def compression_trigger(self) -> int:
        return max(1, min(int(self.context_window * self.compaction_ratio), self.input_budget))


_current: ContextVar[ModelConfig | None] = ContextVar("task_model_config", default=None)


def current_model_config() -> ModelConfig | None:
    return _current.get()


def compatible_model_messages(messages, config: ModelConfig | None):
    """Keep signed provider blocks only for the model/endpoint that produced them."""
    from langchain_core.messages import AIMessage
    if config is None:
        return list(messages)
    identity = [config.provider, config.model, config.base_url]
    result = []
    for message in messages:
        if isinstance(message, AIMessage) and isinstance(message.content, list) and message.response_metadata.get("request_model") != identity:
            text = [part for part in message.content if isinstance(part, str) or isinstance(part, dict) and part.get("type") in {"text", "output_text"}]
            message = message.model_copy(update={"content": text or " "})
        result.append(message)
    return result


@contextmanager
def model_scope(config: ModelConfig | None) -> Iterator[None]:
    token = _current.set(config)
    try:
        yield
    finally:
        _current.reset(token)


class ModelRegistry:
    """In-memory credentials supplied only by the trusted desktop main process."""

    def __init__(self):
        self.initialized = False
        self._models: dict[str, ModelConfig] = {}
        self._active: str | None = None

    def replace(self, models: list[ModelConfig], active_id: str | None) -> None:
        updated = {model.id: model for model in models}
        if len(updated) != len(models) or (active_id is not None and active_id not in updated):
            raise ValueError("默认模型不存在或模型重复")
        self._models, self._active = updated, active_id
        self.initialized = True

    def resolve(self, profile_id: str | None = None) -> ModelConfig:
        result = self._models.get(profile_id or self._active or "")
        if result is None:
            raise ValueError("模型不可用，请在设置中选择有效模型")
        return result

    def find_model(self, provider: str, model: str) -> ModelConfig | None:
        return next((config for config in self._models.values() if config.provider == provider and config.model == model), None)
