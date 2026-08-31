"""Thinking / reasoning kwargs on LLM providers."""

import pytest

from app.llm.gateway import create_model
from app.llm.providers import openai_compat
from app.llm.providers.openai_compat import (
    _REASONING_STREAM_CHUNK_TIMEOUT_S,
    _UNSET,
    _resolve_stream_chunk_timeout,
)


@pytest.fixture(autouse=True)
def _clear_stream_chunk_timeout_env(monkeypatch):
    monkeypatch.delenv("MY_COWORK_STREAM_CHUNK_TIMEOUT_S", raising=False)


def test_deepseek_enables_thinking():
    model = create_model(
        "openai_compat", "deepseek-chat", "k", base_url="https://api.deepseek.com"
    )
    assert model.extra_body["chat_template_kwargs"]["thinking"] is True


def test_glm_enables_thinking():
    model = create_model("openai_compat", "glm-4", "k")
    assert model.extra_body["enable_thinking"] is True


def test_o3_sets_reasoning_effort():
    model = create_model("openai_compat", "o3-mini", "k")
    assert model.reasoning_effort == "medium"


def test_gpt4o_does_not_force_reasoning():
    model = create_model("openai_compat", "gpt-4o", "k")
    assert not model.extra_body
    assert not model.reasoning_effort


def test_anthropic_thinking_budget():
    model = create_model("anthropic", "claude-sonnet-4-20250514", "sk-ant")
    assert model.thinking == {"type": "enabled", "budget_tokens": 4096}
    assert int(model.max_tokens) >= 8192


class _CaptureChatOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class TestStreamChunkTimeout:
    def test_minimax_gets_reasoning_timeout(self):
        assert (
            _resolve_stream_chunk_timeout(_UNSET, "minimax-m3")
            == _REASONING_STREAM_CHUNK_TIMEOUT_S
        )

    def test_non_reasoning_model_leaves_timeout_unset(self):
        assert _resolve_stream_chunk_timeout(_UNSET, "gpt-4o") is _UNSET

    def test_env_var_overrides_heuristic(self, monkeypatch):
        monkeypatch.setenv("MY_COWORK_STREAM_CHUNK_TIMEOUT_S", "30")
        assert _resolve_stream_chunk_timeout(_UNSET, "minimax-m3") == 30.0

    def test_env_var_disables_timeout(self, monkeypatch):
        monkeypatch.setenv("MY_COWORK_STREAM_CHUNK_TIMEOUT_S", "off")
        assert _resolve_stream_chunk_timeout(_UNSET, "minimax-m3") is None

    def test_explicit_timeout_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("MY_COWORK_STREAM_CHUNK_TIMEOUT_S", "30")
        assert _resolve_stream_chunk_timeout(90.0, "minimax-m3") == 90.0

    def test_create_openai_compat_passes_minimax_timeout(self, monkeypatch):
        monkeypatch.setattr(openai_compat, "ChatOpenAI", _CaptureChatOpenAI)
        model = openai_compat.create_openai_compat("MiniMax-M3", "k")
        assert model.kwargs["stream_chunk_timeout"] == _REASONING_STREAM_CHUNK_TIMEOUT_S

    def test_create_openai_compat_omits_timeout_for_gpt4o(self, monkeypatch):
        monkeypatch.setattr(openai_compat, "ChatOpenAI", _CaptureChatOpenAI)
        model = openai_compat.create_openai_compat("gpt-4o", "k")
        assert "stream_chunk_timeout" not in model.kwargs
