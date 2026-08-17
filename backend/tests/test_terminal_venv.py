"""Tests for terminal_base clone and bash activate wrapping."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.tools.builtin.exec import make_bash
from app.tools.builtin.terminal_venv import (
    clone_venv_with_symlinks,
    ensure_agent_venv,
    wrap_cmd_with_activate,
)
from app.guardrails.command_filter import CommandFilter
from app.sandbox.path_guard import PathGuard


class FakeConfirmHub:
    def __init__(self, ok: bool = True) -> None:
        self._ok = ok

    async def request(self, call_id: str, tool: str, args: dict) -> bool:
        return self._ok


def _make_fake_base(tmp_path: Path) -> Path:
    """Minimal terminal_base layout usable by clone (Unix)."""
    base = tmp_path / "terminal_base"
    bin_dir = base / "bin"
    lib_dir = base / "lib" / "python3.10" / "site-packages"
    bin_dir.mkdir(parents=True)
    lib_dir.mkdir(parents=True)
    # Real-ish python home with a python3 stub
    home = tmp_path / "pyhome"
    home.mkdir()
    py = home / "python3"
    py.write_text("#!/bin/sh\necho ok\n")
    py.chmod(0o755)
    (base / "pyvenv.cfg").write_text(f"home = {home}\ninclude-system-site-packages = false\n")
    (bin_dir / "python").symlink_to(py)
    (bin_dir / "activate").write_text(
        f'VIRTUAL_ENV="{base}"\nexport VIRTUAL_ENV\n'
    )
    return base


class TestCloneVenv:
    def test_clone_creates_python_and_lib_symlink(self, tmp_path):
        base = _make_fake_base(tmp_path)
        target = tmp_path / "agent" / ".venv"
        clone_venv_with_symlinks(base, target)
        assert (target / "bin" / "python").exists()
        assert (target / "lib").is_symlink()
        assert (target / "bin" / "activate").exists()
        act = (target / "bin" / "activate").read_text()
        assert str(target) in act
        assert f'VIRTUAL_ENV="{target}"' in act

    def test_ensure_agent_venv_fallback_when_base_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MY_COWORK_TERMINAL_BASE", str(tmp_path / "missing"))
        assert ensure_agent_venv("developer_agent", tmp_path / "out") is None

    def test_ensure_agent_venv_clones_under_task_output(self, tmp_path, monkeypatch):
        base = _make_fake_base(tmp_path)
        monkeypatch.setenv("MY_COWORK_TERMINAL_BASE", str(base))
        out = tmp_path / "task_out"
        venv = ensure_agent_venv("developer_agent", out)
        assert venv == out / "developer_agent" / ".venv"
        assert (venv / "bin" / "python").exists()
        # Second call reuses
        assert ensure_agent_venv("developer_agent", out) == venv

    def test_ensure_without_task_output_returns_base(self, tmp_path, monkeypatch):
        base = _make_fake_base(tmp_path)
        monkeypatch.setenv("MY_COWORK_TERMINAL_BASE", str(base))
        assert ensure_agent_venv("single_agent", None) == base


class TestWrapActivate:
    def test_unix_wrap(self, tmp_path):
        venv = tmp_path / ".venv"
        (venv / "bin").mkdir(parents=True)
        (venv / "bin" / "activate").write_text("# activate\n")
        wrapped = wrap_cmd_with_activate("python script.py", venv)
        assert wrapped.startswith('. "')
        assert "activate" in wrapped
        assert wrapped.endswith(" && python script.py")


class TestBashActivate:
    @pytest.mark.asyncio
    async def test_bash_prefixes_activate_when_base_exists(self, tmp_path, monkeypatch):
        base = _make_fake_base(tmp_path)
        monkeypatch.setenv("MY_COWORK_TERMINAL_BASE", str(base))
        guard = PathGuard([str(tmp_path)])
        bash = make_bash(guard, CommandFilter([]), FakeConfirmHub(), agent_name="dev")

        mock_proc = MagicMock()
        mock_proc.stdout = "ok\n"
        mock_proc.stderr = ""
        mock_proc.returncode = 0

        with patch("app.tools.builtin.exec.subprocess.run", return_value=mock_proc) as run:
            raw = await bash.ainvoke({"cmd": "echo hi", "cwd": str(tmp_path)})

        assert json.loads(raw)["exit_code"] == 0
        run_cmd = run.call_args.args[0]
        assert "activate" in run_cmd
        assert "echo hi" in run_cmd

    @pytest.mark.asyncio
    async def test_bash_no_activate_when_base_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MY_COWORK_TERMINAL_BASE", str(tmp_path / "nope"))
        guard = PathGuard([str(tmp_path)])
        bash = make_bash(guard, CommandFilter([]), FakeConfirmHub(), agent_name="dev")

        mock_proc = MagicMock()
        mock_proc.stdout = ""
        mock_proc.stderr = ""
        mock_proc.returncode = 0

        with patch("app.tools.builtin.exec.subprocess.run", return_value=mock_proc) as run:
            await bash.ainvoke({"cmd": "echo hi", "cwd": str(tmp_path)})

        assert run.call_args.args[0] == "echo hi"
