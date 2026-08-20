"""Per-run long-term memory handle (not stored in the graph checkpoint)."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

_long_term: ContextVar[Any] = ContextVar("long_term_runtime", default=None)


def set_long_term_runtime(store: Any) -> Token:
    return _long_term.set(store)


def reset_long_term_runtime(token: Token) -> None:
    _long_term.reset(token)


def get_long_term_runtime() -> Any:
    return _long_term.get()
