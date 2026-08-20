"""Stream agent token chunks to the TraceBus as ``step.delta`` events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _emit_step_delta(text: str) -> None:
    if not text:
        return
    from app.agents.sanitize import strip_model_junk
    from app.runtime.todo_context import get_todo_runtime

    cleaned = strip_model_junk(text)
    if not cleaned:
        # Token streams often emit a lone space/newline; dropping them glues words.
        if not text.isspace():
            return
        cleaned = text

    rt = get_todo_runtime()
    if rt is None or rt.bus is None:
        return
    rt.bus.emit(
        {
            "task_id": rt.task_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "step.delta",
            "delta": cleaned,
        }
    )


def _message_content_text(message: Any) -> tuple[str, str]:
    """Return ``(reasoning, content_text)`` from a message / chunk."""
    additional = getattr(message, "additional_kwargs", None) or {}
    reasoning = ""
    if isinstance(additional, dict):
        reasoning = str(
            additional.get("reasoning_content") or additional.get("reasoning") or ""
        )

    content = getattr(message, "content", None)
    if isinstance(content, str):
        return reasoning, content
    if isinstance(content, list):
        bits: list[str] = []
        for part in content:
            if isinstance(part, str):
                bits.append(part)
            elif isinstance(part, dict):
                if part.get("type") == "reasoning" and part.get("reasoning"):
                    reasoning += str(part["reasoning"])
                elif part.get("text"):
                    bits.append(str(part["text"]))
        return reasoning, "".join(bits)
    return reasoning, ""


async def astream_agent_messages(
    agent: Any,
    invoke_messages: list[Any],
) -> list[Any]:
    """Run *agent* with message streaming; emit ``step.delta``; return final messages."""
    payload = {"messages": invoke_messages}
    if not hasattr(agent, "astream"):
        result = await agent.ainvoke(payload)
        return list(result.get("messages") or [])

    final_messages: list[Any] = list(invoke_messages)
    reasoning_open = False

    async for mode, chunk in agent.astream(
        payload, stream_mode=["messages", "values"]
    ):
        if mode == "messages":
            msg = chunk[0] if isinstance(chunk, tuple) else chunk
            meta = chunk[1] if isinstance(chunk, tuple) and len(chunk) > 1 else {}
            node = str(meta.get("langgraph_node") or "") if isinstance(meta, dict) else ""
            if node in {"tools", "tool"}:
                continue

            reasoning, text = _message_content_text(msg)
            if reasoning:
                if not reasoning_open:
                    _emit_step_delta("<think>")
                    reasoning_open = True
                _emit_step_delta(reasoning)
            if text:
                if reasoning_open:
                    _emit_step_delta("</think>\n")
                    reasoning_open = False
                _emit_step_delta(text)
        elif mode == "values" and isinstance(chunk, dict):
            msgs = chunk.get("messages")
            if isinstance(msgs, list) and msgs:
                final_messages = list(msgs)

    if reasoning_open:
        _emit_step_delta("</think>\n")

    return final_messages
