"""Eigent has no runtime that rewrites the chat answer into a Markdown file.

Files are created only when the agent calls write tools (``fs_write`` /
officecli). This module kept the old auto-md helper as a no-op so existing
imports and tests stay explicit about the policy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def wants_markdown_report(user_text: str) -> bool:
    """Always False — Eigent does not auto-save a Markdown preview copy."""
    _ = user_text
    return False


def markdown_filename(user_text: str) -> str:
    raw = (user_text or "").strip() or "调研报告"
    return raw[:32] + ".md"


def maybe_write_markdown_report(
    user_text: str,
    messages: list[Any],
    *,
    workdir: Path | None = None,
    body: str | None = None,
) -> tuple[list[Any], str | None]:
    """No-op. Eigent FileToolkit only writes when the agent calls write_to_file."""
    _ = (user_text, workdir, body)
    return list(messages), None
