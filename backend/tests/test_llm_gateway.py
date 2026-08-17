import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.llm.gateway import create_model
from app.llm import token_counter


class FakeEncoding:
    def encode(self, text):
        return text.encode("utf-8")


@pytest.fixture(autouse=True)
def _mock_tiktoken(monkeypatch):
    monkeypatch.setattr(token_counter, "_get_enc", lambda: FakeEncoding())


class TestCreateModel:
    def test_anthropic_returns_chat_anthropic(self):
        model = create_model("anthropic", "claude-sonnet-4-20250514", "sk-ant-key")
        assert isinstance(model, ChatAnthropic)
        assert model.model == "claude-sonnet-4-20250514"
        assert model.anthropic_api_key.get_secret_value() == "sk-ant-key"

    def test_openai_compat_returns_chat_openai(self):
        model = create_model("openai_compat", "gpt-4o", "sk-openai-key")
        assert isinstance(model, ChatOpenAI)
        assert model.model_name == "gpt-4o"
        assert model.openai_api_key.get_secret_value() == "sk-openai-key"

    def test_openai_compat_with_base_url(self):
        model = create_model("openai_compat", "gpt-4o", "sk-key", base_url="https://openrouter.ai/api/v1")
        assert isinstance(model, ChatOpenAI)
        assert str(model.openai_api_base) == "https://openrouter.ai/api/v1"

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            create_model("gemini", "gemini-pro", "key")


class TestTokenCounter:
    def test_count_simple_text(self):
        n = token_counter.count_tokens("Hello, world!")
        assert n > 0
        assert n < 20

    def test_count_messages(self):
        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content="Hello, world!"),
        ]
        n = token_counter.count_tokens(messages)
        assert n > 10
        assert n < 80

    def test_empty_input(self):
        assert token_counter.count_tokens("") == 0

    def test_token_count_increases_with_length(self):
        short = token_counter.count_tokens("hi")
        long = token_counter.count_tokens("hi " * 100)
        assert long > short
