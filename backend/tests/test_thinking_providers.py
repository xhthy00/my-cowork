"""Thinking / reasoning kwargs on LLM providers."""

import pytest

from app.llm.gateway import create_model
from model_integrations import openai_compat
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
    assert model.extra_body == {"thinking": {"type": "enabled"}}


def test_native_deepseek_explicitly_disables_thinking():
    model = create_model("openai_compat", "deepseek-flash", "k",
                         base_url="https://api.deepseek.com", thinking=False)
    assert model.extra_body == {"thinking": {"type": "disabled"}}


def test_custom_endpoint_does_not_guess_vendor_flags_from_model_name():
    model = create_model("openai_compat", "deepseek-chat", "k", base_url="http://localhost:8000/v1")
    assert not model.extra_body


def test_glm_enables_thinking():
    model = create_model("openai_compat", "glm-4.7", "k", base_url='https://api.z.ai/api/paas/v4')
    assert model.extra_body == {'thinking': {'type': 'enabled'}}


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


@pytest.mark.parametrize('model_name,url,expected', [
    ('kimi-k2.5', 'https://api.moonshot.ai/v1', {'thinking': {'type': 'disabled'}}),
    ('kimi-k2-thinking', 'https://api.moonshot.ai/v1', None),
    ('glm-4.7', 'https://api.z.ai/api/paas/v4', {'thinking': {'type': 'disabled'}}),
    ('glm-5.3', 'https://api.z.ai/api/paas/v4', None),
    ('qwen-plus', 'https://dashscope.aliyuncs.com/compatible-mode/v1', {'enable_thinking': False}),
    ('MiniMax-M3.1', 'https://api.minimax.io/v1', None),
])
def test_native_thinking_switches_are_capability_specific(model_name, url, expected):
    model = create_model('openai_compat', model_name, 'test-key', base_url=url, thinking=False)
    assert model.extra_body == expected


@pytest.mark.parametrize('name', ['claude-sonnet-4-6', 'claude-opus-4-7', 'claude-sonnet-5-5'])
def test_claude_adaptive_thinking_and_output_default(name):
    model = create_model('anthropic', name, 'test-key', max_tokens=None, base_url='https://proxy.example.test')
    assert model.thinking == {'type': 'adaptive'}
    assert model.max_tokens == 8192
    assert model.anthropic_api_url == 'https://proxy.example.test'


def test_claude_manual_thinking_budget_is_below_output_limit():
    model = create_model('anthropic', 'claude-sonnet-4-5', 'test-key', max_tokens=2048)
    assert model.thinking['budget_tokens'] == 2047
    with pytest.raises(ValueError, match='大于 1024'):
        create_model('anthropic', 'claude-sonnet-4-5', 'test-key', max_tokens=1024)


def test_runtime_fallback_does_not_inherit_different_protocol_endpoint(monkeypatch):
    from cowork_harness import models
    calls = []
    monkeypatch.setenv('MY_COWORK_FALLBACK', 'anthropic:claude-sonnet-5-5')
    monkeypatch.setenv('MY_COWORK_BASE_URL', 'https://api.deepseek.com')
    monkeypatch.setattr(models, 'create_openai_compat', lambda *args, **kwargs: calls.append(kwargs) or create_model('openai_compat', 'gpt-4o-mini', 'test-key'))
    monkeypatch.setattr(models, 'create_anthropic', lambda *args, **kwargs: calls.append(kwargs) or create_model('anthropic', 'claude-sonnet-5-5', 'test-key'))
    models.create_model({'model': 'deepseek-flash', 'provider': 'openai_compat', 'options': {'thinking': True}})
    assert calls == [{'base_url': 'https://api.deepseek.com', 'thinking': True}, {'base_url': None}]


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


class TestMaxTokens:
    def test_omits_max_tokens_by_default(self, monkeypatch):
        monkeypatch.setattr(openai_compat, "ChatOpenAI", _CaptureChatOpenAI)
        model = openai_compat.create_openai_compat("MiniMax-M3", "k")
        assert "max_tokens" not in model.kwargs

    def test_passes_explicit_positive_max_tokens(self, monkeypatch):
        monkeypatch.setattr(openai_compat, "ChatOpenAI", _CaptureChatOpenAI)
        model = openai_compat.create_openai_compat(
            "MiniMax-M3", "k", max_tokens=32768
        )
        assert model.kwargs["max_tokens"] == 32768

    def test_omits_non_positive_max_tokens(self, monkeypatch):
        monkeypatch.setattr(openai_compat, "ChatOpenAI", _CaptureChatOpenAI)
        for value in (0, -1, None):
            model = openai_compat.create_openai_compat(
                "MiniMax-M3", "k", max_tokens=value
            )
            assert "max_tokens" not in model.kwargs
