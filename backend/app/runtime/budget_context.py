"""Per-task budget runtime so LLM callbacks can emit live token updates."""

from __future__ import annotations

import os
import time
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.llm.token_counter import count_tokens
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


def context_window_limit() -> int:
    """Model context window for the occupancy ring.

    Not the task cost cap (``Budget.max_total_tokens`` / ``MY_COWORK_MAX_TOKENS``).
    Override with ``MY_COWORK_CONTEXT_LIMIT``.
    """
    raw = os.environ.get("MY_COWORK_CONTEXT_LIMIT")
    if raw:
        try:
            n = int(raw)
            if n > 0:
                return n
        except ValueError:
            pass
    return _DEFAULT_CONTEXT_LIMIT


def _budget_event(
    rt: BudgetRuntime,
    tokens: int,
    *,
    context_tokens: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "task_id": rt.task_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "budget.update",
        "tokens": tokens,
        "max_tokens": rt.budget.max_total_tokens,
        "steps": rt.budget.steps,
        "context_limit": context_window_limit(),
    }
    if context_tokens > 0:
        event["context_tokens"] = int(context_tokens)
    if input_tokens > 0:
        event["input_tokens"] = int(input_tokens)
    if output_tokens > 0:
        event["output_tokens"] = int(output_tokens)
    return event


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
    rt.bus.emit(
        _budget_event(
            rt,
            rt.budget.tokens,
            context_tokens=context_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    )


def emit_budget_preview(
    in_flight: int,
    *,
    context_tokens: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """Push a live UI total for an in-flight LLM call without consuming the cap."""
    if in_flight <= 0:
        return
    rt = get_budget_runtime()
    if rt is None:
        return
    rt.bus.emit(
        _budget_event(
            rt,
            rt.budget.tokens + in_flight,
            context_tokens=context_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    )


class LiveTokenPreview:
    """Throttle in-flight prompt+completion estimates to the UI."""

    def __init__(self, prompt_n: int = 0, *, min_interval_s: float = 0.4):
        self.prompt_n = max(0, int(prompt_n))
        self.min_interval_s = min_interval_s
        self._chunks: list[str] = []
        self._last = 0.0
        if self.prompt_n:
            self.flush(force=True)

    def add(self, text: str) -> None:
        if not text:
            return
        first_output = not self._chunks
        self._chunks.append(text)
        self.flush(force=first_output)

    def flush(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last < self.min_interval_s:
            return
        joined = "".join(self._chunks)
        out_n = 0
        if joined:
            try:
                out_n = count_tokens(joined)
            except Exception:
                out_n = max(1, len(joined) // 4)
        in_flight = self.prompt_n + out_n
        if in_flight <= 0:
            return
        self._last = now
        emit_budget_preview(
            in_flight,
            context_tokens=self.prompt_n,
            input_tokens=self.prompt_n,
            output_tokens=out_n,
        )
