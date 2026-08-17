"""
L2 LLM layer: model-agnostic gateway and token counting.

Provides `create_model()` returning LangChain `BaseChatModel` instances,
`model_picker()` for task-kind based model selection,
and `count_tokens()` for budget tracking.
"""

from app.llm.gateway import create_model, embed, local_embed
from app.llm.router import model_picker
from app.llm.token_counter import count_tokens

__all__ = ["create_model", "count_tokens", "model_picker", "embed", "local_embed"]
