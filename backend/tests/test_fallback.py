"""Tests for FallbackChatModel."""

from typing import Any, Optional, Sequence

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from app.llm.fallback import FallbackChatModel, is_retryable_llm_error


class _Boom(Exception):
    def __init__(self, msg: str, status_code: int = 429):
        super().__init__(msg)
        self.status_code = status_code


class _Scripted(BaseChatModel):
    responses: list[BaseMessage] = Field(default_factory=list)
    fail_times: int = 0
    calls: int = 0

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_Scripted":
        return self

    def _generate(
        self,
        messages: Sequence[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls += 1
        if self.fail_times > 0:
            self.fail_times -= 1
            raise _Boom("rate limit 429")
        if not self.responses:
            raise RuntimeError("no responses")
        return ChatResult(generations=[ChatGeneration(message=self.responses[0])])

    async def _agenerate(
        self,
        messages: Sequence[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)

    @property
    def _llm_type(self) -> str:
        return "scripted"


def test_is_retryable():
    assert is_retryable_llm_error(_Boom("429"))
    assert not is_retryable_llm_error(ValueError("bad schema"))


@pytest.mark.asyncio
async def test_fallback_on_429():
    primary = _Scripted(responses=[], fail_times=1)
    secondary = _Scripted(responses=[AIMessage(content="ok")])
    events: list[tuple[int, str]] = []
    model = FallbackChatModel(
        [primary, secondary],
        on_fallback=lambda i, e: events.append((i, str(e))),
    )
    result = await model.ainvoke([HumanMessage(content="hi")])
    assert result.content == "ok"
    assert primary.calls == 1
    assert secondary.calls == 1
    assert events and events[0][0] == 0


@pytest.mark.asyncio
async def test_fallback_exhausted():
    primary = _Scripted(responses=[], fail_times=2)
    secondary = _Scripted(responses=[], fail_times=2)
    model = FallbackChatModel([primary, secondary])
    with pytest.raises(_Boom):
        await model.ainvoke([HumanMessage(content="hi")])


@pytest.mark.asyncio
async def test_fallback_preserves_leaf_budget_checks_and_usage(monkeypatch):
    from app.llm.context_limits import ModelInputBudgetCallback
    from app.llm.model_config import ModelConfig
    from app.llm.budget_callback import instrument_model_for_budget
    import app.llm.budget_callback as accounting

    recorded = []
    monkeypatch.setattr(accounting, "record_llm_tokens", lambda n, **kw: recorded.append(n))
    primary = instrument_model_for_budget(_Scripted(responses=[AIMessage(content="ok")]))
    config = ModelConfig(id="small", provider="openai_compat", model="small", api_key="", context_window=4096, output_limit=1024)
    secondary = _Scripted(responses=[AIMessage(content="fallback")], callbacks=[ModelInputBudgetCallback(config)])
    chain = FallbackChatModel([primary, secondary])
    assert (await chain.ainvoke([HumanMessage(content="hello")])).content == "ok"
    assert len(recorded) == 1
    primary.fail_times = 1
    with pytest.raises(ValueError, match="上下文"):
        await chain.ainvoke([HumanMessage(content="word " * 10000)])
    assert secondary.calls == 0


def test_sync_fallback_runs_leaf_callbacks():
    from app.llm.context_limits import ModelInputBudgetCallback
    from app.llm.model_config import ModelConfig
    config = ModelConfig(id="small", provider="openai_compat", model="small", api_key="", context_window=4096, output_limit=1024)
    model = _Scripted(responses=[AIMessage(content="ok")], callbacks=[ModelInputBudgetCallback(config)])
    with pytest.raises(ValueError, match="上下文"):
        FallbackChatModel([model]).invoke([HumanMessage(content="word " * 10000)])
    assert model.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("primary_recovers", [True, False])
async def test_fallback_native_blocks_belong_to_actual_leaf_across_tool_turns(primary_recovers):
    from langchain_core.tools import tool
    from app.llm.model_config import ModelConfig, model_scope
    from app.runtime.v2.loop import run_act_loop
    class Recording(_Scripted):
        seen: list = Field(default_factory=list)
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            self.seen.append(list(messages))
            if self.fail_times:
                self.fail_times -= 1
                raise _Boom("429")
            return ChatResult(generations=[ChatGeneration(message=self.responses.pop(0))])
    @tool
    def read() -> str:
        """Read a sample."""
        return "sample"
    a = ModelConfig(id="a", provider="anthropic", model="a", api_key="test")
    b = ModelConfig(id="b", provider="anthropic", model="b", api_key="test")
    blocks = [{"type": "thinking", "thinking": "private B", "signature": "B-signature"}]
    primary = Recording(fail_times=1 if primary_recovers else 2, responses=[AIMessage("A finished")])
    secondary = Recording(responses=[AIMessage(content=blocks, tool_calls=[{"id": "read1", "name": "read", "args": {}}]), AIMessage("B finished")])
    with model_scope(a):
        result = await run_act_loop(FallbackChatModel([primary, secondary], model_configs=[a, b]), [read], [HumanMessage("read the sample")])
    assert result[1].response_metadata["request_model"] == ["anthropic", "b", None]
    assert primary.seen[1][1].content != blocks
    if not primary_recovers:
        assert secondary.seen[1][1].content == blocks
    assert result[1].content == blocks
