"""Lark WebSocket plugin: credential test, event parse, message dedupe."""

from __future__ import annotations

from types import SimpleNamespace

from app.server.channels.manager import ChannelManager
from app.server.channels.plugins.lark import _parse_p2_event
from app.server.channels.plugins.lark import test_credentials as check_lark_credentials
from app.server.channels.store import ChannelStore


class _FakeResp:
    def __init__(self, payload: dict, content: bytes = b"{}"):
        self._payload = payload
        self.content = content or b"1"

    def json(self):
        return self._payload


def test_credentials_success():
    def post(url, json, timeout):
        assert "tenant_access_token" in url
        assert json["app_id"] == "cli"
        return _FakeResp({"code": 0, "tenant_access_token": "t-abc"})

    result = check_lark_credentials("cli", "sec", post=post)
    assert result["success"] is True
    assert result["bot_username"] == "lark"


def test_credentials_failure_and_missing():
    assert check_lark_credentials("", "sec")["success"] is False
    def post(url, json, timeout):
        return _FakeResp({"code": 999, "msg": "invalid app"})

    result = check_lark_credentials("cli", "sec", post=post)
    assert result["success"] is False
    assert "invalid" in result["error"]


def test_parse_p2_event_object():
    event = SimpleNamespace(
        header=SimpleNamespace(event_id="evt_1"),
        event=SimpleNamespace(
            message=SimpleNamespace(chat_id="oc_1", content='{"text":"你好"}'),
            sender=SimpleNamespace(sender_id=SimpleNamespace(open_id="ou_1", user_id="u_1")),
        ),
    )
    parsed = _parse_p2_event(event)
    assert parsed["text"] == "你好"
    assert parsed["chat_id"] == "oc_1"
    assert parsed["user_id"] == "ou_1"
    assert parsed["event_id"] == "evt_1"


def test_parse_p2_event_dict():
    parsed = _parse_p2_event(
        {
            "header": {"event_id": "evt_2"},
            "event": {
                "message": {"chat_id": "oc_2", "content": {"text": "ping"}},
                "sender": {"sender_id": {"open_id": "ou_2"}},
            },
        }
    )
    assert parsed["text"] == "ping"
    assert parsed["user_id"] == "ou_2"


def test_message_dedupe(tmp_path):
    seen: list[str] = []

    class TM:
        async def handle(self, req):
            seen.append(req.text)
            yield {"type": "graph.end", "status": "ok"}

    mgr = ChannelManager(
        ChannelStore(tmp_path / "c.db"),
        task_manager=TM(),
        send=lambda *a, **k: None,
        start_lark=lambda *a, **k: None,
        stop_lark=lambda: None,
    )
    mgr.store.authorize_user(
        platform_user_id="ou_1",
        platform_type="lark",
        chat_id="oc_1",
    )
    first = mgr.ingest(
        "lark",
        user_id="ou_1",
        chat_id="oc_1",
        text="once",
        event_id="evt-dup",
    )
    second = mgr.ingest(
        "lark",
        user_id="ou_1",
        chat_id="oc_1",
        text="once",
        event_id="evt-dup",
    )
    assert first.get("ok") is True
    assert second.get("deduped") is True


def test_ws_runtime_start_mocked(monkeypatch):
    from app.server.channels.plugins import lark as lark_plugin

    started = {"n": 0}

    class FakeClient:
        def __init__(self, *a, **k):
            started["n"] += 1
            self.args = a

        def start(self):
            return None

        async def _disconnect(self):
            return None

    class Builder:
        def register_p2_im_message_receive_v1(self, fn):
            return self

        def build(self):
            return object()

    class FakeHandler:
        @staticmethod
        def builder(*a, **k):
            return Builder()

    from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
    import lark_oapi.ws.client as ws_mod

    monkeypatch.setattr(EventDispatcherHandler, "builder", staticmethod(FakeHandler.builder))
    monkeypatch.setattr(ws_mod, "Client", FakeClient)

    statuses: list[str] = []
    runtime = lark_plugin.LarkWsRuntime()
    runtime.start(
        app_id="cli",
        app_secret="sec",
        on_message=lambda p: None,
        on_status=lambda s, e: statuses.append(s),
    )
    assert started["n"] == 1
    assert "connecting" in statuses
    runtime.stop()
