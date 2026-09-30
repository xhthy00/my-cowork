"""Defensive message sanitization for tool-calling model round-trips.

Some providers (e.g. DeepSeek) occasionally emit a tool call whose
``arguments`` JSON cannot be parsed. LangChain stores those as
``invalid_tool_calls`` on the ``AIMessage`` instead of ``tool_calls``, so the
tool is never executed and no ``ToolMessage`` is produced for its id.

``langchain_openai`` still serializes ``invalid_tool_calls`` back into the
assistant message's ``tool_calls`` array on the next request, and OpenAI then
rejects the request with ``400 invalid_request_error`` — "an assistant message
with 'tool_calls' must be followed by tool messages responding to each
'tool_call_id'" — because the id has no matching tool message.

This module injects synthetic error ``ToolMessage`` responses for every
unanswered tool call id (valid or invalid) right before the messages reach the
model, so the round-trip always satisfies the API invariant and the model can
see why the call failed and retry with corrected arguments.
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage

_INVALID_CALL_TEMPLATE = (
    "Invalid tool call: arguments could not be parsed ({args!r}; error: {error}). "
    "Fix the arguments and call the tool again."
)

_MISSING_RESULT_TEMPLATE = (
    "(tool call was not executed — no result available; please retry or continue.)"
)

# MiniMax sometimes leaks decoder tokens into the chat body:
#   ]<|minimax|>[0xf
#   ] <|minimax|> [0xX
_MODEL_JUNK_SPAN_RE = re.compile(
    r"\]?\s*<\|minimax\|>\s*\[0x[0-9A-Fa-fXx]*"
    r"|<\|minimax\|>"
)
_MODEL_JUNK_LINE_RE = re.compile(
    r"^\s*\]?\s*<\|minimax\|>\s*(?:\[0x[0-9A-Fa-fXx]*)?\s*$"
)


def strip_model_junk(text: str) -> str:
    """Drop MiniMax special-token leakage so it never reaches the chat bubble."""
    if not text:
        return text
    kept: list[str] = []
    for ln in text.splitlines(keepends=True):
        body = ln.rstrip("\r\n")
        ending = ln[len(body) :]
        if _MODEL_JUNK_LINE_RE.match(body):
            continue
        cleaned = _MODEL_JUNK_SPAN_RE.sub("", body)
        if cleaned.strip() or (cleaned and ending):
            kept.append(cleaned + ending)
    return "".join(kept)


def _is_assistant(message: Any) -> bool:
    if isinstance(message, AIMessage):
        return True
    if isinstance(message, dict):
        role = str(message.get("role") or message.get("type") or "").lower()
        return role in {"assistant", "ai"}
    return False


def _is_tool(message: Any) -> bool:
    if isinstance(message, ToolMessage):
        return True
    if isinstance(message, dict):
        role = str(message.get("role") or message.get("type") or "").lower()
        return role == "tool"
    return False


def _tool_response_id(message: Any) -> str | None:
    if isinstance(message, ToolMessage):
        return message.tool_call_id
    if isinstance(message, dict):
        return message.get("tool_call_id") or message.get("id") or None
    return None


def _assistant_calls(message: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return ``(tool_calls, invalid_tool_calls)`` for an assistant message."""
    if isinstance(message, AIMessage):
        return (
            [dict(c) for c in (getattr(message, "tool_calls", None) or [])],
            [dict(c) for c in (getattr(message, "invalid_tool_calls", None) or [])],
        )
    if isinstance(message, dict):
        calls = [dict(c) for c in (message.get("tool_calls") or []) if isinstance(c, dict)]
        return calls, []
    return [], []


def _fill_missing_ids(
    message: Any,
    calls: list[dict[str, Any]],
    invalid: list[dict[str, Any]],
    index: int,
) -> Any:
    """Return *message* with generated ids for tool calls that lack one.

    Providers reject tool calls without an id, and we cannot attach a
    ``ToolMessage`` to an id-less call.  Patching a copy keeps the round-trip
    valid without mutating caller-owned state.
    """
    touched = False
    for tag, bucket in (("c", calls), ("i", invalid)):
        for k, call in enumerate(bucket):
            if not str(call.get("id") or "").strip():
                call["id"] = f"call_repaired_{index}_{tag}{k}"
                touched = True
    if not touched:
        return message
    if isinstance(message, AIMessage):
        update: dict[str, Any] = {"tool_calls": calls}
        if invalid:
            update["invalid_tool_calls"] = invalid
        return message.model_copy(update=update)
    if isinstance(message, dict):
        patched = dict(message)
        patched["tool_calls"] = calls
        return patched
    return message


def ensure_tool_responses(messages: list[AnyMessage]) -> list[AnyMessage]:
    """Return *messages* with synthetic tool responses for unanswered calls.

    Every assistant message that declares ``tool_calls`` / ``invalid_tool_calls``
    must be followed (eventually) by a ``ToolMessage`` for each call id, or the
    OpenAI-compatible API rejects the request.  This helper inserts error
    ``ToolMessage`` objects for any id that has no response in the following
    messages, covering malformed ``invalid_tool_calls``, interrupted checkpoints,
    truncated histories, dict-form (serialized) messages and id-less tool calls
    alike.
    """
    out: list[AnyMessage] = []
    n = len(messages)
    i = 0
    while i < n:
        message = messages[i]
        if not _is_assistant(message):
            out.append(message)
            i += 1
            continue

        calls, invalid = _assistant_calls(message)
        if not calls and not invalid:
            out.append(message)
            i += 1
            continue

        message = _fill_missing_ids(message, calls, invalid, i)
        out.append(message)

        answered: set[str] = set()
        j = i + 1
        while j < n and not _is_assistant(messages[j]):
            if _is_tool(messages[j]):
                rid = _tool_response_id(messages[j])
                if rid:
                    answered.add(rid)
            j += 1

        for call in calls:
            call_id = call.get("id")
            if call_id and call_id not in answered:
                out.append(
                    ToolMessage(
                        content=_MISSING_RESULT_TEMPLATE,
                        tool_call_id=call_id,
                        name=call.get("name") or "",
                    )
                )
        for call in invalid:
            call_id = call.get("id")
            if call_id and call_id not in answered:
                out.append(
                    ToolMessage(
                        content=_INVALID_CALL_TEMPLATE.format(
                            args=call.get("args") or "",
                            error=call.get("error") or "malformed arguments",
                        ),
                        tool_call_id=call_id,
                        name=call.get("name") or "",
                    )
                )
        i += 1
    return out


def _is_system(message: Any) -> bool:
    if isinstance(message, SystemMessage):
        return True
    if isinstance(message, dict):
        role = str(message.get("role") or message.get("type") or "").lower()
        return role in {"system", "systemmessage"}
    role = str(getattr(message, "type", None) or getattr(message, "role", None) or "")
    return role in {"system", "SystemMessage"}


def _content_str(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("content") or "")
    return str(getattr(message, "content", "") or "")


def prepare_model_messages(messages: list[AnyMessage]) -> list[AnyMessage]:
    """Make the thread acceptable to strict OpenAI-compat APIs (MiniMax 2013).

    MiniMax rejects empty assistant ``content`` on tool-call turns, ``system``
    after a tool result, and consecutive leading ``system`` blocks.
    """
    if not messages:
        return []
    lead: list[str] = []
    rest_start = 0
    for i, msg in enumerate(messages):
        if not _is_system(msg):
            rest_start = i
            break
        text = _content_str(msg).strip()
        if text:
            lead.append(text)
        rest_start = i + 1
    out: list[AnyMessage] = []
    if lead:
        out.append(SystemMessage(content="\n\n".join(lead)))
    for msg in messages[rest_start:]:
        if _is_system(msg):
            text = _content_str(msg).strip()
            if text:
                out.append(HumanMessage(content="[Instruction]\n" + text))
            continue
        if isinstance(msg, AIMessage):
            content = msg.content
            empty = content is None or content == ""
            has_calls = bool(getattr(msg, "tool_calls", None) or [])
            if empty:
                msg = msg.model_copy(update={"content": " " if has_calls else "(continue)"})
        out.append(msg)
    return _fold_instructions_into_tools(out)


def _is_instruction_human(message: Any) -> bool:
    if isinstance(message, HumanMessage):
        pass
    elif isinstance(message, dict):
        role = str(message.get("role") or message.get("type") or "").lower()
        if role not in {"human", "user"}:
            return False
    else:
        role = str(getattr(message, "type", None) or getattr(message, "role", None) or "")
        if role not in {"human", "user", "HumanMessage"}:
            return False
    return _content_str(message).lstrip().startswith("[Instruction]")


def _merge_into_tool(tool_msg: Any, extra: str) -> Any:
    blob = (str(_content_str(tool_msg)).rstrip() + "\n\n" + extra.strip()).strip()
    if isinstance(tool_msg, ToolMessage):
        return ToolMessage(
            content=blob,
            tool_call_id=tool_msg.tool_call_id,
            name=tool_msg.name or "",
        )
    if isinstance(tool_msg, dict):
        patched = dict(tool_msg)
        patched["content"] = blob
        return patched
    return tool_msg


def _fold_instructions_into_tools(messages: list[AnyMessage]) -> list[AnyMessage]:
    """Keep tool results contiguous after assistant tool_calls (MiniMax 2013).

    A user/system turn in the middle of a tool-result group makes MiniMax
    reject the next request with ``invalid params, 400 (2013)``.
    """
    out: list[AnyMessage] = []
    for msg in messages:
        if _is_instruction_human(msg) and out and _is_tool(out[-1]):
            out[-1] = _merge_into_tool(out[-1], _content_str(msg))
            continue
        out.append(msg)
    return out
