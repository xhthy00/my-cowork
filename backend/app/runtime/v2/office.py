"""OfficeCLI validate helper for the v2 quality loop."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from app.tools.officecli.resolve import resolve_officecli

_PATH_RE = re.compile(
    r"(?:^|[\s`'\"=:：(\[])"
    r"(?P<path>(?:~|/|[A-Za-z]:\\)[^\s`*'\"<>|\]]+?\.(?:docx?|pptx?|xlsx|xls|pdf))",
    re.IGNORECASE | re.MULTILINE,
)
_UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")
_WRITE_TOOLS = frozenset(
    {"docx_gen", "pptx_gen", "xlsx_gen", "pdf_gen", "fs.write", "bash"}
)
_PANDOC_REFUSE = (
    "[ERROR] Do not use pandoc/LibreOffice to create Word/PPT/Excel. "
    "Load officecli-docx (or officecli-pptx / officecli-xlsx) and write the "
    "file with officecli via bash. Fallback: docx_gen / pptx_gen / xlsx_gen "
    "only if officecli is missing. Do not convert HTML/Markdown into .docx."
)
_PANDOC_TO_OFFICE_RE = re.compile(
    r"\bpandoc\b",
    re.IGNORECASE,
)
_PANDOC_OFFICE_EXT_RE = re.compile(
    r"\.(?:docx?|pptx?|xlsx)\b|-t\s+docx|--to=docx",
    re.IGNORECASE,
)
_LIBRE_CONVERT_RE = re.compile(
    r"\b(?:soffice|libreoffice)\b[\s\S]{0,200}?--convert-to\s+(?:docx?|pptx?|xlsx)\b",
    re.IGNORECASE,
)


def office_bypass_refuse(cmd: str) -> str | None:
    """Refuse HTML/md→Office converters; Word/PPT/Excel must use officecli."""
    q = (cmd or "").strip()
    if not q:
        return None
    if _PANDOC_TO_OFFICE_RE.search(q) and _PANDOC_OFFICE_EXT_RE.search(q):
        return _PANDOC_REFUSE
    if _LIBRE_CONVERT_RE.search(q):
        return _PANDOC_REFUSE
    return None


def decode_fs_path(path: str) -> str:
    """Turn literal \\uXXXX sequences into characters without touching Windows \\Users."""

    def repl(match: re.Match[str]) -> str:
        return chr(int(match.group(1), 16))

    return _UNICODE_ESCAPE_RE.sub(repl, path or "")


def officecli_available() -> bool:
    return resolve_officecli() is not None


def validate_office_file(path: str | Path, timeout: float = 30.0) -> tuple[bool, str]:
    """Run ``officecli validate`` when the binary exists; otherwise skip."""
    target = Path(decode_fs_path(str(path))).expanduser()
    if not target.is_file():
        return False, f"missing file: {target}"
    binary = resolve_officecli()
    if binary is None:
        return True, "officecli missing — skipped validate"
    try:
        proc = subprocess.run(
            [str(binary), "validate", str(target)],
            capture_output=True,
            timeout=timeout,
            check=False,
            text=True,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return False, out.strip() or f"validate exit {proc.returncode}"
    return True, out.strip() or "ok"


def paths_from_text(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for m in _PATH_RE.finditer(text or ""):
        raw = decode_fs_path(m.group("path").rstrip(".,;:)"))
        if raw not in seen:
            seen.add(raw)
            out.append(raw)
    return out


def paths_from_messages(messages: list[Any]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for msg in messages:
        name = str(getattr(msg, "name", "") or "")
        role = str(getattr(msg, "type", "") or "")
        content = str(getattr(msg, "content", "") or "")
        if name not in _WRITE_TOOLS and role not in {"tool", "ToolMessage", "ai", "AIMessage"}:
            continue
        for path in paths_from_text(content):
            if path not in seen:
                seen.add(path)
                found.append(path)
    return found


def validate_messages(messages: list[Any]) -> tuple[bool, list[str]]:
    """Validate office paths actually written in this transcript."""
    issues: list[str] = []
    for path in paths_from_messages(messages):
        ok, msg = validate_office_file(path)
        if not ok:
            issues.append(f"Office file not valid: {path} ({msg})")
    return not issues, issues
