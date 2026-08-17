"""Task decomposition for Eigent-style Workforce (LangGraph, no CAMEL)."""

from __future__ import annotations

import json
import re
from typing import Any

from app.agents.workers import WORKER_IDS, normalize_worker_id

_DECOMPOSE_SYSTEM = """你是 Workforce 任务规划器。把用户目标拆成可并行的自包含子任务。

规则：
- 复杂任务拆成 2–6 个子任务；简单任务可只产出 1 个清晰子任务。
- 每个子任务必须自包含（执行者不知道父任务全文）。
- 明确 deliverable；可并行的步骤不要串行（dependencies 留空数组）。
- assignee 只能是：developer_agent | browser_agent | document_agent | multi_modal_agent
  - developer_agent: 本地文件/终端/脚本
  - browser_agent: 搜索/浏览/调研
  - document_agent: 生成 docx/pptx/xlsx/pdf、写文件、飞书通知
  - multi_modal_agent: 媒体产物整理、共享笔记协同
- 只输出 JSON 数组，不要 markdown，不要解释。
- 用户用中文则 content 用中文。

每项字段：
{"id":"task_1","content":"...","assignee":"browser_agent","dependencies":[]}
dependencies 为其他子任务 id 列表。
"""


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


def parse_subtasks_json(text: str) -> list[dict[str, Any]]:
    raw = (text or "").strip()
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


async def decompose_subtasks(text: str, llm: Any | None) -> list[dict[str, Any]]:
    q = (text or "").strip()
    if _is_trivial(q):
        return []
    if llm is None:
        return fallback_subtasks(q)
    prompt = f"User request:\n{q}\n\nReturn the JSON subtask array now."
    try:
        if hasattr(llm, "ainvoke"):
            msg = await llm.ainvoke(
                [
                    {"role": "system", "content": _DECOMPOSE_SYSTEM},
                    {"role": "user", "content": prompt},
                ]
            )
            content = getattr(msg, "content", None)
            if isinstance(content, list):
                content = "".join(
                    str(part.get("text", part)) if isinstance(part, dict) else str(part)
                    for part in content
                )
            todos = parse_subtasks_json(str(content or ""))
        elif hasattr(llm, "invoke"):
            msg = llm.invoke(
                [
                    {"role": "system", "content": _DECOMPOSE_SYSTEM},
                    {"role": "user", "content": prompt},
                ]
            )
            todos = parse_subtasks_json(str(getattr(msg, "content", "") or ""))
        else:
            todos = []
        if todos:
            return todos
    except Exception:
        pass
    return fallback_subtasks(q)
