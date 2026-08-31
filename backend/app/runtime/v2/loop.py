"""Self-managed Act loop (v2) — bind_tools, execute, stream. Stops on no tool calls."""

from __future__ import annotations

import json
import re
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool

from app.agents.sanitize import (
    ensure_tool_responses,
    prepare_model_messages,
    strip_model_junk,
)
from app.runtime.agent_stream import (
    _emit_llm_progress,
    _emit_step_delta,
    _message_content_text,
    llm_heartbeat,
)
from app.runtime.context import is_user_facing_answer, looks_like_process_narration
from app.runtime.v2.office import office_bypass_refuse, paths_from_text, validate_office_file
from app.runtime.v2.critic import collect_evidence, fetch_candidates
from app.tools.mcp.manager import filter_mcp_tools, get_enabled_mcp

_DEFAULT_MAX_STEPS = 40
_MAX_RESEARCH_SEARCHES = 8
_MAX_RESEARCH_FETCHES = 8
_RESEARCH_BUDGET_NOTICE = (
    "[NOTICE] Research budget exhausted (max 8 searches / 8 page fetches). "
    "Do not call web_search, web_fetch, or other fetch tools again. "
    "Write findings notes if needed, then the <summary> and stop."
)
_OFFICE_GEN = frozenset({"docx_gen", "pptx_gen", "xlsx_gen", "pdf_gen"})
_FS_WRITE = frozenset({"fs.write", "fs_write"})
_BASH_NAMES = frozenset({"bash", "exec.bash"})
_OFFICE_SKILL_RE = re.compile(
    r"officecli|pitch-deck|word-form|official-document",
    re.IGNORECASE,
)
_FILE_REFUSE = (
    "[ERROR] The user asked for Markdown or a chat answer, not an Office file. "
    "Do not write Word/PPT/Excel/PDF or run officecli. "
    "If they asked for .md, use fs_write and stop."
)


def _tool_map(tools: list[BaseTool] | None) -> dict[str, BaseTool]:
    out: dict[str, BaseTool] = {}
    for tool in tools or []:
        name = getattr(tool, "name", None) or ""
        if name:
            out[str(name)] = tool
    return out


def _call_args(call: Any) -> dict[str, Any]:
    if isinstance(call, dict):
        args = call.get("args") or call.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {"input": args}
        return args if isinstance(args, dict) else {"input": args}
    args = getattr(call, "args", None) or {}
    return args if isinstance(args, dict) else {"input": args}


async def _invoke_tool(
    tool: BaseTool,
    args: dict[str, Any],
    *,
    name: str = "",
    call_id: str = "",
) -> str:
    tool_name = name or str(getattr(tool, "name", "") or "")
    cid = call_id or tool_name
    if tool_name:
        _emit_tool_event("tool.start", name=tool_name, call_id=cid, args=args)
    out = ""
    try:
        try:
            if hasattr(tool, "ainvoke"):
                result = await tool.ainvoke(args)
            else:
                result = tool.invoke(args)
        except Exception as exc:
            out = f"[ERROR] {type(exc).__name__}: {exc}"
            return out
        if isinstance(result, str):
            out = result
        else:
            try:
                out = json.dumps(result, ensure_ascii=False, default=str)
            except Exception:
                out = str(result)
        return out
    finally:
        if tool_name:
            _emit_tool_event(
                "tool.result", name=tool_name, call_id=cid, args=args, result=out
            )


def _tool_calls_of(msg: Any) -> list[dict[str, Any]]:
    raw = list(getattr(msg, "tool_calls", None) or [])
    if not raw:
        extra = getattr(msg, "additional_kwargs", None) or {}
        if isinstance(extra, dict):
            raw = list(extra.get("tool_calls") or [])
    out: list[dict[str, Any]] = []
    for call in raw:
        if isinstance(call, dict):
            args = call.get("args") or call.get("arguments") or {}
            out.append(
                {
                    "id": str(call.get("id") or ""),
                    "name": str(call.get("name") or ""),
                    "args": args if isinstance(args, dict) else {"input": args},
                    "type": "tool_call",
                }
            )
            continue
        args = getattr(call, "args", None) or {}
        out.append(
            {
                "id": str(getattr(call, "id", "") or ""),
                "name": str(getattr(call, "name", "") or ""),
                "args": args if isinstance(args, dict) else {"input": args},
                "type": "tool_call",
            }
        )
    return [c for c in out if c.get("name")]


def _is_file_write_call(name: str, args: dict[str, Any]) -> bool:
    """Office files only — Markdown ``fs_write`` is the default report format."""
    if name in _OFFICE_GEN:
        return True
    if name in _FS_WRITE:
        path = str(args.get("path") or "")
        return bool(re.search(r"\.(docx?|pptx?|xlsx|xls|pdf)\b", path, re.I))
    if name == "load_skill":
        skill = str(
            args.get("name") or args.get("skill") or args.get("skill_name") or ""
        )
        return bool(_OFFICE_SKILL_RE.search(skill))
    if name in _BASH_NAMES:
        cmd = str(args.get("command") or args.get("cmd") or args.get("input") or "")
        if re.search(r"\bofficecli(?:\.exe)?\b", cmd, re.I):
            return True
        if re.search(r"\.(docx|pptx|xlsx|pdf)\b", cmd, re.I) and re.search(
            r"\b(create|write|save|out|output)\b", cmd, re.I
        ):
            return True
    return False


def _should_emit_user_text(msg: AIMessage) -> bool:
    text = str(getattr(msg, "content", "") or "")
    if not text.strip():
        return False
    calls = list(getattr(msg, "tool_calls", None) or [])
    if not calls:
        return not looks_like_process_narration(text)
    return is_user_facing_answer(text)


def _tool_preview(name: str, args: dict[str, Any], limit: int = 72) -> str:
    """Short arg snippet for the live WorkLog (Eigent ACTIVATE_TOOLKIT row)."""
    raw = ""
    if name in {"bash", "exec.bash"}:
        raw = str(args.get("command") or args.get("cmd") or args.get("input") or "")
    elif name in {"fs.write", "fs.read", "fs.delete", "fs.list", "fs.mkdir"}:
        raw = str(args.get("path") or "")
    elif name == "web_search":
        raw = str(args.get("query") or "")
    elif name == "web_fetch":
        raw = str(args.get("url") or "")
    elif name == "load_skill":
        raw = str(
            args.get("name") or args.get("skill") or args.get("skill_name") or ""
        )
    else:
        for key in ("path", "query", "url", "name", "text", "command", "cmd"):
            if args.get(key):
                raw = str(args[key])
                break
    raw = " ".join(str(raw).split())
    if len(raw) > limit:
        return raw[: limit - 1] + "…"
    return raw


def _emit_tool_event(
    etype: str,
    *,
    name: str,
    call_id: str,
    args: dict[str, Any] | None = None,
    result: str | None = None,
) -> None:
    from datetime import datetime, timezone

    from app.runtime.todo_context import get_todo_runtime

    rt = get_todo_runtime()
    if rt is None or rt.bus is None or not name:
        return
    preview = _tool_preview(name, args or {})
    stamp = datetime.now(timezone.utc).isoformat()
    nested: dict[str, Any] = {
        "call_id": call_id,
        "tool": name,
        "preview": preview,
        "timestamp": stamp,
    }
    if result is not None:
        nested["result"] = result if len(result) <= 4000 else result[:4000] + "…"
    rt.bus.emit(
        {
            "task_id": rt.task_id,
            "timestamp": stamp,
            "type": etype,
            "agent_id": rt.agent_id,
            "call_id": call_id,
            "tool": name,
            "preview": preview,
            "payload": nested,
        }
    )


def _as_ai_message(acc: Any, pieces: list[str]) -> AIMessage:
    """Turn a streamed/merged chunk into a complete AIMessage.

    ``AIMessageChunk`` subclasses ``AIMessage``, so callers must not ``return last``
    from ``astream`` — that keeps only the final delta and drops tool_calls.
    """
    if type(acc) is AIMessage:
        cleaned = strip_model_junk(str(acc.content or ""))
        if cleaned != acc.content:
            return AIMessage(content=cleaned, tool_calls=list(acc.tool_calls or []))
        return acc
    streamed = "".join(pieces)
    text = ""
    if acc is not None:
        _, text = _message_content_text(acc)
    content = strip_model_junk(text or streamed)
    tool_calls = _tool_calls_of(acc) if acc is not None else []
    return AIMessage(content=content, tool_calls=tool_calls)


def _tool_call_chunk_progress(chunk: Any) -> tuple[str, int]:
    """Return ``(tool_name, arg_chars)`` from a streamed tool-call delta."""
    name = ""
    chars = 0
    pieces = getattr(chunk, "tool_call_chunks", None) or []
    for tc in pieces:
        if isinstance(tc, dict):
            n = str(tc.get("name") or "")
            args = tc.get("args") or ""
        else:
            n = str(getattr(tc, "name", None) or "")
            args = getattr(tc, "args", None) or ""
        if n:
            name = n
        if args:
            chars += len(args if isinstance(args, str) else json.dumps(args, ensure_ascii=False))
    return name, chars


async def _invoke_model(model: Any, messages: list[Any]) -> AIMessage:
    """Stream tokens to TraceBus when possible; return the final AIMessage."""
    if hasattr(model, "astream"):
        pieces: list[str] = []
        reasoning_open = False
        acc: Any = None
        tool_name = ""
        tool_chars = 0
        last_progress = 0.0
        async with llm_heartbeat():
            async for chunk in model.astream(messages):
                if acc is None:
                    acc = chunk
                else:
                    try:
                        acc = acc + chunk
                    except TypeError:
                        acc = chunk
                reasoning, text = _message_content_text(chunk)
                if reasoning:
                    if not reasoning_open:
                        _emit_step_delta("<think>")
                        reasoning_open = True
                    _emit_step_delta(reasoning)
                if text:
                    if reasoning_open:
                        _emit_step_delta("</think>\n")
                        reasoning_open = False
                    pieces.append(text)
                    _emit_step_delta(text)
                name, extra = _tool_call_chunk_progress(chunk)
                if name:
                    tool_name = name
                if extra:
                    tool_chars += extra
                    now = time.monotonic()
                    if now - last_progress >= 0.4:
                        last_progress = now
                        _emit_llm_progress(tool=tool_name or "tool", chars=tool_chars)
        if tool_chars and time.monotonic() - last_progress >= 0.05:
            _emit_llm_progress(tool=tool_name or "tool", chars=tool_chars)
        if reasoning_open:
            _emit_step_delta("</think>\n")
        return _as_ai_message(acc, pieces)

    result = await model.ainvoke(messages)
    if isinstance(result, AIMessage):
        cleaned = strip_model_junk(str(result.content or ""))
        if cleaned != result.content:
            result = AIMessage(
                content=cleaned, tool_calls=list(result.tool_calls or [])
            )
        reasoning, text = _message_content_text(result)
        if reasoning:
            _emit_step_delta("<think>")
            _emit_step_delta(reasoning)
            _emit_step_delta("</think>\n")
        if text and _should_emit_user_text(result):
            _emit_step_delta(text)
        return result
    text = strip_model_junk(str(getattr(result, "content", None) or result))
    out = AIMessage(content=text)
    if _should_emit_user_text(out):
        _emit_step_delta(text)
    return out


async def inject_forced_search(
    tools: list[BaseTool] | None,
    user_text: str,
    messages: list[Any],
) -> list[Any]:
    """Run two distinct ``web_search`` queries when the model only announced intent."""
    tool = _tool_map(tools).get("web_search")
    if tool is None:
        return list(messages)
    q1 = (user_text or "").strip()[:300]
    q2 = (q1[:280] + " 细则 生效 例外").strip()
    if q2 == q1:
        q2 = (q1 + " official details").strip()
    inv = collect_evidence(messages)
    existing = {" ".join(q.split()).casefold() for q in inv.search_queries}
    planned = [q for q in (q1, q2) if q and " ".join(q.split()).casefold() not in existing]
    if not planned:
        planned = [q2] if q2 else []
    if not planned:
        return list(messages)
    out = list(messages)
    for i, query in enumerate(planned[:2]):
        cid = f"call_forced_web_search_{len(out)}_{i}"
        content = await _invoke_tool(
            tool, {"query": query, "count": 8}, name="web_search", call_id=cid
        )
        out.append(
            AIMessage(
                content=" ",
                tool_calls=[
                    {
                        "id": cid,
                        "name": "web_search",
                        "args": {"query": query, "count": 8},
                        "type": "tool_call",
                    }
                ],
            )
        )
        out.append(ToolMessage(content=str(content), tool_call_id=cid, name="web_search"))
    out.append(
        HumanMessage(
            content=(
                "[Instruction]\n"
                "web_search results are in the previous tool messages. "
                "Next: web_fetch the 2-3 most relevant http(s) URLs from those "
                "results. Do not write the final answer from snippets alone. "
                "Do not announce another search without calling the tool."
            )
        )
    )
    return out


async def inject_forced_fetch(
    tools: list[BaseTool] | None,
    messages: list[Any],
    *,
    limit: int = 3,
) -> list[Any]:
    """Fetch top search URLs when the model searched but never opened pages."""
    tool = _tool_map(tools).get("web_fetch")
    if tool is None:
        return list(messages)
    urls = fetch_candidates(messages, limit=limit)
    if not urls:
        return list(messages)
    out = list(messages)
    for i, url in enumerate(urls):
        cid = f"call_forced_web_fetch_{len(out)}_{i}"
        content = await _invoke_tool(
            tool, {"url": url}, name="web_fetch", call_id=cid
        )
        out.append(
            AIMessage(
                content=" ",
                tool_calls=[
                    {
                        "id": cid,
                        "name": "web_fetch",
                        "args": {"url": url},
                        "type": "tool_call",
                    }
                ],
            )
        )
        out.append(ToolMessage(content=str(content), tool_call_id=cid, name="web_fetch"))
    out.append(
        HumanMessage(
            content=(
                "[Instruction]\n"
                "web_fetch page text is in the previous tool messages. "
                "Write the complete user-facing answer from those pages. "
                "Cite only URLs that appear in the fetch results."
            )
        )
    )
    return out


def _completed_research_counts(messages: list[Any]) -> tuple[int, int]:
    """Count finished search/fetch tool messages (ignore the in-flight AI call)."""
    searches = 0
    fetches = 0
    for msg in messages or []:
        role = str(getattr(msg, "type", None) or "")
        name = str(getattr(msg, "name", "") or "").lower()
        if role not in {"tool", "ToolMessage"}:
            continue
        if name == "web_search":
            searches += 1
        elif "fetch" in name:
            fetches += 1
    return searches, fetches


async def run_act_loop(
    model: Any,
    tools: list[BaseTool] | None,
    messages: list[Any],
    *,
    max_steps: int = _DEFAULT_MAX_STEPS,
    deadline_s: float | None = None,
    cancel_event: Any = None,
    allow_file_writes: bool = True,
) -> list[Any]:
    """Run model ↔ tools until the model stops calling tools (ChatAgent-style)."""
    tools = filter_mcp_tools(list(tools or []), get_enabled_mcp())
    mapping = _tool_map(tools)
    bound = model.bind_tools(tools) if tools and hasattr(model, "bind_tools") else model
    working = list(messages)
    started = time.monotonic()
    steps = 0

    def _cancelled() -> bool:
        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            return True
        if deadline_s is not None and (time.monotonic() - started) >= deadline_s:
            return True
        return False

    while steps < max_steps:
        if _cancelled():
            break
        steps += 1
        payload = prepare_model_messages(ensure_tool_responses(working))
        ai = await _invoke_model(bound, payload)
        working.append(ai)
        calls = list(getattr(ai, "tool_calls", None) or [])
        if not calls:
            break
        if not allow_file_writes:
            only_files = all(
                _is_file_write_call(
                    str(c.get("name") if isinstance(c, dict) else getattr(c, "name", "") or ""),
                    _call_args(c),
                )
                for c in calls
            )
            if only_files and is_user_facing_answer(str(ai.content or "")):
                working[-1] = AIMessage(content=str(ai.content or ""))
                break
        for call in calls:
            if _cancelled():
                break
            name = str(call.get("name") if isinstance(call, dict) else getattr(call, "name", "") or "")
            cid = str(call.get("id") if isinstance(call, dict) else getattr(call, "id", "") or "")
            args = _call_args(call)
            if not allow_file_writes and _is_file_write_call(name, args):
                working.append(
                    ToolMessage(content=_FILE_REFUSE, tool_call_id=cid or name, name=name)
                )
                continue
            from app.runtime.v2.office_gate import OFFICE_WRITE_REFUSE, office_writes_blocked

            if office_writes_blocked() and _is_file_write_call(name, args):
                working.append(
                    ToolMessage(
                        content=OFFICE_WRITE_REFUSE, tool_call_id=cid or name, name=name
                    )
                )
                continue
            searches, fetches = _completed_research_counts(working)
            over_search = name == "web_search" and searches >= _MAX_RESEARCH_SEARCHES
            over_fetch = "fetch" in name.lower() and fetches >= _MAX_RESEARCH_FETCHES
            if over_search or over_fetch:
                working.append(
                    ToolMessage(
                        content=_RESEARCH_BUDGET_NOTICE,
                        tool_call_id=cid or name,
                        name=name,
                    )
                )
                continue
            if name in _BASH_NAMES:
                cmd = str(args.get("command") or args.get("cmd") or args.get("input") or "")
                refused = office_bypass_refuse(cmd)
                if refused:
                    working.append(
                        ToolMessage(content=refused, tool_call_id=cid or name, name=name)
                    )
                    continue
            tool = mapping.get(name)
            if tool is None:
                content = f"[ERROR] Unknown tool {name!r}."
            else:
                content = await _invoke_tool(
                    tool, args, name=name, call_id=cid or name
                )
            if name in {"docx_gen", "pptx_gen", "xlsx_gen", "pdf_gen", "fs.write", "bash"}:
                notes: list[str] = []
                for path in paths_from_text(str(content)):
                    ok, msg = validate_office_file(path)
                    if not ok:
                        notes.append(f"[VALIDATE FAIL] {path}: {msg}")
                if notes:
                    content = str(content) + "\n" + "\n".join(notes)
            if name == "load_skill" and content and not str(content).startswith("[ERROR]"):
                content = (
                    "[Instruction] Follow the skill markdown below as the plan. "
                    "Do not recap the skill; continue the user task.\n\n"
                    + str(content)
                )
            working.append(
                ToolMessage(content=content, tool_call_id=cid or name, name=name)
            )
    return working
