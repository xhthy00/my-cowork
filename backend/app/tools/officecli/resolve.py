"""Locate the officecli binary and probe watch support."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


ERR_NOT_FOUND = "OFFICECLI_NOT_FOUND"


def _bundled_candidates() -> list[Path]:
    """App-bundled / explicitly configured paths (highest priority)."""
    out: list[Path] = []
    env = (os.environ.get("MY_COWORK_OFFICECLI") or "").strip()
    if env:
        out.append(Path(env).expanduser())
    # Packaged layout: <resources>/bin/officecli[.exe]
    # Dev may also set MY_COWORK_OFFICECLI_DIR to resources/bin.
    bindir = (os.environ.get("MY_COWORK_OFFICECLI_DIR") or "").strip()
    if bindir:
        d = Path(bindir).expanduser()
        out.append(d / "officecli.exe")
        out.append(d / "officecli")
    return out


def _system_candidates() -> list[Path]:
    out: list[Path] = []
    which = shutil.which("officecli") or shutil.which("officecli.exe")
    if which:
        out.append(Path(which))
    home = Path.home()
    out.append(home / ".local" / "bin" / "officecli")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        out.append(Path(local) / "OfficeCli" / "officecli.exe")
    return out


def _candidate_paths() -> list[Path]:
    seen: set[str] = set()
    uniq: list[Path] = []
    for p in [*_bundled_candidates(), *_system_candidates()]:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq


def probe_watch(binary: Path) -> bool:
    """Return True if ``binary watch --help`` succeeds (AionUi rejects old npm builds)."""
    try:
        proc = subprocess.run(
            [str(binary), "watch", "--help"],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def resolve_officecli() -> Path | None:
    """Return path to a watch-capable officecli, or None.

    Preference: MY_COWORK_OFFICECLI / bundled dir → PATH → known install dirs.
    """
    for path in _candidate_paths():
        if not path.is_file():
            continue
        if not os.access(path, os.X_OK) and path.suffix.lower() != ".exe":
            if os.name != "nt":
                continue
        if probe_watch(path):
            return path
    return None
