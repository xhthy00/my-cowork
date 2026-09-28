"""Workforce dependency-ready fan-out and compatibility document helpers."""

from __future__ import annotations
from typing import Any
from langgraph.types import Send
from app.agents.workers import WORKER_IDS
from app.task_support.documents import (
    _msg_role,
    _msg_content,
    _msg_name,
    _latest_user_text,
    _asks_office_too,
    _intent_text,
    wants_markdown_file,
    wants_web_app,
    wants_html_file,
    wants_unspecified_document,
    wants_file_document,
    wants_document,
    markdown_only,
    wants_pptx,
    _iter_tool_calls,
    _args_blob,
    _msg_tool_call_id,
    _result_failed,
    _has_office_ext,
    has_office_deliverable,
    document_tools_succeeded,
    _is_plausible_office_fs_path,
    extract_claimed_office_paths,
)

MAX_ROUNDS = 16
MAX_RETRIES = 3

def ready_subtasks(subtasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return waiting tasks whose dependencies are all completed."""
    by_id = {str(t.get("id")): t for t in subtasks}
    ready: list[dict[str, Any]] = []
    for t in subtasks:
        if str(t.get("status") or "") != "waiting":
            continue
        deps = t.get("dependencies") or []
        ok = True
        for dep in deps:
            other = by_id.get(str(dep))
            if other is None or str(other.get("status")) != "completed":
                ok = False
                break
        if ok:
            ready.append(t)
    return ready


def all_terminal(subtasks: list[dict[str, Any]]) -> bool:
    if not subtasks:
        return True
    return all(str(t.get("status")) in {"completed", "failed"} for t in subtasks)


def apply_retry_or_fail(subtasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reset failed tasks under retry budget to waiting; leave others."""
    out: list[dict[str, Any]] = []
    for t in subtasks:
        item = dict(t)
        if str(item.get("status")) == "failed":
            retries = int(item.get("retries") or 0)
            if retries < MAX_RETRIES:
                item["retries"] = retries + 1
                item["status"] = "waiting"
                item["result"] = ""
        out.append(item)
    return out


def route_after_coordinator(state: dict[str, Any]) -> Any:
    """END, or list of Send to worker nodes for ready subtasks."""
    round_n = int(state.get("round") or 0)
    if round_n >= MAX_ROUNDS:
        return "END"

    subtasks = list(state.get("subtasks") or [])
    if not subtasks:
        return "END"

    if all_terminal(subtasks):
        return "END"

    ready = ready_subtasks(subtasks)
    if not ready:
        return "END"

    sends: list[Send] = []
    for t in ready:
        assignee = str(t.get("assignee") or "")
        if assignee not in WORKER_IDS:
            assignee = "browser_agent"
        sends.append(
            Send(
                assignee,
                {
                    **state,
                    "subtasks": subtasks,
                    "assigned_task_id": str(t["id"]),
                },
            )
        )
    return sends if sends else "END"


# --- Legacy helpers kept for tests that still import them during migration ---

FINISH_TOKENS = {"FINISH", "finish", "end", "END", ""}


def parse_workers(content: str) -> list[str]:
    """Parse legacy supervisor tokens into worker names (normalized)."""
    from app.agents.workers import LEGACY_WORKER_MAP, normalize_worker_id

    text = (content or "").strip().strip("`\"'")
    if text in FINISH_TOKENS:
        return []
    upper = text.upper()
    if upper.startswith("PARALLEL:"):
        body = text.split(":", 1)[1]
        names: list[str] = []
        for part in body.split(","):
            name = normalize_worker_id(part.strip())
            if name and name not in names:
                names.append(name)
        return names
    one = normalize_worker_id(text)
    if one:
        return [one]
    lower = text.lower()
    for legacy, modern in LEGACY_WORKER_MAP.items():
        if legacy in lower or modern in lower:
            return [modern]
    if any(tok in lower for tok in ("finish", "done", "complete", "结束")):
        return []
    return []


def parse_next_worker(content: str) -> str | None:
    workers = parse_workers(content)
    if not workers:
        return None
    if len(workers) == 1:
        return workers[0]
    return "PARALLEL:" + ",".join(workers)


def needs_forced_delegation(user_text: str) -> bool:
    q = (user_text or "").strip()
    if not q:
        return False
    if q.lower() in {"hello", "hi", "hey", "你好", "您好", "在吗", "谢谢"}:
        return False
    markers = (
        "帮", "生成", "写", "做", "攻略", "报告", "文档", "搜索", "检索", "调研",
        "备案", "旅游", "ppt", "docx", "pdf", "create", "write", "generate",
        "research", "travel", "document",
    )
    ql = q.lower()
    if any(m in ql for m in markers) or any(m in q for m in ("帮", "生成", "写", "做")):
        return True
    return len(q) >= 20


def infer_default_worker(user_text: str) -> str:
    q = user_text or ""
    ql = q.lower()
    if wants_web_app(q):
        return "developer_agent"
    if wants_file_document(q):
        return "document_agent"
    if any(k in q for k in ("飞书", "lark", "slack", "消息", "通知")):
        return "document_agent"
    if any(k in q for k in ("旅游", "攻略", "搜索", "检索", "调研", "政策", "备案", "天气")):
        return "browser_agent"
    if any(k in ql for k in ("文件", "桌面", "bash", "脚本", "读写", "write a file", "write")):
        return "developer_agent"
    if any(k in q for k in ("生成", "写", "帮我", "做一份", "出一份")):
        return "document_agent"
    return "browser_agent"


def route_after_supervisor(state: dict[str, Any]) -> Any:
    """Deprecated: prefer route_after_coordinator. Kept for old tests."""
    round_n = int(state.get("round") or 0)
    if round_n >= MAX_ROUNDS:
        return "END"
    raw = str(state.get("next_worker") or "")
    workers = parse_workers(raw)
    user_text = ""
    for msg in reversed(state.get("messages") or []):
        if _msg_role(msg) in ("human", "user") and _msg_content(msg):
            user_text = _msg_content(msg)
            break
    if not workers and round_n <= 1 and needs_forced_delegation(user_text):
        workers = [infer_default_worker(user_text)]
    need_pptx = wants_pptx(user_text)
    if not workers and wants_document(user_text) and not document_tools_succeeded(
        state, require_pptx=need_pptx
    ):
        if round_n < MAX_ROUNDS:
            workers = ["document_agent"]
    if not workers:
        return "END"
    if len(workers) == 1:
        return workers[0]
    return [Send(name, {**state, "assigned_task_id": None}) for name in workers]
