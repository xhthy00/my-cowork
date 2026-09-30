"""Last budget check shared by planners, workers, summaries, and fallbacks."""
import json
from langchain_core.callbacks import BaseCallbackHandler
from app.llm.model_config import ModelConfig
from app.llm.token_counter import count_tokens


class ContextPreparationError(ValueError):
    """The selected model cannot safely receive the prepared conversation."""


class ModelInputBudgetCallback(BaseCallbackHandler):
    raise_error = True

    def __init__(self, config: ModelConfig):
        self.input_budget = config.input_budget

    def on_chat_model_start(self, serialized, messages, **kwargs):
        params = kwargs.get("invocation_params") or {}
        tool_tokens = count_tokens(json.dumps(params.get("tools") or [], ensure_ascii=False))
        for batch in messages:
            if count_tokens(batch) + tool_tokens > self.input_budget:
                raise ContextPreparationError("当前输入超过模型可用上下文；请缩短输入、压缩会话或选择更大窗口")
