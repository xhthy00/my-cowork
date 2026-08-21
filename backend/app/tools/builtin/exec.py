"""Shell execution tool with path guard, command filter and confirm gate."""

import asyncio
import json
import os
import subprocess
import sys
import uuid

from langchain_core.tools import BaseTool, tool

from app.guardrails.approval import ConfirmHub
from app.guardrails.command_filter import CommandFilter
from app.runtime.v2.office import office_bypass_refuse
from app.runtime.v2.office_gate import (
    OFFICE_WRITE_REFUSE,
    is_office_write_command,
    office_writes_blocked,
)
from app.sandbox.path_guard import PathGuard, PathGuardError, resolve_tool_path
from app.runtime.workspace_context import get_workspace_runtime
from app.tools.builtin.terminal_venv import (
    ensure_agent_venv,
    wrap_cmd_with_activate,
)

# Hide the extra console window on Windows; cmd.exe flashing can look like a hang.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Prevent infinite hangs (e.g. interactive python / stuck officecli).
_DEFAULT_BASH_TIMEOUT = 180.0


def decode_subprocess_output(data: bytes | str | None) -> str:
    """Decode subprocess bytes from UTF-8 or Chinese Windows GBK/GB18030.

    Forcing ``encoding='utf-8'`` on ``cmd.exe`` turns 中文路径 into mojibake;
    the model then loops on ``chcp`` / recoding and appears stuck.
    """
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("gb18030", errors="replace")


def _bash_timeout() -> float:
    raw = os.environ.get("MY_COWORK_BASH_TIMEOUT", "").strip()
    if not raw:
        return _DEFAULT_BASH_TIMEOUT
    try:
        return max(5.0, float(raw))
    except ValueError:
        return _DEFAULT_BASH_TIMEOUT


def make_bash(
    guard: PathGuard,
    command_filter: CommandFilter,
    confirm_hub: ConfirmHub | None,
    *,
    agent_name: str = "single_agent",
) -> BaseTool:
    """Build a ``bash`` tool bound to the given guard/filter/hub.

    Execution order: path guard check -> command filter check -> confirm hub
    request -> (optional) terminal venv activate -> subprocess run. Returns a
    JSON string with stdout, stderr and exit_code. When a WorkspaceRuntime is
    active, *cwd* is forced to the frozen working_directory.
    """

    @tool
    async def bash(cmd: str, cwd: str = ".") -> str:
        """Run a shell command in a whitelisted working directory.

        Windows uses cmd.exe (not bash): ``dir`` / ``type`` / ``officecli``,
        not ``ls`` / ``cat``. Unicode paths work as-is — never run ``chcp``
        or encoding-conversion loops; use fs tools if a path looks wrong.
        Word/PPT/Excel: run ``officecli``, never pandoc or LibreOffice convert.
        """
        try:
            rt = get_workspace_runtime()
            if rt is not None:
                cwd = str(rt.working_directory)
            else:
                cwd = str(resolve_tool_path(cwd))

            guard.check_path(cwd)
            command_filter.check(cmd)
        except PathGuardError as exc:
            return json.dumps(
                {"stdout": "", "stderr": str(exc), "exit_code": 1}
            )

        refused = office_bypass_refuse(cmd)
        if refused:
            return json.dumps(
                {"stdout": "", "stderr": refused, "exit_code": 1}
            )
        if office_writes_blocked() and is_office_write_command(cmd):
            return json.dumps(
                {
                    "stdout": "",
                    "stderr": OFFICE_WRITE_REFUSE,
                    "exit_code": 1,
                }
            )

        if confirm_hub is not None:
            call_id = f"exec.bash:{uuid.uuid4().hex}"
            ok = await confirm_hub.request(
                call_id, "exec.bash", {"cmd": cmd, "cwd": cwd}
            )
            if not ok:
                return json.dumps(
                    {
                        "stdout": "",
                        "stderr": "Operation rejected by user",
                        "exit_code": 1,
                    }
                )

        run_cmd = cmd
        rt = get_workspace_runtime()
        task_output = rt.task_output_root if rt is not None else None
        venv = ensure_agent_venv(agent_name, task_output)
        if venv is not None:
            run_cmd = wrap_cmd_with_activate(cmd, venv)

        timeout = _bash_timeout()
        child_env = os.environ.copy()
        child_env.setdefault("PYTHONUTF8", "1")
        child_env.setdefault("PYTHONIOENCODING", "utf-8")
        run_kwargs: dict = {
            "shell": True,
            "cwd": cwd,
            "capture_output": True,
            "timeout": timeout,
            "env": child_env,
        }
        if _CREATE_NO_WINDOW:
            run_kwargs["creationflags"] = _CREATE_NO_WINDOW
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                run_cmd,
                **run_kwargs,
            )
        except subprocess.TimeoutExpired as exc:
            out = decode_subprocess_output(exc.stdout)
            err = decode_subprocess_output(exc.stderr)
            return json.dumps(
                {
                    "stdout": out,
                    "stderr": (
                        err + f"\nCommand timed out after {timeout:.0f}s"
                    ).strip(),
                    "exit_code": 124,
                }
            )
        except Exception as exc:
            return json.dumps(
                {"stdout": "", "stderr": str(exc), "exit_code": 1}
            )
        return json.dumps(
            {
                "stdout": decode_subprocess_output(proc.stdout),
                "stderr": decode_subprocess_output(proc.stderr),
                "exit_code": proc.returncode,
            }
        )

    return bash
