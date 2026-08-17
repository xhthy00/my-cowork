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

from typing import Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ExtendedModelResponse,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import AIMessage, AnyMessage, ToolMessage

_INVALID_CALL_TEMPLATE = (
    "Invalid tool call: arguments could not be parsed ({args!r}; error: {error}). "
    "Fix the arguments and call the tool again."
)

_MISSING_RESULT_TEMPLATE = (
    "(tool call was not executed — no result available; please retry or continue.)"
)


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


class ToolResponsesMiddleware(AgentMiddleware[Any, Any, Any]):
    """Agent middleware that patches tool responses before each model call."""

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Any,
    ) -> ModelResponse[Any] | AIMessage | ExtendedModelResponse[Any]:
        sanitized = ensure_tool_responses(list(request.messages))
        return handler(request.override(messages=sanitized))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Any,
    ) -> ModelResponse[Any] | AIMessage | ExtendedModelResponse[Any]:
        sanitized = ensure_tool_responses(list(request.messages))
        return await handler(request.override(messages=sanitized))
