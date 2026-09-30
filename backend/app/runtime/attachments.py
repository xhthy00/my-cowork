"""Parse chat attachment markers and stage files into the task workdir."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

_ATTACHMENT_RE = re.compile(r"\[附件:\s*([^\]]+)\]")


def extract_attachment_paths(text: str) -> list[str]:
    """Return paths listed in ``[附件: a, b]`` markers (order preserved)."""
    out: list[str] = []
    for match in _ATTACHMENT_RE.finditer(text or ""):
        for part in match.group(1).split(","):
            p = part.strip().strip("\"'")
            if p and p not in out:
                out.append(p)
    return out


def is_absolute_fs_path(path: str) -> bool:
    p = Path(path).expanduser()
    return p.is_absolute()


def stage_attachments_for_task(
    text: str,
    workdir: Path,
    guard: Any | None = None,
) -> str:
    """Whitelist attachment parents, copy into ``workdir/attachments``, rewrite text.

    Filename-only markers cannot be located; a system note is appended so the
    agent does not probe ``/``.
    """
    paths = extract_attachment_paths(text)
    if not paths:
        return text

    staged_dir = workdir / "attachments"
    staged_dir.mkdir(parents=True, exist_ok=True)
    replacements: dict[str, str] = {}
    missing: list[str] = []

    for raw in paths:
        expanded = Path(raw).expanduser()
        if not expanded.is_absolute():
            missing.append(raw)
            continue
        try:
            src = expanded.resolve()
        except Exception:
            missing.append(raw)
            continue
        if not src.is_file():
            missing.append(raw)
            continue

        if guard is not None:
            try:
                guard.add_whitelist(str(src.parent))
            except Exception:
                pass

        dest = staged_dir / src.name
        if dest.resolve() != src:
            shutil.copy2(src, dest)
        if guard is not None:
            try:
                guard.add_whitelist(str(staged_dir))
            except Exception:
                pass
        replacements[raw] = str(dest.resolve())

    new_text = text
    for old, new in replacements.items():
        new_text = new_text.replace(old, new)

    notes: list[str] = []
    if replacements:
        listed = "\n".join(f"- {p}" for p in replacements.values())
        notes.append(
            "附件已就绪（可直接用下列绝对路径读取，勿访问 / 或其他未授权目录）：\n"
            + listed
        )
    if missing:
        notes.append(
            "以下附件缺少绝对路径或文件不存在，无法读取："
            + "、".join(missing)
            + "。请用户重新用回形针选择文件后再试。"
        )
    if notes:
        new_text = new_text.rstrip() + "\n\n[系统]\n" + "\n".join(notes)
    return new_text
