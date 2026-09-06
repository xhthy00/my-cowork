"""Task decomposition for Eigent-style Workforce (LangGraph, no CAMEL)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.agents.workers import WORKER_IDS, normalize_worker_id
from app.runtime.todo_planner import is_office_plan_text

_LOG = logging.getLogger(__name__)
_DECOMPOSE_SYSTEM = None


def _decompose_system() -> str:
    global _DECOMPOSE_SYSTEM
    if _DECOMPOSE_SYSTEM:
        return _DECOMPOSE_SYSTEM
    from app.agents.factory import load_prompt

    text = load_prompt("planner") or ""
    if text:
        _DECOMPOSE_SYSTEM = text
    else:
        _LOG.warning(
            "planner.md missing; workforce decompose will fall back to 1 task"
        )
    return text


def _is_trivial(text: str) -> bool:
    q = (text or "").strip()
    if not q:
        return True
    if q.lower() in {"hello", "hi", "hey", "你好", "您好", "在吗", "谢谢"}:
        return True
    return len(q) < 8 and not any(
        m in q for m in ("帮", "生成", "写", "做", "搜", "create", "write", "make")
    )


def fallback_subtasks(text: str) -> list[dict[str, Any]]:
    """Heuristic single-task plan when LLM unavailable."""
    q = (text or "").strip()
    if _is_trivial(q):
        return []
    ql = q.lower()
    assignee = "browser_agent"
    if any(
        k in ql
        for k in (
            "pptx",
            "ppt",
            "docx",
            "xlsx",
            "pdf",
            "excel",
            "幻灯片",
            "文档",
            "报告",
            "汇报",
            "公文",
            "请示",
            "通知",
            "估算",
            "official-document-writing",
        )
    ):
        assignee = "document_agent"
    elif any(k in q for k in ("飞书", "lark", "消息")):
        assignee = "document_agent"
    elif any(k in ql for k in ("文件", "bash", "脚本", "终端", "write a file")):
        assignee = "developer_agent"
    elif any(k in q for k in ("旅游", "攻略", "搜索", "检索", "调研", "政策")):
        assignee = "browser_agent"
    return [
        {
            "id": "task_1",
            "content": q,
            "assignee": assignee,
            "dependencies": [],
            "status": "waiting",
            "result": "",
            "retries": 0,
        }
    ]


def normalize_subtasks(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        tid = str(item.get("id") or f"task_{i}").strip() or f"task_{i}"
        if tid in seen:
            tid = f"{tid}_{i}"
        seen.add(tid)
        assignee = normalize_worker_id(str(item.get("assignee") or "")) or "browser_agent"
        deps_raw = item.get("dependencies") or []
        deps = [str(d) for d in deps_raw if str(d).strip()] if isinstance(deps_raw, list) else []
        status = str(item.get("status") or "waiting").strip().lower()
        if status not in {"waiting", "running", "completed", "failed"}:
            status = "waiting"
        try:
            retries = int(item.get("retries") or 0)
        except (TypeError, ValueError):
            retries = 0
        out.append(
            {
                "id": tid,
                "content": content,
                "assignee": assignee if assignee in WORKER_IDS else "browser_agent",
                "dependencies": deps,
                "status": status,
                "result": str(item.get("result") or ""),
                "retries": retries,
            }
        )
    return out


def _part_text(part: Any) -> str:
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        if part.get("type") == "reasoning":
            return str(part.get("reasoning") or part.get("text") or "")
        return str(part.get("text") or "")
    return str(part)


def _llm_blobs(msg: Any) -> list[str]:
    """Content then reasoning, then both — MiniMax-M3 often JSON-only in reasoning."""
    content = getattr(msg, "content", None)
    if isinstance(content, list):
        content_text = "".join(_part_text(part) for part in content)
    else:
        content_text = str(content or "")
    additional = getattr(msg, "additional_kwargs", None) or {}
    reasoning = str(
        additional.get("reasoning_content") or additional.get("reasoning") or ""
    )
    blobs: list[str] = []
    for blob in (content_text, reasoning, f"{content_text}\n{reasoning}"):
        stripped = blob.strip()
        if stripped and stripped not in blobs:
            blobs.append(stripped)
    return blobs


def parse_subtasks_json(text: str) -> list[dict[str, Any]]:
    from app.runtime.context import strip_think_blocks

    raw = strip_think_blocks(text or "").strip()
    if not raw:
        return []
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()
    start = raw.find("[")
    end = raw.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return []
    return normalize_subtasks(data)


_MD_ONLY_BRIEF = "将内容写入 Markdown 文件（.md）。"


def align_subtasks_to_user_format(
    text: str, subtasks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Drop invented Word/officecli briefs when the user asked only for Markdown.

    Eigent document agent writes the user-specified extension via write_to_file;
    unspecified format is HTML. Workforce Progress is this subtask list.
    """
    from app.graphs.routing import wants_document, wants_markdown_file

    q = (text or "").strip()
    if not subtasks or not (wants_markdown_file(q) and not wants_document(q)):
        return subtasks
    out: list[dict[str, Any]] = []
    for item in subtasks:
        row = dict(item)
        if is_office_plan_text(str(row.get("content") or "")):
            row["content"] = _MD_ONLY_BRIEF
        out.append(row)
    return out


async def decompose_subtasks(text: str, llm: Any | None) -> list[dict[str, Any]]:
    q = (text or "").strip()
    if _is_trivial(q):
        return []
    if llm is None:
        return align_subtasks_to_user_format(q, fallback_subtasks(q))
    prompt = f"User request:\n{q}\n\nReturn the JSON subtask array now."
    try:
        if hasattr(llm, "ainvoke"):
            msg = await llm.ainvoke(
                [
                    {"role": "system", "content": _decompose_system()},
                    {"role": "user", "content": prompt},
                ]
            )
        elif hasattr(llm, "invoke"):
            msg = llm.invoke(
                [
                    {"role": "system", "content": _decompose_system()},
                    {"role": "user", "content": prompt},
                ]
            )
        else:
            msg = None
        todos: list[dict[str, Any]] = []
        if msg is not None:
            for blob in _llm_blobs(msg):
                todos = parse_subtasks_json(blob)
                if todos:
                    break
        if todos:
            return align_subtasks_to_user_format(q, todos)
        _LOG.warning("decompose produced no JSON subtasks; using single-task fallback")
    except Exception:
        _LOG.exception("decompose llm failed; using single-task fallback")
    return align_subtasks_to_user_format(q, fallback_subtasks(q))
