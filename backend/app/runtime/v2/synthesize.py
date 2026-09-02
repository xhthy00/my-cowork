"""User-facing final answer (v2)."""

from __future__ import annotations

import json
import re
from typing import Any

from app.agents.factory import load_prompt
from app.agents.sanitize import strip_model_junk
from app.runtime.context import (
    is_user_facing_answer,
    last_ai_text,
    looks_like_workspace_dump,
    strip_think_blocks,
)
from app.runtime.v2.office import paths_from_messages, paths_from_text

_SUMMARY_RE = re.compile(r"<summary>(.*?)</summary>", re.IGNORECASE | re.DOTALL)
_META_RE = re.compile(
    r"^\s*(subtask\s+completed|all\s+tasks?\s+completed|deliverable\s*:)",
    re.IGNORECASE,
)
_PROCESS_META_RE = re.compile(
    r"^\s*(subtask\s+completed|all\s+tasks?\s+completed|all\s+done|deliverable\s*:|"
    r"failed\s*:|finished\s+\w+_agent)\b",
    re.IGNORECASE,
)
_WRITE_TOOLS = frozenset(
    {"bash", "docx_gen", "pptx_gen", "xlsx_gen", "pdf_gen", "fs.write", "fs_write"}
)
_NOTE_TOOLS = frozenset({"read_note", "list_note", "append_note", "create_note"})
_FETCH_CLIP = 8_000
_SEARCH_CLIP = 4_000
_EVIDENCE_LIMIT = 24_000
_THIN_SUMMARY = 80


def _is_real_human(msg: Any) -> bool:
    role = str(getattr(msg, "type", None) or getattr(msg, "role", None) or "")
    if role not in {"human", "HumanMessage", "user"}:
        return False
    content = str(getattr(msg, "content", "") or "")
    return not content.startswith("[Instruction]")


def current_turn_messages(messages: list[Any] | None) -> list[Any]:
    """Keep the latest real user turn and everything after it.

    Prior turns stay in the Act-loop context, but must not be treated as this
    turn's answer, evidence, or completeness floor.
    """
    msgs = list(messages or [])
    cut = 0
    found = False
    for i, msg in enumerate(msgs):
        if _is_real_human(msg):
            cut = i
            found = True
    if not found:
        return msgs
    return msgs[cut:]


def _clip(text: str, limit: int) -> str:
    body = (text or "").strip()
    if len(body) <= limit:
        return body
    return body[:limit] + "…"


def evidence_blob(messages: list[Any], limit: int = _EVIDENCE_LIMIT) -> str:
    """Compact notes for the synthesizer — this turn only (not prior chat)."""
    messages = current_turn_messages(messages)
    fetches: list[str] = []
    searches: list[str] = []
    notes: list[str] = []
    drafts: list[str] = []
    users: list[str] = []
    files: list[str] = []
    for msg in messages or []:
        role = str(getattr(msg, "type", None) or "")
        name = str(getattr(msg, "name", "") or "")
        content = str(getattr(msg, "content", "") or "")
        if role in {"human", "HumanMessage", "user"}:
            users.append("User: " + _clip(content, 800))
            continue
        if name == "web_fetch":
            fetches.append(f"{name}: " + _clip(content, _FETCH_CLIP))
            continue
        if name == "web_search":
            searches.append(f"{name}: " + _clip(content, _SEARCH_CLIP))
            continue
        if name in _NOTE_TOOLS:
            notes.append(f"{name}: " + _clip(content, 2_000))
            continue
        if name in _WRITE_TOOLS:
            paths = paths_from_text(content)
            files.append(
                f"{name}: files: " + ", ".join(paths) if paths else f"{name}: ran"
            )
            continue
        if role in {"ai", "AIMessage", "assistant"}:
            body = strip_think_blocks(content)
            if not body or looks_like_workspace_dump(body):
                continue
            drafts.append("draft: " + _clip(body, 1_500))
    parts = [*notes, *fetches, *searches, *files, *users, *drafts]
    blob = "\n\n".join(parts)
    return blob if len(blob) <= limit else blob[-limit:]


def extract_worker_summary(text: str) -> str:
    tagged = _SUMMARY_RE.search(text or "")
    if tagged:
        return tagged.group(1).strip()
    return strip_think_blocks(text or "")


def is_process_meta(text: str) -> bool:
    """True when a worker result is English harness meta, not a user-facing summary."""
    t = strip_think_blocks(text)
    if not t:
        return True
    if _SUMMARY_RE.search(t):
        return False
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if not lines:
        return True
    if all(
        _PROCESS_META_RE.match(ln) or (ln.startswith("- ") and "/" in ln)
        for ln in lines
    ):
        return True
    if _PROCESS_META_RE.match(lines[0]) and not re.search(r"[\u4e00-\u9fff]", t):
        return True
    return False


def worker_summary_parts(subtasks: list[dict[str, Any]] | None) -> list[str]:
    """User-facing bodies from each worker result (skip process meta)."""
    parts: list[str] = []
    for st in subtasks or []:
        raw = str(st.get("result") or "")
        tagged = _SUMMARY_RE.search(raw)
        if tagged:
            body = tagged.group(1).strip()
            if body:
                parts.append(body)
            continue
        clean = strip_think_blocks(raw)
        if clean and not is_process_meta(clean):
            parts.append(clean)
    return parts


def resolve_workforce_end_summary(subtasks: list[dict[str, Any]] | None) -> str:
    """One user-facing end card. Never concatenate every worker report."""
    parts = worker_summary_parts(subtasks)
    if not parts:
        return ""
    return parts[-1]


def summary_is_thin(text: str) -> bool:
    body = extract_worker_summary(text)
    if not body or is_process_meta(body) or looks_like_workspace_dump(body):
        return True
    return len(body.strip()) < _THIN_SUMMARY


def _has_findings_or_fetch(messages: list[Any] | None) -> bool:
    for msg in messages or []:
        name = str(getattr(msg, "name", "") or "")
        if name == "web_fetch":
            return True
        if name in {"append_note", "create_note"}:
            blob = str(getattr(msg, "content", "") or "")
            if "findings" in blob.lower():
                return True
        for call in getattr(msg, "tool_calls", None) or []:
            if isinstance(call, dict):
                cname = str(call.get("name") or "")
                args = call.get("args") or {}
            else:
                cname = str(getattr(call, "name", "") or "")
                args = getattr(call, "args", None) or {}
            if cname == "web_fetch":
                return True
            if cname in {"append_note", "create_note"}:
                note = str((args or {}).get("name") or "") if isinstance(args, dict) else ""
                if note.lower() == "findings":
                    return True
    return False


def digest_from_tools(messages: list[Any]) -> str:
    """User-facing fallback from search hits and written files."""
    messages = current_turn_messages(messages)
    lines: list[str] = []
    for msg in messages or []:
        if str(getattr(msg, "name", "") or "") != "web_search":
            continue
        raw = str(getattr(msg, "content", "") or "").strip()
        rows: Any
        try:
            rows = json.loads(raw)
        except json.JSONDecodeError:
            if raw and not raw.startswith("[ERROR]"):
                lines.append(raw[:1_500])
            continue
        if not isinstance(rows, list):
            continue
        for row in rows[:6]:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "").strip()
            snippet = str(row.get("snippet") or "").strip()
            url = str(row.get("url") or "").strip()
            bit = " ".join(p for p in (title, snippet) if p).strip()
            if bit and url:
                lines.append(f"- {bit}（{url}）")
            elif bit:
                lines.append(f"- {bit}")
    paths = paths_from_messages(messages)
    parts: list[str] = []
    if lines:
        parts.append("根据检索：\n" + "\n".join(lines))
    if paths:
        parts.append("交付文件：" + "、".join(paths))
    return "\n\n".join(parts).strip()


def best_user_facing_text(messages: list[Any]) -> str:
    """Longest real chat answer in *this* user turn (skip prior-session articles)."""
    best = ""
    best_n = -1
    for msg in current_turn_messages(messages):
        role = str(getattr(msg, "type", None) or "")
        if role not in {"ai", "AIMessage", "assistant"}:
            continue
        body = strip_model_junk(extract_worker_summary(str(getattr(msg, "content", "") or "")))
        if not is_user_facing_answer(body):
            continue
        n = len(body)
        if n > best_n:
            best, best_n = body, n
    return best


def fallback_synthesize(user_text: str, messages: list[Any]) -> str:
    turn = current_turn_messages(messages)
    raw = best_user_facing_text(turn) or last_ai_text(turn)
    body = extract_worker_summary(raw)
    if looks_like_workspace_dump(body):
        body = ""
    elif body and not is_user_facing_answer(body):
        body = ""
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    if lines and all(_META_RE.match(ln) for ln in lines):
        body = ""
    return body.strip() or digest_from_tools(turn)


async def synthesize_answer(
    user_text: str,
    messages: list[Any],
    llm: Any | None = None,
    *,
    rewrite: bool = False,
) -> str:
    fallback = fallback_synthesize(user_text, messages)
    turn = current_turn_messages(messages)
    last_bad = looks_like_workspace_dump(last_ai_text(turn))
    # Pure Q&A, or a tool run that already produced a clean user-facing reply.
    if llm is None or (not rewrite and fallback and not last_bad):
        return fallback
    prompt = load_prompt(
        "synthesize",
        user_text=user_text or "",
        evidence=evidence_blob(messages),
    )
    try:
        from app.runtime.agent_stream import _emit_step_delta, astream_llm_content

        prompt_messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Write the final user-facing answer now."},
        ]
        text = await astream_llm_content(llm, prompt_messages)
        text = _SUMMARY_RE.sub(lambda m: m.group(1).strip(), text)
        last_turn = last_ai_text(turn)
        if looks_like_workspace_dump(text):
            clean = fallback or digest_from_tools(turn)
            if clean and clean != last_turn:
                _emit_step_delta("\n" + clean)
            return clean
        if text and text != last_turn and not hasattr(llm, "astream"):
            _emit_step_delta("\n" + text)
        return text or fallback
    except Exception:
        return fallback


async def compose_workforce_answer(
    user_text: str,
    *,
    subtasks: list[dict[str, Any]] | None = None,
    messages: list[Any] | None = None,
    llm: Any | None = None,
) -> str:
    """Merge worker <summary> tags; rewrite only when the composition is thin."""
    msgs = list(messages or [])
    parts = worker_summary_parts(subtasks)
    composed = resolve_workforce_end_summary(subtasks)
    # One worker: keep their <summary>. Several workers: synthesize one
    # user-facing answer (Eigent END card) instead of concatenating every role.
    if composed and not summary_is_thin(composed) and len(parts) <= 1:
        from app.runtime.agent_stream import _emit_step_delta

        _emit_step_delta(composed)
        return composed
    if llm is not None and (len(parts) > 1 or _has_findings_or_fetch(msgs)):
        return await synthesize_answer(user_text, msgs, llm, rewrite=True)
    return composed or fallback_synthesize(user_text, msgs)
