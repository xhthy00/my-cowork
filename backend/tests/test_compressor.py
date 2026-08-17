"""Tests for context compressor."""

from dataclasses import dataclass, field

import pytest
from langchain_core.messages import HumanMessage

from app.runtime import compressor as compressor_mod
from app.runtime.compressor import maybe_compress


@dataclass
class _Ctx:
    messages: list = field(default_factory=list)


@pytest.mark.asyncio
async def test_maybe_compress_130k_keeps_last_5(monkeypatch: pytest.MonkeyPatch):
    older = [HumanMessage(content=f"old-{i}") for i in range(80)]
    recent = [HumanMessage(content=f"keep-{i}") for i in range(5)]
    ctx = _Ctx(messages=[*older, *recent])

    # Pretend the history is 130k tokens before compress, ~1k after.
    calls = {"n": 0}

    def fake_count(messages):
        calls["n"] += 1
        # First call (pre-check) → over threshold; later calls unused
        if calls["n"] == 1:
            return 130_000
        return 1_000

    monkeypatch.setattr(compressor_mod, "count_tokens", fake_count)

    async def summarize(_msgs):
        return "FIXED_SUMMARY"

    ran = await maybe_compress(ctx, threshold=120_000, keep=5, summarize=summarize)
    assert ran is True
    assert [m.content for m in ctx.messages[-5:]] == [f"keep-{i}" for i in range(5)]
    assert ctx.messages[0].content == "FIXED_SUMMARY"
    # summary + 5 kept
    assert len(ctx.messages) == 6
    # Post-compress token count under 30k (plan acceptance)
    assert compressor_mod.count_tokens(ctx.messages) < 30_000


@pytest.mark.asyncio
async def test_make_llm_summarize_uses_compress_picker(monkeypatch: pytest.MonkeyPatch):
    creates: list[tuple] = []

    class _FakeLLM:
        async def ainvoke(self, prompt):
            return type("R", (), {"content": "LLM_SUMMARY"})()

    def fake_create(provider, model, api_key, **kwargs):
        creates.append((provider, model, api_key))
        return _FakeLLM()

    monkeypatch.setenv("MY_COWORK_API_KEY", "k")
    monkeypatch.setattr("app.llm.gateway.create_model", fake_create)
    monkeypatch.setattr(
        "app.llm.router.model_picker",
        lambda kind: ("openai_compat", "gpt-4o-mini") if kind == "compress" else ("x", "y"),
    )

    from app.runtime.compressor import make_llm_summarize

    fn = make_llm_summarize()
    text = await fn([HumanMessage(content="hello world")])
    assert "LLM_SUMMARY" in text
    assert creates and creates[0][0] == "openai_compat"
    assert creates[0][1] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_maybe_compress_under_threshold_noop(monkeypatch: pytest.MonkeyPatch):
    ctx = _Ctx(messages=[HumanMessage(content="hi")] * 3)
    monkeypatch.setattr(compressor_mod, "count_tokens", lambda _m: 100)
    assert await maybe_compress(ctx, threshold=120_000) is False
    assert len(ctx.messages) == 3
