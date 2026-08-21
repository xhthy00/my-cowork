"""Tests for agent message streaming → step.delta."""

from __future__ import annotations

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from app.observability.trace import TraceBus
from app.runtime.agent_stream import astream_agent_messages
from app.runtime.todo_context import TodoRuntime, reset_todo_runtime, set_todo_runtime


class _StreamFake(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "stream-fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(content="<think>plan</think>\nok")
                )
            ]
        )

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        for ch in "<think>plan</think>\nok":
            yield ChatGenerationChunk(message=AIMessageChunk(content=ch))

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop=stop)

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        for c in self._stream(messages, stop=stop):
            yield c


@pytest.mark.asyncio
async def test_astream_agent_messages_emits_step_deltas():
    from langchain.agents import create_agent

    bus = TraceBus()
    events: list[dict] = []
    bus.subscribe(events.append)
    token = set_todo_runtime(
        TodoRuntime(task_id="t1", bus=bus, agent_id="single_agent")
    )
    try:
        agent = create_agent(_StreamFake(), [], system_prompt="x")
        messages = await astream_agent_messages(
            agent, [HumanMessage(content="hi")]
        )
        deltas = [e["delta"] for e in events if e.get("type") == "step.delta"]
        joined = "".join(deltas)
        assert "<think>" in joined
        assert "plan" in joined
        assert "ok" in joined
        assert all(e.get("agent_id") == "single_agent" for e in events if e.get("type") == "step.delta")
        assert any(getattr(m, "type", None) == "ai" for m in messages)
    finally:
        reset_todo_runtime(token)


@pytest.mark.asyncio
async def test_astream_agent_messages_without_runtime_still_returns():
    from langchain.agents import create_agent

    agent = create_agent(_StreamFake(), [], system_prompt="x")
    messages = await astream_agent_messages(agent, [HumanMessage(content="hi")])
    assert messages
    assert any("ok" in str(getattr(m, "content", "")) for m in messages)


@pytest.mark.asyncio
async def test_astream_llm_content_emits_step_deltas():
    from app.runtime.agent_stream import astream_llm_content

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
