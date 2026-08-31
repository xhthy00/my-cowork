"""Stream agent token chunks to the TraceBus as ``step.delta`` events."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

# How often to ping the UI while waiting on the model (no content required).
LLM_HEARTBEAT_S = 2.0


def _emit_runtime_event(event_type: str, **fields: Any) -> None:
    from app.runtime.todo_context import get_todo_runtime

    rt = get_todo_runtime()
    if rt is None or rt.bus is None:
        return
    rt.bus.emit(
        {
            "task_id": rt.task_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "agent_id": rt.agent_id,
            **fields,
        }
    )


def _emit_step_delta(text: str) -> None:
    if not text:
        return
    from app.agents.sanitize import strip_model_junk

    cleaned = strip_model_junk(text)
    if not cleaned:
        # Token streams often emit a lone space/newline; dropping them glues words.
        if not text.isspace():
            return
        cleaned = text
    _emit_runtime_event("step.delta", delta=cleaned)


def _emit_llm_progress(*, tool: str, chars: int) -> None:
    if chars <= 0:
        return
    _emit_runtime_event("llm.progress", tool=tool, chars=int(chars))


@asynccontextmanager
async def llm_heartbeat(interval_s: float | None = None):
    """Emit ``llm.heartbeat`` while an LLM stream is in flight so the UI stays live."""
    delay = LLM_HEARTBEAT_S if interval_s is None else interval_s
    stop = asyncio.Event()

    async def _beat() -> None:
        while not stop.is_set():
            _emit_runtime_event("llm.heartbeat")
            try:
                await asyncio.wait_for(stop.wait(), timeout=max(0.2, delay))
            except TimeoutError:
                continue

    task = asyncio.create_task(_beat())
    try:
        yield
    finally:
        stop.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


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


async def astream_llm_content(llm: Any, messages: list[Any]) -> str:
    """Stream a plain LLM completion onto the TraceBus as ``step.delta``."""
    from app.agents.sanitize import strip_model_junk

    if llm is None:
        return ""

    parts: list[str] = []
    reasoning_open = False

    def emit_reason(text: str) -> None:
        nonlocal reasoning_open
        if not text:
            return
        if not reasoning_open:
            _emit_step_delta("<think>")
            reasoning_open = True
        _emit_step_delta(text)

    def emit_answer(text: str) -> None:
        nonlocal reasoning_open
        if not text:
            return
        cleaned = text if text.isspace() else strip_model_junk(text)
        if not cleaned:
            return
        if reasoning_open:
            _emit_step_delta("</think>\n")
            reasoning_open = False
        _emit_step_delta(cleaned)
        if not cleaned.isspace():
            parts.append(cleaned)

    if hasattr(llm, "astream"):
        async with llm_heartbeat():
            async for chunk in llm.astream(messages):
                reasoning, text = _message_content_text(chunk)
                if reasoning:
                    emit_reason(reasoning)
                if text:
                    emit_answer(text)
    else:
        msg = await llm.ainvoke(messages)
        _reasoning, text = _message_content_text(msg)
        cleaned = strip_model_junk(text) if text else ""
        if cleaned:
            parts.append(cleaned)

    if reasoning_open:
        _emit_step_delta("</think>\n")
    return "".join(parts).strip()
