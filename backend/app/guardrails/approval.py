"""Async approval gate with ConfirmHub."""

from __future__ import annotations

import asyncio
import re
from typing import Any, Callable

_OFFICECLI_CMD_RE = re.compile(r"^\s*officecli(\s|$)")


class ConfirmTimeout(Exception):
    """Raised when a confirm request is not resolved within the timeout."""


class ConfirmHub:
    """Hold pending confirmation requests and resolve them asynchronously.

    The hub is intended to be a singleton owned by ``TaskManager`` so that
    multiple concurrent tasks share the same ``call_id -> Future`` pool.
    """

    def __init__(
        self,
        emit: Callable[[dict[str, Any]], None] | None = None,
        timeout_seconds: float = 600.0,
        audit: Any = None,
    ) -> None:
        self._emit = emit or (lambda _event: None)
        self._timeout_seconds = timeout_seconds
        self._audit = audit
        self._futures: dict[str, asyncio.Future[bool]] = {}
        self._plan_futures: dict[str, asyncio.Future[list[dict[str, Any]]]] = {}
        self._pending_meta: dict[str, dict[str, Any]] = {}
        # After the user approves one officecli bash, skip further officecli confirms.
        self._officecli_auto_ok = False

    def _audit_log(self, **kwargs: Any) -> None:
        if self._audit is None:
            return
        try:
            self._audit.log(**kwargs)
        except Exception:
            pass

    async def request(self, call_id: str, tool: str, args: dict[str, Any]) -> bool:
        """Emit a confirmation request and await user resolution.

        Returns ``True`` if the user approves, ``False`` if they reject.
        Raises ``ConfirmTimeout`` if no resolution arrives within the timeout.
        """
        cmd = str(args.get("cmd") or "")
        is_officecli = tool == "exec.bash" and bool(_OFFICECLI_CMD_RE.match(cmd))
        if is_officecli and self._officecli_auto_ok:
            return True

        # Register the future before emit so synchronous bus subscribers can
        # resolve immediately (e.g. auto-approve in tests).
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._futures[call_id] = future
        self._pending_meta[call_id] = {"tool": tool, "args": args}

        self._audit_log(
            kind="confirm_request",
            tool=tool,
            call_id=call_id,
            detail={"args": args},
        )
        self._emit(
            {
                "type": "tool.confirm_request",
                "call_id": call_id,
                "tool": tool,
                "args": args,
                "payload": {"call_id": call_id, "tool": tool, "args": args},
            }
        )

        try:
            ok = await asyncio.wait_for(future, timeout=self._timeout_seconds)
        except asyncio.TimeoutError:
            raise ConfirmTimeout(
                f"Confirmation request {call_id} timed out after {self._timeout_seconds}s"
            )
        finally:
            self._futures.pop(call_id, None)
        if ok and is_officecli:
            self._officecli_auto_ok = True
        return ok

    def clear_officecli_auto(self) -> None:
        """Reset per-task officecli auto-approve (call at task start)."""
        self._officecli_auto_ok = False

    def resolve(self, call_id: str, ok: bool) -> bool:
        """Resolve a pending confirmation request.

        Returns ``True`` if a waiting future was settled, else ``False``.
        """
        meta = self._pending_meta.pop(call_id, {})
        self._audit_log(
            kind="confirm_resolve",
            tool=str(meta.get("tool") or ""),
            call_id=call_id,
            ok=ok,
            detail={"args": meta.get("args") or {}},
        )
        future = self._futures.get(call_id)
        if future is None or future.done():
            return False
        future.set_result(ok)
        return True

    async def request_plan(
        self, task_id: str, subtasks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Emit to_sub_tasks and wait for edited subtasks from the UI."""
        future: asyncio.Future[list[dict[str, Any]]] = (
            asyncio.get_running_loop().create_future()
        )
        self._plan_futures[task_id] = future
        self._emit(
            {
                "type": "to_sub_tasks",
                "task_id": task_id,
                "subtasks": subtasks,
                "needs_confirm": True,
            }
        )
        try:
            return await asyncio.wait_for(future, timeout=self._timeout_seconds)
        except asyncio.TimeoutError:
            raise ConfirmTimeout(
                f"Plan confirmation for {task_id} timed out after {self._timeout_seconds}s"
            )
        finally:
            self._plan_futures.pop(task_id, None)

    def resolve_plan(
        self, task_id: str, subtasks: list[dict[str, Any]] | None = None
    ) -> None:
        """Resolve a pending plan confirmation with optional edited subtasks."""
        future = self._plan_futures.get(task_id)
        if future is None or future.done():
            return
        future.set_result(list(subtasks or []))
