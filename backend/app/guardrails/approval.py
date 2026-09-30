"""Async approval gate with ConfirmHub."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from contextvars import ContextVar, Token
from typing import Any, Callable

_OFFICECLI_CMD_RE = re.compile(r"^\s*officecli(\s|$)")
REMOTE_CHANNEL_SOURCES = frozenset({"weixin", "lark", "telegram", "dingtalk"})
_remote_channel: ContextVar[bool] = ContextVar("confirm_remote_channel", default=False)
_automation_policy: ContextVar[tuple | None] = ContextVar(
    "automation_approval_policy", default=None
)
_GRANT_TARGETS = {
    "fs.write": "path", "docx.gen": "out_path", "pptx.gen": "out_path",
    "xlsx.gen": "out_path", "pdf.gen": "out_path", "browser_navigate": "url",
    "lark.send_message": "chat_id",
}
_WORKSPACE_WRITES = {"fs.write", "docx.gen", "pptx.gen", "xlsx.gen", "pdf.gen", "browser_screenshot"}
# Browser writes use the same unattended-task opt-in as shell execution. The
# persisted flag keeps its original name so existing task settings still apply.
_BROWSER_INTERACTIONS = {"browser_click", "browser_type", "browser_select", "browser_upload_file"}


def valid_automation_grants(raw: list[dict[str, str]]) -> list[dict[str, str]]:
    """Only exact, target-bound eligible tools can receive standing grants."""
    result: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict) or item.get("access") != "write":
            continue
        tool, target = str(item.get("tool") or "").strip(), str(item.get("target") or "").strip()
        if tool not in _GRANT_TARGETS or not target or "*" in target:
            continue
        grant = {"tool": tool, "target": target}
        if grant not in result:
            result.append(grant)
    return result


def valid_automation_commands(raw: list[str]) -> list[str]:
    """Persist only explicit, single-line commands; matching remains exact."""
    if not isinstance(raw, list):
        raise ValueError("Allowed commands must be a list")
    commands: list[str] = []
    for value in raw:
        if not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise ValueError("Each allowed command must contain 1–2000 characters")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Allowed commands must be single-line text")
        command = value.strip()
        if command not in commands:
            commands.append(command)
    return commands


def set_automation_policy(workspace: str | None, grants: list[dict[str, str]],
                          current_grants: Callable[[], list[dict[str, str]]] | None = None,
                          commands: list[str] | None = None,
                          current_commands: Callable[[], list[str]] | None = None,
                          auto_approve_commands: bool = False,
                          current_auto_approve_commands: Callable[[], bool] | None = None) -> Token:
    entries = tuple((str(item.get("tool") or ""), str(item.get("target") or "")) for item in grants)
    return _automation_policy.set((workspace, entries, current_grants,
                                   tuple(commands or ()), current_commands,
                                   auto_approve_commands, current_auto_approve_commands))


def reset_automation_policy(token: Token) -> None:
    _automation_policy.reset(token)


def _automation_allows(tool: str, args: dict[str, Any], policy: tuple) -> bool:
    (workspace, grants, current_grants, commands, current_commands,
     auto_approve_commands, current_auto_approve_commands) = policy
    if current_grants is not None:
        grants = tuple((str(item.get("tool") or ""), str(item.get("target") or ""))
                       for item in current_grants())
    auto_approve = (current_auto_approve_commands() if current_auto_approve_commands is not None
                    else auto_approve_commands)
    if tool == "exec.bash":
        if not workspace:
            return False
        cmd, cwd = args.get("cmd"), args.get("cwd")
        if not isinstance(cmd, str) or not isinstance(cwd, str):
            return False
        try:
            same_workspace = Path(cwd).resolve() == Path(workspace).resolve()
        except (OSError, ValueError):
            return False
        if not same_workspace:
            return False
        if auto_approve:
            return True
        allowed = current_commands() if current_commands is not None else commands
        return cmd.strip() in allowed
    if tool in _BROWSER_INTERACTIONS and auto_approve:
        return True
    if tool in {"browser_navigate", "browser_close"}:
        return True  # Browser navigation/read-only close; interactions still ask.
    if workspace and tool in _WORKSPACE_WRITES:
        path = args.get("path") or args.get("out_path")
        if isinstance(path, str) and path:
            try:
                if Path(path).resolve().is_relative_to(Path(workspace).resolve()):
                    return True
            except (OSError, ValueError):
                pass
    target_key = _GRANT_TARGETS.get(tool)
    target = args.get(target_key) if target_key else None
    return isinstance(target, str) and (tool, target) in grants


def set_remote_channel(enabled: bool) -> Token:
    return _remote_channel.set(bool(enabled))


def reset_remote_channel(token: Token) -> None:
    _remote_channel.reset(token)


def is_remote_channel() -> bool:
    return _remote_channel.get()


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

    async def request(self, call_id: str, tool: str, args: dict[str, Any], *, tool_title: str | None = None) -> bool:
        """Emit a confirmation request and await user resolution.

        Returns ``True`` if the user approves, ``False`` if they reject.
        Raises ``ConfirmTimeout`` if no resolution arrives within the timeout.
        Remote IM channels have no confirm UI (AionUi YOLO), so tool calls
        are auto-approved instead of waiting on the desktop modal.
        """
        automation_policy = _automation_policy.get()
        if automation_policy is not None and _automation_allows(tool, args, automation_policy):
            self._audit_log(kind="confirm_request", tool=tool, call_id=call_id,
                            ok=True, detail={"automation_scoped_grant": True})
            return True
        if automation_policy is None and is_remote_channel():
            self._audit_log(
                kind="confirm_request",
                tool=tool,
                call_id=call_id,
                ok=True,
                detail={"args": args, "remote_auto_approved": True},
            )
            return True

        cmd = str(args.get("cmd") or "")
        is_officecli = tool == "exec.bash" and bool(_OFFICECLI_CMD_RE.match(cmd))
        if automation_policy is None and is_officecli and self._officecli_auto_ok:
            return True

        # Register the future before emit so synchronous bus subscribers can
        # resolve immediately (e.g. auto-approve in tests).
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._futures[call_id] = future
        from app.observability.trace import _runtime_task_id
        title = {"tool_title": tool_title} if tool_title else {}
        self._pending_meta[call_id] = {"tool": tool, "args": args, "task_id": _runtime_task_id() or "", **title}

        self._audit_log(
            kind="confirm_request",
            tool=tool,
            call_id=call_id,
            detail={"args": args},
        )
        confirm_event: dict[str, Any] = {
            "type": "tool.confirm_request",
            "call_id": call_id,
            "tool": tool,
            "args": args,
            **title,
            "payload": {"call_id": call_id, "tool": tool, "args": args, **title},
        }
        try:
            from app.runtime.todo_context import get_todo_runtime

            todo = get_todo_runtime()
            if todo is not None and getattr(todo, "task_id", None):
                tid = str(todo.task_id)
                confirm_event["task_id"] = tid
                confirm_event["payload"] = {**confirm_event["payload"], "task_id": tid}
                self._pending_meta[call_id]['task_id'] = tid
        except Exception:
            pass
        self._emit(confirm_event)

        try:
            ok = (await future if automation_policy is not None
                  else await asyncio.wait_for(future, timeout=self._timeout_seconds))
        except asyncio.TimeoutError:
            raise ConfirmTimeout(
                f"Confirmation request {call_id} timed out after {self._timeout_seconds}s"
            )
        finally:
            self._futures.pop(call_id, None)
            self._pending_meta.pop(call_id, None)
        if ok and is_officecli and automation_policy is None:
            self._officecli_auto_ok = True
        return ok

    def clear_officecli_auto(self) -> None:
        """Reset per-task officecli auto-approve (call at task start)."""
        self._officecli_auto_ok = False

    def pending(self, task_id: str) -> list[dict[str, Any]]:
        return [{"call_id": call_id, **meta} for call_id, meta in self._pending_meta.items()
                if meta.get("task_id") == task_id and call_id in self._futures and not self._futures[call_id].done()]

    def resolve(self, call_id: str, ok: bool) -> bool:
        """Resolve a pending confirmation request.

        Returns ``True`` if a waiting future was settled, else ``False``.
        """
        meta = self._pending_meta.pop(call_id, {})
        self._audit_log(
            kind="confirm_resolve",
            tool=str(meta.get("tool") or ""),
            call_id=call_id,
            task_id=str(meta.get("task_id") or ""),
            ok=ok,
            detail={"args": meta.get("args") or {}},
        )
        future = self._futures.get(call_id)
        if future is None or future.done():
            return False
        future.set_result(ok)
        self._emit({'type': 'tool.confirm_resolved', 'task_id': meta.get('task_id', ''), 'call_id': call_id, 'ok': ok})
        return True

    async def request_plan(
        self, task_id: str, subtasks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Emit to_sub_tasks and wait for edited subtasks from the UI."""
        if is_remote_channel():
            return list(subtasks)
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
            return (await future if _automation_policy.get() is not None
                    else await asyncio.wait_for(future, timeout=self._timeout_seconds))
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
