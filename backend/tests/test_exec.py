import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.guardrails.approval import ConfirmHub
from app.guardrails.command_filter import DEFAULT_PATTERNS, CommandFilter, CommandForbidden
from app.sandbox.path_guard import PathGuard
from app.tools.builtin.exec import make_bash


class FakeConfirmHub:
    def __init__(self, ok: bool) -> None:
        self._ok = ok

    async def request(self, call_id: str, tool: str, args: dict) -> bool:
        return self._ok

    def resolve(self, call_id: str, ok: bool) -> None:
        pass


def _make(tool, tmp_path, *, ok: bool = True, filter_patterns: list[str] | None = None):
    """Build a bash tool bound to private deps, return the tool."""
    guard = PathGuard([str(tmp_path)])
    command_filter = CommandFilter(filter_patterns or [])
    confirm_hub = FakeConfirmHub(ok) if ok is not None else None
    return tool(guard, command_filter, confirm_hub)


class TestExecBash:
    @pytest.mark.asyncio
    async def test_cwd_outside_whitelist_returns_error(self, tmp_path):
        # Use a sibling path outside the whitelist, not a fixed /tmp/outside
        # which on macOS resolves through /tmp -> /private/tmp and can race
        # the whitelist sibling.
        outside = tmp_path.parent / "outside-whitelist-xyz"
        bash = _make(make_bash, tmp_path)
        raw = await bash.ainvoke({"cmd": "ls", "cwd": str(outside)})
        payload = json.loads(raw)
        assert payload["exit_code"] == 1
        assert "whitelist" in payload["stderr"].lower()

    @pytest.mark.asyncio
    async def test_forbidden_command_raises(self, tmp_path):
        bash = _make(make_bash, tmp_path, filter_patterns=list(DEFAULT_PATTERNS))
        with pytest.raises(CommandForbidden):
            await bash.ainvoke({"cmd": "rm -rf /", "cwd": str(tmp_path)})

    @pytest.mark.asyncio
    async def test_user_denied_returns_rejection(self, tmp_path):
        bash = _make(make_bash, tmp_path, ok=False)

        result = await bash.ainvoke({"cmd": "ls", "cwd": str(tmp_path)})

        parsed = json.loads(result)
        assert parsed["exit_code"] == 1
        assert "rejected" in parsed["stderr"].lower()

    @pytest.mark.asyncio
    async def test_remote_channel_auto_approves_bash(self, tmp_path):
        from app.guardrails.approval import ConfirmHub, reset_remote_channel, set_remote_channel

        guard = PathGuard([str(tmp_path)])
        hub = ConfirmHub(timeout_seconds=30)
        bash = make_bash(guard, CommandFilter([]), hub)
        token = set_remote_channel(True)
        try:
            raw = await bash.ainvoke({"cmd": "echo hi", "cwd": str(tmp_path)})
        finally:
            reset_remote_channel(token)
        payload = json.loads(raw)
        assert payload["exit_code"] == 0
        assert "hi" in payload["stdout"]

    @pytest.mark.asyncio
    async def test_user_allowed_runs_subprocess(self, tmp_path):
        bash = _make(make_bash, tmp_path, ok=True)

        mock_proc = MagicMock()
        mock_proc.stdout = "hello\n"
        mock_proc.stderr = ""
        mock_proc.returncode = 0

        with patch("app.tools.builtin.exec.subprocess.run", return_value=mock_proc) as run:
            result = await bash.ainvoke({"cmd": "echo hello", "cwd": str(tmp_path)})

        parsed = json.loads(result)
        assert parsed["exit_code"] == 0
        assert parsed["stdout"] == "hello\n"
        assert run.call_args.kwargs.get("capture_output") is True
        assert "encoding" not in run.call_args.kwargs
        assert run.call_args.kwargs.get("timeout") == 180.0

    @pytest.mark.asyncio
    async def test_timeout_returns_124(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MY_COWORK_BASH_TIMEOUT", "5")
        bash = _make(make_bash, tmp_path, ok=True)

        def _hang(*_a, **_k):
            raise subprocess.TimeoutExpired(cmd="sleep", timeout=5)

        with patch("app.tools.builtin.exec.subprocess.run", side_effect=_hang):
            result = await bash.ainvoke({"cmd": "sleep 99", "cwd": str(tmp_path)})
        parsed = json.loads(result)
        assert parsed["exit_code"] == 124
        assert "timed out" in parsed["stderr"].lower()

    @pytest.mark.asyncio
    async def test_invalid_utf8_stdout_does_not_crash(self, tmp_path):
        """Binary/incomplete UTF-8 (e.g. truncated docx via head -c) must soft-decode."""
        bash = _make(make_bash, tmp_path, ok=True)
        # 0xe4 alone is an incomplete UTF-8 lead byte — classic crash with strict decode.
        result = await bash.ainvoke({"cmd": "printf '\\xe4'", "cwd": str(tmp_path)})
        parsed = json.loads(result)
        assert parsed["exit_code"] == 0
        assert isinstance(parsed["stdout"], str)
        assert len(parsed["stdout"]) >= 1

    def test_decode_gbk_windows_paths(self):
        from app.tools.builtin.exec import decode_subprocess_output

        raw = "C:\\Users\\张三\\桌面\\报告.docx".encode("gbk")
        assert "张三" in decode_subprocess_output(raw)
        assert "桌面" in decode_subprocess_output(raw)
        assert decode_subprocess_output("already-str") == "already-str"
        utf = "C:\\Users\\张三\\桌面\\报告.docx".encode("utf-8")
        assert "张三" in decode_subprocess_output(utf)
