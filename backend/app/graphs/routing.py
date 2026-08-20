"""Workforce routing: dependency-ready fan-out and document helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from langgraph.types import Send

from app.agents.workers import WORKER_IDS

MAX_ROUNDS = 16
MAX_RETRIES = 3

_DOC_TOOL_NAMES = frozenset(
    {
        "pptx_gen",
        "docx_gen",
        "xlsx_gen",
        "pdf_gen",
        "pptx.gen",
        "docx.gen",
        "xlsx.gen",
        "pdf.gen",
        "fs.write",
    }
)
_BASH_TOOL_NAMES = frozenset({"bash", "exec.bash"})
_OFFICECLI_WRITE_RE = re.compile(
    r"\bofficecli(?:\.exe)?\s+(create|add|set|batch|save|close|remove|move|swap)\b",
    re.IGNORECASE,
)
_OFFICE_EXTS = (".pptx", ".ppt", ".docx", ".doc", ".xlsx", ".xls", ".pdf")
_PPTX_EXTS = (".pptx", ".ppt")
_RESULT_FAIL_MARKERS = (
    "rejected",
    "operation rejected",
    "error",
    "failed",
    "traceback",
    "参数无效",
    "生成失败",
)

# Generation intent only — mentioning 文档/docx as an input (解读/附件) must NOT match.
# Keep 函 out of nouns (matches 函数). Prefer 公函/函件.
_DOC_VERB = (
    r"(?:重新生成|再生成|重新写|重新做|再写一份|再出一份|再做一份|"
    r"生成|创建|撰写|起草|写出|导出|输出|制作|"
    r"做一份|做成|出一份|写一份|帮我做|帮我写)"
)
_DOC_NOUN = (
    r"(?:pptx?|docx?|xlsx|xls|pdf|excel|幻灯片|演示文稿|"
    r"公文|公函|函件|"
    r"请示|通知|纪要|通报|决定|决议|公告|通告|批复|议案|"
    r"估算表|明细表|预算表|测算表|台账|估算)"
)
_DOC_GEN_RE = re.compile(
    _DOC_VERB
    + r".{0,32}"
    + _DOC_NOUN
    + r"|"
    + _DOC_NOUN
    + r".{0,16}"
    + r"(?:重新生成|再生成|生成|创建|撰写|起草|导出|输出|制作)",
    re.IGNORECASE,
)
_DOC_SKILL_RE = re.compile(
    r"(?:#\s*)?official-document-writing",
    re.IGNORECASE,
)
_GEN_HINTS = ("生成", "撰写", "起草", "写一份", "做一份", "制作", "导出", "写出")


def _msg_role(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("type") or msg.get("role") or "")
    return str(getattr(msg, "type", None) or getattr(msg, "role", None) or "")


def _msg_content(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("content") or "")
    return str(getattr(msg, "content", None) or "")


def _msg_name(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("name") or "")
    return str(getattr(msg, "name", None) or "")


def _latest_user_text(state: dict[str, Any]) -> str:
    messages = state.get("messages") or []
    for msg in reversed(messages):
        role = _msg_role(msg)
        content = _msg_content(msg)
        if role in ("human", "user") and content:
            return content
    for msg in messages:
        content = _msg_content(msg)
        if content:
            return content
    return str(state.get("user_text") or "")


_MD_FILE_RE = re.compile(
    r"(?:markdown|\.md\b|md\s*文档|md文档|md\s*文件|"
    r"markdown\s*(?:文档|文件)|生成\s*md|写成?\s*md|输出\s*md|"
    r"帮我生成md)",
    re.IGNORECASE,
)
_OFFICE_FORMAT_RE = re.compile(
    r"\b(?:docx?|xlsx|pptx?|pdf|word)\b|word\s*版|word\s*文档|excel|"
    r"幻灯片|演示文稿|公文|请示|\.docx\b|\.pptx\b|\.xlsx\b",
    re.IGNORECASE,
)


def wants_markdown_file(user_text: str) -> bool:
    """True when the user asked for Markdown / .md, not Word."""
    q = (user_text or "").strip()
    return bool(q and _MD_FILE_RE.search(q))


_UNSPECIFIED_DOC_RE = re.compile(
    _DOC_VERB
    + r".{0,32}"
    + r"(?:报告|文档|方案|白皮书|论文|paper|report)"
    + r"|"
    + r"(?:报告|文档|方案|白皮书|论文|paper|report)"
    + r".{0,16}"
    + r"(?:重新生成|再生成|生成|创建|撰写|起草|导出|输出|制作)",
    re.IGNORECASE,
)


def wants_unspecified_document(user_text: str) -> bool:
    """Eigent Document Agent: document/report/paper with no format → HTML file."""
    q = (user_text or "").strip()
    if not q or wants_markdown_file(q) or wants_document(q):
        return False
    return bool(_UNSPECIFIED_DOC_RE.search(q))


def wants_file_document(user_text: str) -> bool:
    """Any file artifact: office, markdown, or unspecified HTML report."""
    return (
        wants_document(user_text)
        or wants_markdown_file(user_text)
        or wants_unspecified_document(user_text)
    )


def wants_document(user_text: str) -> bool:
    """True when the user asked to *generate* an office document (not merely mention one)."""
    q = (user_text or "").strip()
    if not q:
        return False
    if wants_markdown_file(q) and not _OFFICE_FORMAT_RE.search(q):
        return False
    if _DOC_GEN_RE.search(q):
        return True
    if _DOC_SKILL_RE.search(q) and any(v in q for v in _GEN_HINTS):
        return True
    if _OFFICE_FORMAT_RE.search(q) and any(v in q for v in _GEN_HINTS):
        return True
    if re.search(r"word\s*版", q, re.IGNORECASE):
        return True
    return any(
        k in q
        for k in (
            "做成 ppt",
            "做成ppt",
            "做一份 ppt",
            "出一份 ppt",
            "做PPT",
            "做 ppt",
            "生成图文",
        )
    )


def wants_pptx(user_text: str) -> bool:
    q = (user_text or "").strip()
    if not q:
        return False
    ql = q.lower()
    return any(k in ql for k in ("pptx", "ppt", "幻灯片", "演示文稿")) or "做ppt" in ql.replace(
        " ", ""
    )


def _iter_tool_calls(msg: Any) -> list[dict[str, Any]]:
    raw = getattr(msg, "tool_calls", None)
    if not raw and isinstance(msg, dict):
        raw = msg.get("tool_calls")
    if not raw:
        additional = getattr(msg, "additional_kwargs", None) or {}
        if isinstance(additional, dict):
            raw = additional.get("tool_calls")
    if not raw:
        return []
    out: list[dict[str, Any]] = []
    for call in raw:
        if isinstance(call, dict):
            name = str(call.get("name") or "")
            args = call.get("args") or call.get("arguments") or {}
            fn = call.get("function")
            if not name and isinstance(fn, dict):
                name = str(fn.get("name") or "")
                args = fn.get("arguments") or args
            out.append(
                {
                    "id": str(call.get("id") or ""),
                    "name": name,
                    "args": args,
                }
            )
            continue
        out.append(
            {
                "id": str(getattr(call, "id", "") or ""),
                "name": str(getattr(call, "name", "") or ""),
                "args": getattr(call, "args", {}) or {},
            }
        )
    return out


def _args_blob(args: Any) -> str:
    if isinstance(args, dict):
        return " ".join(
            str(args.get(key) or "")
            for key in ("cmd", "command", "path", "out_path", "name")
        )
    return str(args or "")


def _msg_tool_call_id(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("tool_call_id") or "")
    return str(getattr(msg, "tool_call_id", None) or "")


def _result_failed(content: str) -> bool:
    low = content.lower()
    # JSON `"error": null` is a successful officecli payload, not a failure.
    stripped = re.sub(r'"error"\s*:\s*(null|"")', " ", low)
    return any(marker in stripped for marker in _RESULT_FAIL_MARKERS)


def _has_office_ext(text: str, *, require_pptx: bool = False) -> bool:
    low = (text or "").lower()
    exts = _PPTX_EXTS if require_pptx else _OFFICE_EXTS
    return any(ext in low for ext in exts)


def has_office_deliverable(
    paths: Iterable[str] | None,
    *,
    require_pptx: bool = False,
) -> bool:
    """True when *paths* includes a newly written office file."""
    if not paths:
        return False
    for path in paths:
        low = str(path).lower()
        if require_pptx:
            if low.endswith(_PPTX_EXTS):
                return True
        elif low.endswith(_OFFICE_EXTS):
            return True
    return False


def document_tools_succeeded(state: dict[str, Any], *, require_pptx: bool = False) -> bool:
    """True when this run actually wrote an office file (not merely load_skill)."""
    messages = list(state.get("messages") or [])
    cmd_by_id: dict[str, str] = {}
    for msg in messages:
        for call in _iter_tool_calls(msg):
            cid = call.get("id") or ""
            if cid:
                cmd_by_id[str(cid)] = _args_blob(call.get("args"))

    allowed = (
        frozenset({"pptx_gen", "pptx.gen"})
        if require_pptx
        else _DOC_TOOL_NAMES
    )
    for msg in messages:
        name = _msg_name(msg)
        role = _msg_role(msg)
        content = _msg_content(msg).strip()
        if not content:
            continue
        is_tool = role in ("tool", "ToolMessage") or bool(_msg_tool_call_id(msg))
        cmd = cmd_by_id.get(_msg_tool_call_id(msg), "")
        is_write_tool = name in allowed
        is_officecli_bash = name in _BASH_TOOL_NAMES and (
            "officecli" in cmd.lower() or "officecli" in content.lower()
        )
        if not is_write_tool and not (is_tool and is_officecli_bash):
            continue
        if _result_failed(content):
            continue
        if require_pptx and content.lower().rstrip().endswith(".pdf"):
            continue
        if is_officecli_bash and (
            not _OFFICECLI_WRITE_RE.search(cmd)
            or not _has_office_ext(cmd, require_pptx=require_pptx)
        ):
            continue
        if name == "fs.write" and not _has_office_ext(content, require_pptx=require_pptx):
            continue
        return True
    return False


_CLAIMED_OFFICE_RE = re.compile(
    r"(?:^|[\s`'\"=:：(\[])"
    r"(?P<path>(?:~|/|[A-Za-z]:\\)[^\s`*'\"<>|\]]+?\.(?:docx?|pptx?|xlsx|xls|pdf))",
    re.IGNORECASE | re.MULTILINE,
)


def _is_plausible_office_fs_path(raw: str) -> bool:
    """Reject URL remnants such as ``https://www.doc`` → ``//www.doc``."""
    p = (raw or "").strip()
    if not p:
        return False
    lower = p.lower()
    if lower.startswith(("http://", "https://", "ftp://")):
        return False
    unix = p.replace("\\", "/")
    if unix.startswith("//"):
        return False
    name = unix.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0].lower()
    if stem in {"www", "http", "https"} or stem.startswith("www."):
        return False
    return True


def extract_claimed_office_paths(text: str) -> list[str]:
    """Absolute office paths the model listed in a user-facing reply."""
    out: list[str] = []
    seen: set[str] = set()
    for match in _CLAIMED_OFFICE_RE.finditer(text or ""):
        raw = match.group("path").rstrip(".,;:)")
        if not raw or raw in seen or not _is_plausible_office_fs_path(raw):
            continue
        seen.add(raw)
        out.append(raw)
    return out


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
