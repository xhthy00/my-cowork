"""Eigent-aligned terminal_base clone for bash activation."""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_AGENT = "single_agent"


def get_app_version() -> str:
    return os.environ.get("MY_COWORK_APP_VERSION") or "0.1.0"


def get_terminal_base_venv_path() -> Path:
    """Path to ~/.my-cowork/venvs/terminal_base-{version} (or MY_COWORK_TERMINAL_BASE)."""
    override = os.environ.get("MY_COWORK_TERMINAL_BASE")
    if override:
        return Path(override)
    return (
        Path.home()
        / ".my-cowork"
        / "venvs"
        / f"terminal_base-{get_app_version()}"
    )


def _base_python(base: Path) -> Path:
    if platform.system() == "Windows":
        return base / "Scripts" / "python.exe"
    return base / "bin" / "python"


def _cloned_python(cloned: Path) -> Path:
    return _base_python(cloned)


def clone_venv_with_symlinks(source_venv: Path, target_venv: Path) -> None:
    """Clone terminal_base into target using symlinks (Unix) or junction (Windows)."""
    is_windows = platform.system() == "Windows"
    source_cfg = source_venv / "pyvenv.cfg"
    python_home: str | None = None
    with open(source_cfg, encoding="utf-8") as f:
        for line in f:
            if line.startswith("home = "):
                python_home = line.split("=", 1)[1].strip()
                break
    if not python_home:
        raise RuntimeError(f"Could not determine Python home from {source_cfg}")

    target_venv.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_cfg, target_venv / "pyvenv.cfg")

    if is_windows:
        target_bin = target_venv / "Scripts"
        target_bin.mkdir(parents=True, exist_ok=True)
        source_scripts = source_venv / "Scripts"
        for exe in ("python.exe", "pythonw.exe"):
            src = source_scripts / exe
            if src.exists():
                shutil.copy2(src, target_bin / exe)
        for script in ("activate.bat", "activate.ps1", "deactivate.bat"):
            src = source_scripts / script
            if src.exists():
                content = src.read_text(encoding="utf-8")
                content = content.replace(str(source_venv), str(target_venv))
                (target_bin / script).write_text(content, encoding="utf-8")
        source_lib = source_venv / "Lib"
        target_lib = target_venv / "Lib"
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target_lib), str(source_lib)],
            check=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
    else:
        target_bin = target_venv / "bin"
        target_bin.mkdir(parents=True, exist_ok=True)
        python_exe = Path(python_home) / "python3"
        if not python_exe.exists():
            python_exe = Path(python_home) / "python"
        if not python_exe.exists():
            # Fall back to base venv's python (may already be a symlink)
            base_py = source_venv / "bin" / "python"
            if base_py.exists():
                python_exe = base_py.resolve()
            else:
                raise RuntimeError(f"Python not found under home={python_home}")
        os.symlink(str(python_exe), target_bin / "python")
        os.symlink("python", target_bin / "python3")

        source_bin = source_venv / "bin"
        for script in ("activate", "activate.csh", "activate.fish"):
            src = source_bin / script
            if src.exists():
                content = src.read_text(encoding="utf-8")
                content = content.replace(str(source_venv), str(target_venv))
                (target_bin / script).write_text(content, encoding="utf-8")

        source_lib = source_venv / "lib"
        os.symlink(str(source_lib), target_venv / "lib")


def ensure_agent_venv(
    agent_name: str,
    task_output_root: Path | None,
) -> Path | None:
    """Ensure {task_output_root}/{agent}/.venv clone exists; return path or None."""
    terminal_base = get_terminal_base_venv_path()
    if not _base_python(terminal_base).exists():
        logger.warning(
            "Terminal base venv not found at %s, falling back to system Python",
            terminal_base,
        )
        return None

    if task_output_root is None:
        # No workspace: activate terminal_base directly (no per-agent clone dir).
        return terminal_base

    agent = agent_name or DEFAULT_AGENT
    cloned_env_path = Path(task_output_root) / agent / ".venv"
    if _cloned_python(cloned_env_path).exists():
        return cloned_env_path

    logger.info("Cloning terminal_base venv to %s", cloned_env_path)
    try:
        cloned_env_path.parent.mkdir(parents=True, exist_ok=True)
        clone_venv_with_symlinks(terminal_base, cloned_env_path)
        return cloned_env_path
    except Exception:
        logger.exception("Failed to clone terminal_base venv")
        if cloned_env_path.exists():
            shutil.rmtree(cloned_env_path, ignore_errors=True)
        logger.warning("Falling back to system Python")
        return None


def wrap_cmd_with_activate(cmd: str, venv_path: Path) -> str:
    """Prefix shell command with venv activate (Eigent / CAMEL shell_exec)."""
    if platform.system() == "Windows":
        activate = venv_path / "Scripts" / "activate.bat"
        if not activate.exists():
            return cmd
        return f'call "{activate}" && {cmd}'
    activate = venv_path / "bin" / "activate"
    if not activate.exists():
        return cmd
    return f'. "{activate}" && {cmd}'
