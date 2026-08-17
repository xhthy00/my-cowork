"""Install officecli via the official install scripts."""

from __future__ import annotations

import os
import subprocess
from typing import Any

from app.tools.officecli.resolve import ERR_NOT_FOUND, resolve_officecli

ERR_INSTALL_FAILED = "INSTALL_FAILED"

_INSTALL_SH = "https://d.officecli.ai/install.sh"
_INSTALL_PS1 = "https://d.officecli.ai/install.ps1"


def install_officecli(*, timeout: float = 300.0) -> dict[str, Any]:
    """Run the platform installer; return status payload."""
    existing = resolve_officecli()
    if existing is not None:
        return {"status": "ready", "path": str(existing), "error_code": None}

    try:
        if os.name == "nt":
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    f"irm {_INSTALL_PS1} | iex",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        else:
            proc = subprocess.run(
                ["bash", "-lc", f"curl -fsSL {_INSTALL_SH} | bash"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "status": "error",
            "path": None,
            "error_code": ERR_INSTALL_FAILED,
            "detail": str(exc),
        }

    found = resolve_officecli()
    if found is not None:
        return {"status": "ready", "path": str(found), "error_code": None}

    detail = (proc.stderr or proc.stdout or "").strip()[-2000:]
    return {
        "status": "error",
        "path": None,
        "error_code": ERR_INSTALL_FAILED if proc.returncode != 0 else ERR_NOT_FOUND,
        "detail": detail or f"exit={proc.returncode}",
    }
