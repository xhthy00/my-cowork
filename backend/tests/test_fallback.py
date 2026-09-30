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
