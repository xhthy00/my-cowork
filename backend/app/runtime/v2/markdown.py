"""Default research deliverable: a Markdown file for the preview panel."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage

from app.runtime.context import is_user_facing_answer
from app.runtime.v2.synthesize import best_user_facing_text

_RESEARCH = (
    "调研",
    "最新",
    "政策",
    "攻略",
    "价格",
    "新闻",
    "对比",
    "分析",
    "梳理",
    "整理",
    "摘要",
    "总结",
)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_UNSAFE_RE = re.compile(r'[#@\[\]{}\\/:*?"<>|\n\r]+')


def wants_markdown_report(user_text: str) -> bool:
    """True when the default deliverable should be a Markdown file, not Word."""
    from app.graphs.routing import wants_document, wants_markdown_file

    q = (user_text or "").strip()
    if not q:
        return False
    if wants_document(q):
        return False
    if wants_markdown_file(q):
        return True
    return any(token in q for token in _RESEARCH)


def _already_wrote_markdown(messages: list[Any]) -> bool:
    for msg in messages or []:
        name = str(getattr(msg, "name", "") or "")
        content = str(getattr(msg, "content", "") or "")
        if name in {"fs.write", "fs_write"} and ".md" in content.lower():
            return True
        if "Wrote " in content and content.lower().rstrip().endswith(".md"):
            return True
    return False


def markdown_filename(user_text: str) -> str:
    raw = _UNSAFE_RE.sub("", user_text or "").strip()
    raw = re.sub(r"\s+", "", raw)
    if not raw:
        raw = "调研报告"
    return raw[:32] + ".md"


def maybe_write_markdown_report(
    user_text: str,
    messages: list[Any],
    *,
    workdir: Path | None = None,
    body: str | None = None,
) -> tuple[list[Any], str | None]:
    """Write a Markdown report after the synthesized chat answer exists."""
    if not wants_markdown_report(user_text):
        return list(messages), None
    text = (body or "").strip() or best_user_facing_text(messages)
    if not is_user_facing_answer(text):
        return list(messages), None
    if len(_CJK_RE.findall(text)) < 80:
        return list(messages), None
    if _already_wrote_markdown(messages):
        return list(messages), None
    if workdir is None:
        from app.runtime.workspace_context import get_workspace_runtime

        rt = get_workspace_runtime()
        if rt is None:
            return list(messages), None
        workdir = Path(rt.working_directory)
    workdir.mkdir(parents=True, exist_ok=True)
    path = workdir / markdown_filename(user_text)
    path.write_text(text.strip() + "\n", encoding="utf-8")
    try:
        from app.workspace.overlay import maybe_record_write

        maybe_record_write(path)
    except Exception:
        pass
    note = f"已整理为 Markdown：{path}"
    return [*messages, AIMessage(content=note)], str(path)
