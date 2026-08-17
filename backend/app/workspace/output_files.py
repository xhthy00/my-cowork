"""Classify deliverable vs process output files (aligned with renderer outputFiles.ts)."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Iterable


DELIVERABLE_EXT = re.compile(
    r"\.(png|jpe?g|webp|gif|svg|bmp|pdf|docx?|pptx?|xlsx|csv|html?|md)$",
    re.IGNORECASE,
)

SCRATCH_EXT = re.compile(
    r"\.(txt|json|py|sh|bash|js|mjs|cjs|ts|tsx|log|tmp)$",
    re.IGNORECASE,
)

PROCESS_NAME = re.compile(
    r"^(requirements\.txt|pyproject\.toml|package\.json|uv\.lock|\.gitignore|skill\.md)$",
    re.IGNORECASE,
)

INTERMEDIATE_NAME = re.compile(
    r"(^|[_-])(part\d*|skeleton|wrapper|head|style|script\d*|script_b64|test|tmp|temp|"
    r"draft|chart_data|with_data|html_head|html_script|html_part)([._-]|$)",
    re.IGNORECASE,
)

# Throwaway probe/test file names agents create while experimenting
# (t_nf_0.0.xlsx, tC.xlsx, x1_check.xlsx, tmp_build.xlsx, …).
# Multi-letter keywords need a separator/end after them (checklist.xlsx stays);
# single letters (t/x/z) REQUIRE a separator so table_销售.xlsx survives.
_PROBE_NAME = re.compile(
    r"^(?:(?:tmp|temp|test|try|probe|chk|check|demo|sample)\d*(?=[_-]|$)|(?:[txz]\d*)[_-])",
    re.IGNORECASE,
)

# Excel number-format tokens (#,##0 / 0.0% / $#,##0) accidentally baked into
# probe file names — never legitimate deliverable names.
_FORMAT_TOKEN = re.compile(r"[#%]|\$#")


def _looks_like_probe_basename(stem: str) -> bool:
    """True when *stem* matches a throwaway probe pattern (e.g. t_nf_0.0)."""
    # Ultra-short throwaway stems: tC, x2, z9 …
    if len(stem) <= 3 and re.match(r"^[txzTXZ][A-Z0-9]", stem):
        return True
    match = _PROBE_NAME.match(stem)
    if match is None:
        return False
    rest = stem[match.end() :]
    # Only treat as probe when the remainder is short (a tag, not a real title).
    return len(rest) <= 8


def is_deliverable_basename(name: str) -> bool:
    """True if *name* (filename only) looks like a final user-facing deliverable."""
    if not name or name.startswith("."):
        return False
    if PROCESS_NAME.search(name):
        return False
    if SCRATCH_EXT.search(name):
        return False
    if INTERMEDIATE_NAME.search(name):
        return False
    if _FORMAT_TOKEN.search(name):
        return False
    stem = name.rsplit(".", 1)[0] if "." in name else name
    if _looks_like_probe_basename(stem):
        return False
    return bool(DELIVERABLE_EXT.search(name))


def is_deliverable_output_path(file_path: str) -> bool:
    """Return True if *file_path* looks like a final user-facing deliverable."""
    normalized = file_path.replace("\\", "/")
    if "/_scratch/" in normalized or "/.venv/" in normalized:
        return False
    name = normalized.rsplit("/", 1)[-1] if normalized else ""
    return is_deliverable_basename(name)


def is_process_output_path(file_path: str) -> bool:
    """Process/intermediate file — inverse of deliverable heuristic."""
    return not is_deliverable_output_path(file_path)


def list_new_deliverables(
    workdir: Path | str,
    *,
    min_mtime: float,
    already: Iterable[str | Path] = (),
) -> list[str]:
    """Deliverable files under *workdir* written at/after *min_mtime*.

    Used at graph.end to surface files the agent created via bash/python
    without a parseable path in tool output (and when a later tool error
    aborts before ``artifact.file`` is emitted).
    """
    try:
        root = Path(workdir).expanduser().resolve()
    except OSError:
        return []
    if not root.is_dir():
        return []

    skip_dirs = {"_scratch", ".venv", "node_modules", ".git", "__pycache__"}
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
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
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
            if not is_deliverable_output_path(key):
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


def _is_under(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _unique_dest(root: Path, name: str) -> Path:
    dest = root / name
    if not dest.exists():
        return dest
    stem = Path(name).stem
    suffix = Path(name).suffix
    i = 1
    while True:
        cand = root / f"{stem}_{i}{suffix}"
        if not cand.exists():
            return cand
        i += 1


def cleanup_process_files(
    workdir: Path | str,
    written_paths: Iterable[str | Path],
) -> tuple[list[str], list[str]]:
    """Delete ``_scratch`` and tracked process files under *workdir*.

    Deliverable-looking files found under ``_scratch`` are moved to *workdir*
    first (agents sometimes write finals into scratch by mistake). Only paths
    that resolve inside *workdir* are touched.

    Returns ``(cleaned_paths, rescued_paths)``.
    """
    root = Path(workdir)
    try:
        root = root.resolve()
    except OSError:
        return [], []

    cleaned: list[str] = []
    rescued: list[str] = []

    scratch = root / "_scratch"
    if scratch.exists():
        try:
            for p in list(scratch.rglob("*")):
                if not p.is_file():
                    continue
                if not is_deliverable_basename(p.name):
                    continue
                dest = _unique_dest(root, p.name)
                try:
                    shutil.move(str(p), str(dest))
                    rescued.append(str(dest.resolve()))
                except OSError:
                    continue
        except OSError:
            pass
        try:
            for p in scratch.rglob("*"):
                if p.is_file():
                    cleaned.append(str(p))
        except OSError:
            pass
        shutil.rmtree(scratch, ignore_errors=True)
        if not scratch.exists():
            cleaned.append(str(scratch))

    seen: set[str] = set()
    for raw in written_paths:
        try:
            path = Path(str(raw)).expanduser()
            path = path.resolve()
        except OSError:
            continue
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if not _is_under(root, path):
            continue
        if not path.exists() or not path.is_file():
            continue
        if is_deliverable_output_path(str(path)):
            continue
        if not is_process_output_path(str(path)):
            continue
        try:
            path.unlink(missing_ok=True)
            cleaned.append(str(path))
        except OSError:
            continue

    return cleaned, rescued
