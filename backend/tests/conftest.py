from typing import Any, Optional, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field
import pytest


@pytest.fixture(autouse=True)
def isolated_industry_registry(tmp_path_factory, monkeypatch):
    # Registry initialization is now a write; assembly tests must never import
    # or migrate the developer's installed industry apps.
    state = tmp_path_factory.mktemp('host-state')
    monkeypatch.setenv("MY_COWORK_INDUSTRY_APPS_ROOT", str(state / "industry-apps"))
    monkeypatch.setenv("MY_COWORK_DATA_DIR", str(state / "data"))
    monkeypatch.setenv("MY_COWORK_CHANNELS_DB", str(state / "channels.db"))
    mcp_json = state / 'mcp.json'
    mcp_json.write_text('{}')
    monkeypatch.setenv('MY_COWORK_MCP_JSON', str(mcp_json))


class FakeChatModel(BaseChatModel):
    """A deterministic chat model that returns pre-scripted responses."""

    responses: list[BaseMessage] = Field(default_factory=list)
    idx: int = 0
    model_name: str = "cowork:scripted"

    def bind_tools(
        self,
        tools: Any,
        **kwargs: Any,
    ) -> "FakeChatModel":
        """Return self so tool-binding is a no-op."""
        return self

    def _generate(
        self,
        messages: Sequence[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self.idx >= len(self.responses):
            raise RuntimeError("FakeChatModel exhausted its scripted responses")
        message = self.responses[self.idx]
        self.idx += 1
        return ChatResult(generations=[ChatGeneration(message=message)])

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
        return "fake"

    def reset(self) -> None:
        self.idx = 0


def make_ai(content: str = "", tool_calls: Optional[list[dict]] = None) -> AIMessage:
    """Helper to build an AIMessage, optionally with tool_calls."""
    return AIMessage(
        content=content,
        tool_calls=tool_calls or [],
    )
