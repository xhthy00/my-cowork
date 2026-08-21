"""Scan this-run office files for completion gating (Eigent: no process cleanup)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


OFFICE_EXT = {".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".pdf"}
SKIP_DIRS = {
    "camel_logs",
    ".venv",
    "node_modules",
    ".git",
    "__pycache__",
}


def list_new_office_files(
    workdir: Path | str,
    *,
    min_mtime: float,
    already: Iterable[str | Path] = (),
) -> list[str]:
    """Office files under *workdir* written at/after *min_mtime*.

    Used only as a completion-gate fallback when write-tool events were missed.
    Does not emit UI artifacts and does not delete anything.
    """
    try:
        root = Path(workdir).expanduser().resolve()
    except OSError:
        return []
    if not root.is_dir():
        return []

    seen: set[str] = set()
    for raw in already:
        try:
            seen.add(str(Path(str(raw)).expanduser().resolve()))
        except OSError:
            key = str(raw).replace("\\", "/")
            if key:
                seen.add(key)

    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [
            d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
        ]
        for name in filenames:
            path = Path(dirpath) / name
            try:
                resolved = path.resolve()
            except OSError:
                continue
            key = str(resolved)
            if key in seen:
                continue
            if not resolved.is_file():
                continue
            if resolved.suffix.lower() not in OFFICE_EXT:
                continue
            try:
                if resolved.stat().st_mtime < min_mtime - 5.0:
                    continue
            except OSError:
                continue
            seen.add(key)
            found.append(key)
    found.sort()
    return found
