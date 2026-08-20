"""Thinking / reasoning kwargs on LLM providers."""

from app.llm.gateway import create_model


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
