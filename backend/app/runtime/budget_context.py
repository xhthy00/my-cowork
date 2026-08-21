"""Per-task budget runtime so LLM callbacks can emit live token updates."""

from __future__ import annotations

import os
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.runtime.budget import Budget

_DEFAULT_CONTEXT_LIMIT = 200_000


@dataclass
class BudgetRuntime:
    task_id: str
    bus: Any
    budget: Budget


_budget_runtime: ContextVar[BudgetRuntime | None] = ContextVar(
    "budget_runtime", default=None
)


def set_budget_runtime(runtime: BudgetRuntime | None) -> Token:
    return _budget_runtime.set(runtime)


def reset_budget_runtime(token: Token) -> None:
    _budget_runtime.reset(token)


def get_budget_runtime() -> BudgetRuntime | None:
    return _budget_runtime.get()


def context_window_limit(budget: Budget | None = None) -> int:
    """Model / task context window shown in the chat footer."""
    raw = os.environ.get("MY_COWORK_CONTEXT_LIMIT")
    if raw:
        try:
            n = int(raw)
            if n > 0:
                return n
        except ValueError:
            pass
    if budget is not None and getattr(budget, "max_total_tokens", 0):
        try:
            n = int(budget.max_total_tokens)
            if n > 0:
                return n
        except (TypeError, ValueError):
            pass
    try:
        return int(os.environ.get("MY_COWORK_MAX_TOKENS", str(_DEFAULT_CONTEXT_LIMIT)))
    except ValueError:
        return _DEFAULT_CONTEXT_LIMIT


def record_llm_tokens(
    n: int,
    *,
    context_tokens: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Consume *n* tokens and emit ``budget.update`` when a task is in progress."""
    if n <= 0:
        return
    rt = get_budget_runtime()
    if rt is None:
        return
    rt.budget.consume_tokens(n)
    event: dict[str, Any] = {
        "task_id": rt.task_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "budget.update",
        "tokens": rt.budget.tokens,
        "max_tokens": rt.budget.max_total_tokens,
        "steps": rt.budget.steps,
        "context_limit": context_window_limit(rt.budget),
    }
    if context_tokens > 0:
        event["context_tokens"] = int(context_tokens)
    if input_tokens > 0:
        event["input_tokens"] = int(input_tokens)
    if output_tokens > 0:
        event["output_tokens"] = int(output_tokens)
    rt.bus.emit(event)
