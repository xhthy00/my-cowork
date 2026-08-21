"""LangChain callback: accumulate tokens after each LLM call (live UI budget)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.llm.token_counter import count_tokens
from app.runtime.budget_context import record_llm_tokens


def _flatten_chat_messages(messages: list[list[BaseMessage]]) -> list[BaseMessage]:
    flat: list[BaseMessage] = []
    for batch in messages:
        flat.extend(batch)
    return flat


def _usage_parts(usage: Any) -> tuple[int, int, int]:
    """Return ``(total, prompt, completion)`` from a provider usage dict."""
    if not isinstance(usage, dict):
        return 0, 0, 0
    total = 0
    raw_total = usage.get("total_tokens")
    if raw_total is not None:
        try:
            total = max(0, int(raw_total))
        except (TypeError, ValueError):
            total = 0
    try:
        tin = int(
            usage.get("prompt_tokens")
            or usage.get("input_tokens")
            or usage.get("prompt_token_count")
            or 0
        )
        tout = int(
            usage.get("completion_tokens")
            or usage.get("output_tokens")
            or usage.get("completion_token_count")
            or 0
        )
    except (TypeError, ValueError):
        tin, tout = 0, 0
    tin, tout = max(0, tin), max(0, tout)
    if total <= 0:
        total = tin + tout
    return total, tin, tout


def _parts_from_llm_result(response: LLMResult) -> tuple[int, int, int]:
    llm_output = response.llm_output or {}
    for key in ("token_usage", "usage", "usage_metadata"):
        total, tin, tout = _usage_parts(llm_output.get(key))
        if total or tin or tout:
            return total, tin, tout

    texts: list[str] = []
    for gens in response.generations or []:
        for gen in gens:
            if isinstance(gen, ChatGeneration) and gen.message is not None:
                meta = getattr(gen.message, "usage_metadata", None)
                total, tin, tout = _usage_parts(meta if isinstance(meta, dict) else None)
                if total or tin or tout:
                    return total, tin, tout
                content = gen.message.content
                if isinstance(content, str):
                    texts.append(content)
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and "text" in part:
                            texts.append(str(part["text"]))
                        elif isinstance(part, str):
                            texts.append(part)
            else:
                text = getattr(gen, "text", None)
                if text:
                    texts.append(str(text))
    total = count_tokens(texts) if texts else 0
    return total, 0, total


class BudgetTokenCallback(BaseCallbackHandler):
    """Count prompt+completion tokens per LLM call and push ``budget.update``."""

    raise_error: bool = False

    def __init__(self) -> None:
        super().__init__()
        self._prompt_tokens: dict[UUID, int] = {}

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        try:
            self._prompt_tokens[run_id] = count_tokens(_flatten_chat_messages(messages))
        except Exception:
            self._prompt_tokens[run_id] = 0

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        if run_id in self._prompt_tokens:
            return
        try:
            self._prompt_tokens[run_id] = count_tokens(prompts)
        except Exception:
            self._prompt_tokens[run_id] = 0

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        prompt_n = self._prompt_tokens.pop(run_id, 0)
        try:
            usage_n, usage_in, usage_out = _parts_from_llm_result(response)
        except Exception:
            usage_n, usage_in, usage_out = 0, 0, 0
        if usage_n > 0:
            # Provider usage already includes prompt + completion.
            n = usage_n
        else:
            out_n = 0
            try:
                texts: list[str] = []
                for gens in response.generations or []:
                    for gen in gens:
                        if isinstance(gen, ChatGeneration) and gen.message is not None:
                            content = gen.message.content
                            if isinstance(content, str):
                                texts.append(content)
                        else:
                            text = getattr(gen, "text", None)
                            if text:
                                texts.append(str(text))
                out_n = count_tokens(texts) if texts else 0
            except Exception:
                out_n = 0
            n = prompt_n + out_n
            usage_in = prompt_n
            usage_out = out_n
        context_n = usage_in or prompt_n
        if n > 0:
            record_llm_tokens(
                n,
                context_tokens=context_n,
                input_tokens=usage_in or prompt_n,
                output_tokens=usage_out,
            )

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._prompt_tokens.pop(run_id, None)


BUDGET_TOKEN_CALLBACK = BudgetTokenCallback()


def instrument_model_for_budget(model: Any) -> Any:
    """Attach the shared budget callback so nested agent LLM calls report usage."""
    if model is None:
        return model

    # Fallback chain: instrument each leaf model.
    models = getattr(model, "models", None)
    if isinstance(models, list) and models and type(model).__name__ == "FallbackChatModel":
        model.models = [instrument_model_for_budget(m) for m in models]
        return model

    cb = BUDGET_TOKEN_CALLBACK
    try:
        existing = list(getattr(model, "callbacks", None) or [])
    except Exception:
        existing = []
    if cb in existing:
        return model
    existing.append(cb)
    try:
        model.callbacks = existing
        return model
    except Exception:
        try:
            return model.with_config(callbacks=[cb])
        except Exception:
            return model
