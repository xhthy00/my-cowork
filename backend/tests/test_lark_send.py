"""Tests for lark send_message."""

import pytest

from app.tools.builtin.lark.send_message import send


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def create_message(self, chat_id: str, text: str) -> str:
        self.calls.append((chat_id, text))
        return "msg_123"


@pytest.mark.asyncio
async def test_send_message_calls_client_with_chat_and_text():
    client = _FakeClient()
    msg_id = await send("oc_chat_1", "hello lark", client=client)
    assert msg_id == "msg_123"
    assert client.calls == [("oc_chat_1", "hello lark")]


@pytest.mark.asyncio
async def test_send_without_credentials_raises(monkeypatch):
    monkeypatch.delenv("LARK_APP_ID", raising=False)
    monkeypatch.delenv("LARK_APP_SECRET", raising=False)
    monkeypatch.delenv("LARK_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="未配置飞书应用凭证"):
        await send("oc_chat_1", "hello")


def test_lark_tool_returns_error_instead_of_raising(monkeypatch):
    monkeypatch.delenv("LARK_APP_ID", raising=False)
    monkeypatch.delenv("LARK_APP_SECRET", raising=False)
    monkeypatch.delenv("LARK_SECRET", raising=False)
    from app.tools.builtin.lark.tools import make_lark_send_tool

    result = make_lark_send_tool().invoke({"chat_id": "oc_1", "text": "hi"})
    assert "发送飞书消息失败" in result
