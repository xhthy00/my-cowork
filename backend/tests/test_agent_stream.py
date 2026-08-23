"""Tests for LLM token streaming → step.delta."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessageChunk

from app.observability.trace import TraceBus
from app.runtime.agent_stream import astream_llm_content
from app.runtime.todo_context import TodoRuntime, reset_todo_runtime, set_todo_runtime


@pytest.mark.asyncio
async def test_astream_llm_content_emits_step_deltas():
    class _Plain:
        async def astream(self, _messages):
            for ch in ["## 结论\n", "扬州已取消限购。"]:
                yield AIMessageChunk(content=ch)

    bus = TraceBus()
    events: list[dict] = []
    bus.subscribe(events.append)
    token = set_todo_runtime(
        TodoRuntime(task_id="t1", bus=bus, agent_id="synthesize")
    )
    try:
        text = await astream_llm_content(
            _Plain(),
            [{"role": "user", "content": "写终稿"}],
        )
        assert "扬州已取消限购" in text
        deltas = [e["delta"] for e in events if e.get("type") == "step.delta"]
        assert "".join(deltas) == text
        assert all(
            e.get("agent_id") == "synthesize"
            for e in events
            if e.get("type") == "step.delta"
        )
    finally:
        reset_todo_runtime(token)
