import pytest

from app.llm import model_picker


class TestModelPicker:
    def test_supervisor_returns_anthropic_sonnet(self):
        provider, model = model_picker("supervisor")
        assert provider == "anthropic"
        assert model == "claude-sonnet-4-20250514"

    def test_compress_returns_openai_mini(self):
        provider, model = model_picker("compress")
        assert provider == "openai_compat"
        assert model == "gpt-4o-mini"

    def test_unknown_kind_raises(self):
        with pytest.raises(ValueError, match="Unknown task_kind"):
            model_picker("unknown_kind")
