"""Pure todo normalization and progress transformations."""

from __future__ import annotations
import json
import re
from typing import Any

def _is_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def todos_match_user_language(todos: list[dict[str, Any]], user_text: str) -> bool:
    """Chinese user requests must not show English-only Progress titles."""
    if not todos:
        return True
    if not _is_chinese(user_text):
        return True
    for t in todos:
        if not _is_chinese(str(t.get("content") or "")):
            return False
        active = str(t.get("active_form") or "")
        if active and not _is_chinese(active):
            return False
    return True


def normalize_todos(raw: Any) -> list[dict[str, Any]]:
    """Normalize to Eigent serialized_todos shape; enforce one in_progress."""
    if not isinstance(raw, list):
        return []

    todos: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        active = str(item.get("active_form") or item.get("activeForm") or "").strip()
        if not active:
            active = _to_active_form(content)
        status = str(item.get("status") or "pending").strip().lower()
        if status not in ("pending", "in_progress", "completed"):
            status = "pending"
        substeps = _normalize_substeps(item.get("substeps"), f"todo_{index}")
        if status == "completed":
            _complete_open_substeps(substeps)
        todos.append(
            {
                "id": f"todo_{index}",
                "content": content,
                "active_form": active,
                "status": status,
                "substeps": substeps,
            }
        )

    if not todos:
        return []

    # Exactly one in_progress (Eigent rule); prefer first non-completed.
    in_prog = [t for t in todos if t["status"] == "in_progress"]
    if len(in_prog) == 0:
        for t in todos:
            if t["status"] != "completed":
                t["status"] = "in_progress"
                break
    elif len(in_prog) > 1:
        keep = in_prog[0]["id"]
        for t in todos:
            if t["status"] == "in_progress" and t["id"] != keep:
                t["status"] = "pending"
    return todos


def _normalize_substeps(raw: Any, parent_id: str) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        status = str(item.get("status") or "pending").strip().lower()
        if status not in {"pending", "in_progress", "completed", "failed"}:
            status = "pending"
        out.append({
            "id": f"{parent_id}_step_{len(out) + 1}",
            "content": content,
            "active_form": str(item.get("active_form") or "").strip() or _to_active_form(content),
            "status": status,
        })
    return out


def _complete_open_substeps(substeps: list[dict[str, Any]]) -> None:
    """A completed parent cannot leave planned children pending or running."""
    for substep in substeps:
        if substep.get("status") in {"pending", "in_progress"}:
            substep["status"] = "completed"


def _reconcile_substeps(
    parent_id: str,
    previous: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    *,
    allow_rewording: bool,
) -> list[dict[str, Any]]:
    if not incoming:
        return [dict(row) for row in previous]
    if len(incoming) < len(previous) and not allow_rewording:
        by_title = {str(row.get("content")): row for row in incoming}
        return [
            {**old, "status": by_title.get(str(old.get("content")), {}).get("status", old.get("status"))}
            for old in previous
        ]
    same_shape = len(previous) == len(incoming)
    used: set[str] = set()
    next_index = max(
        (int(match.group(1)) for row in previous
         if (match := re.search(r"_step_(\d+)$", str(row.get("id") or "")))),
        default=0,
    ) + 1
    out: list[dict[str, Any]] = []
    for index, child in enumerate(incoming):
        old = next((row for row in previous if row.get("content") == child.get("content")
                    and str(row.get("id")) not in used), None)
        if old is None and same_shape and index < len(previous):
            candidate = previous[index]
            if str(candidate.get("id")) not in used:
                old = candidate
        item = dict(child)
        if old is not None:
            item["id"] = str(old["id"])
            used.add(item["id"])
            if not allow_rewording:
                item["content"] = old["content"]
                item["active_form"] = old.get("active_form") or child.get("active_form")
        else:
            item["id"] = f"{parent_id}_step_{next_index}"
            next_index += 1
        out.append(item)
    return out


def reconcile_todos(
    previous: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    *,
    revision_reason: str = "",
) -> tuple[list[dict[str, Any]], bool]:
    """Keep visible step identities stable while accepting explicit plan revisions.

    A normal todo_write is a status update. Rewording the same number of rows
    without a reason must not make the progress panel jump. Added/removed rows
    are a genuine revision and retain IDs for matching existing titles.
    """
    if not previous:
        return incoming, bool(incoming)
    same_shape = len(previous) == len(incoming)
    allow_rewording = bool(revision_reason.strip())
    old_titles = [str(row.get("content") or "") for row in previous]
    new_titles = [str(row.get("content") or "") for row in incoming]
    reordered = same_shape and old_titles != new_titles and sorted(old_titles) == sorted(new_titles)
    used_ids: set[str] = set()
    next_id = max(
        (int(str(row.get("id") or "")[5:]) for row in previous
         if re.fullmatch(r"todo_\d+", str(row.get("id") or ""))),
        default=0,
    ) + 1
    result: list[dict[str, Any]] = []
    changed = bool(reordered)

    for index, row in enumerate(incoming):
        old = None
        if same_shape and not allow_rewording and not reordered:
            old = previous[index]
        else:
            old = next((p for p in previous if p.get("content") == row.get("content")
                        and str(p.get("id")) not in used_ids), None)
            if old is None and same_shape and index < len(previous) and str(previous[index].get("id")) not in used_ids:
                old = previous[index]
        item = dict(row)
        if old is not None:
            item["id"] = str(old["id"])
            used_ids.add(item["id"])
            if not allow_rewording and same_shape and not reordered:
                item["content"] = old["content"]
                item["active_form"] = old.get("active_form") or row.get("active_form")
            elif item["content"] != old["content"]:
                changed = True
            old_children = list(old.get("substeps") or [])
            new_children = list(row.get("substeps") or [])
            if not new_children:
                new_children = old_children
            children = _reconcile_substeps(
                item["id"], old_children, new_children,
                allow_rewording=allow_rewording,
            )
            if item["status"] == "completed":
                _complete_open_substeps(children)
            item["substeps"] = children
        else:
            item["id"] = f"todo_{next_id}"
            next_id += 1
            item["substeps"] = _normalize_substeps(item.get("substeps"), item["id"])
            if item["status"] == "completed":
                _complete_open_substeps(item["substeps"])
            changed = True
        result.append(item)

    if len(previous) != len(result):
        changed = True
    return result, changed


def _to_active_form(content: str) -> str:
    """Best-effort present-continuous for Chinese / English titles."""
    c = content.strip()
    if not c:
        return c
    # Chinese: prefix 正在 if not already
    if re.search(r"[\u4e00-\u9fff]", c):
        if c.startswith("正在"):
            return c
        return f"正在{c}"
    # English: naive -ing
    lower = c[0].lower() + c[1:] if c else c
    first, *rest = lower.split(" ", 1)
    if first.endswith("e") and not first.endswith("ee"):
        first = first[:-1] + "ing"
    elif not first.endswith("ing"):
        first = first + "ing"
    return (first + (" " + rest[0] if rest else "")).capitalize()


def parse_todos_json(text: str) -> list[dict[str, Any]]:
    """Extract JSON array from model output."""
    raw = (text or "").strip()
    if not raw:
        return []
    # Strip markdown fences
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()
    # Find array bounds
    start = raw.find("[")
    end = raw.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return []
    return normalize_todos(data)


def fallback_todos(text: str, *, session_mode: str = "workforce") -> list[dict[str, Any]]:
    """Minimal generic plan when LLM is unavailable — NOT a fixed domain template."""
    q = (text or "").strip()
    if not q:
        return []
    # Simple conversational → no todos (Eigent rule)
    if len(q) < 8 and not any(ch in q for ch in ("写", "生成", "做", "帮", "create", "write", "make")):
        return []
    if session_mode == "single-agent":
        steps = [
            ("Break down the user request", "Breaking down the user request"),
            ("Execute the main work", "Executing the main work"),
            ("Deliver the result", "Delivering the result"),
        ]
        if re.search(r"[\u4e00-\u9fff]", q):
            steps = [
                ("拆解用户需求", "正在拆解用户需求"),
                ("执行主要工作", "正在执行主要工作"),
                ("交付结果", "正在交付结果"),
            ]
    else:
        steps = [
            ("Assign workers", "Assigning workers"),
            ("Execute subtasks", "Executing subtasks"),
            ("Summarize results", "Summarizing results"),
        ]
        if re.search(r"[\u4e00-\u9fff]", q):
            steps = [
                ("分配合适的 Worker", "正在分配 Worker"),
                ("执行子任务", "正在执行子任务"),
                ("汇总结果", "正在汇总结果"),
            ]
    raw = [
        {
            "content": c,
            "active_form": a,
            "status": "in_progress" if i == 0 else "pending",
        }
        for i, (c, a) in enumerate(steps)
    ]
    return normalize_todos(raw)


_OFFICE_TODO_RE = re.compile(
    r"officecli|\.docx|\.pptx|\.xlsx|\bpptx\b|\bdocx\b|"
    r"生成\s*(?:word|Word)|Word\s*版|Word\s*文档|创建\s*Word|"
    r"\bword\b|"
    r"输出文档文件|调用\s*officecli",
    re.IGNORECASE,
)


def is_office_plan_text(text: str) -> bool:
    """True when a todo/subtask title is a Word/officecli step."""
    return bool(_OFFICE_TODO_RE.search(text or ""))


def without_office_todos(todos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop Word/officecli steps; empty if the whole plan was document-only."""
    kept: list[dict[str, Any]] = []
    for item in todos or []:
        blob = f"{item.get('content') or ''} {item.get('active_form') or ''}"
        if is_office_plan_text(blob):
            continue
        kept.append(item)
    return normalize_todos(kept) if kept else []


def _markdown_file_todos() -> list[dict[str, Any]]:
    return normalize_todos(
        [
            {
                "content": "整理来源内容",
                "active_form": "正在整理来源内容",
                "status": "in_progress",
            },
            {
                "content": "写入 Markdown 文件",
                "active_form": "正在写入 Markdown 文件",
                "status": "pending",
            },
            {
                "content": "核对路径并交付",
                "active_form": "正在核对路径并交付",
                "status": "pending",
            },
        ]
    )


def _drop_office_plan_if_chat(
    q: str, todos: list[dict[str, Any]], *, session_mode: str
) -> list[dict[str, Any]]:
    from app.task_support.documents import wants_document, wants_markdown_file

    if not todos:
        return todos
    md_only = wants_markdown_file(q) and not wants_document(q)
    if wants_document(q) and not md_only:
        return todos
    filtered = without_office_todos(todos)
    if len(filtered) == len(todos):
        return todos
    if md_only:
        return filtered if filtered else _markdown_file_todos()
    return fallback_todos(q, session_mode=session_mode)


# Back-compat sync entry used by tests / offline
def plan_todos(text: str, *, session_mode: str = "workforce") -> list[dict[str, Any]]:
    return fallback_todos(text, session_mode=session_mode)


def advance_todos(
    todos: list[dict[str, Any]],
    *,
    mark_completed_ids: list[str] | None = None,
    next_in_progress_id: str | None = None,
    complete_all: bool = False,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    done_ids = set(mark_completed_ids or [])
    for t in todos:
        item = dict(t)
        if complete_all or item["id"] in done_ids:
            item["status"] = "completed"
        elif next_in_progress_id and item["id"] == next_in_progress_id:
            item["status"] = "in_progress"
        elif (
            next_in_progress_id
            and item["status"] == "in_progress"
            and item["id"] != next_in_progress_id
        ):
            item["status"] = "completed"
        out.append(item)
    return normalize_todos(out) if out else out


def next_pending_id(todos: list[dict[str, Any]]) -> str | None:
    for t in todos:
        if t.get("status") == "pending":
            return str(t["id"])
    for t in todos:
        if t.get("status") == "in_progress":
            return str(t["id"])
    return None


def pick_todo_for_worker(todos: list[dict[str, Any]], worker: str) -> str | None:
    """Advance plan sequentially when workers run (no keyword domain templates)."""
    _ = worker
    return next_pending_id(todos) or next(
        (str(t["id"]) for t in todos if t.get("status") == "in_progress"),
        None,
    )


def apply_todo_write(todos_input: Any) -> list[dict[str, Any]]:
    """Eigent todo_write semantics: replace full ordered list."""
    return normalize_todos(todos_input)
