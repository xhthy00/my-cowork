"""Channel manager: test/enable, pairing whitelist, TaskManager ingest."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from app.main import create_app
from app.orchestrator.task_manager import TaskRequest
from app.server.channels.manager import ChannelError, ChannelManager
from app.server.channels.store import ChannelStore
from app.server.routes.webhook_lark import REMOTE_DENIED_MSG


def _mgr(tmp_path, *, test_lark=None):
    sent: list[tuple[str, str]] = []
    tasks: list[TaskRequest] = []

    async def fake_send(chat_id: str, text: str) -> str:
        sent.append((chat_id, text))
        return "m1"

    class TM:
        async def handle(self, req: TaskRequest):
            tasks.append(req)
            yield {"type": "graph.end", "status": "ok"}

    mgr = ChannelManager(
        ChannelStore(tmp_path / "channels.db"),
        task_manager=TM(),
        send=fake_send,
        test_lark=test_lark or (lambda app_id, app_secret: {"success": True, "bot_username": "lark"}),
        start_lark=lambda *a, **k: None,
        stop_lark=lambda: None,
    )
    return mgr, sent, tasks


def test_plugin_success_and_failure(tmp_path):
    mgr, _, _ = _mgr(
        tmp_path,
        test_lark=lambda app_id, app_secret: {"success": True, "bot_username": "lark"},
    )
    assert mgr.test_plugin("lark", {"app_id": "cli", "app_secret": "sec"})["success"] is True

    mgr2, _, _ = _mgr(
        tmp_path,
        test_lark=lambda app_id, app_secret: {"success": False, "error": "bad creds"},
    )
    assert mgr2.test_plugin("lark", {"app_id": "x", "app_secret": "y"})["success"] is False
    assert mgr2.test_plugin("telegram", {})["success"] is False


def test_enable_without_credentials_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("LARK_APP_ID", raising=False)
    monkeypatch.delenv("LARK_APP_SECRET", raising=False)
    mgr, _, _ = _mgr(tmp_path)
    with pytest.raises(ChannelError, match="请输入 App ID 和 App Secret"):
        mgr.enable_plugin("lark", {})
    with pytest.raises(ChannelError, match="即将推出"):
        mgr.enable_plugin("telegram", {})
    with pytest.raises(ChannelError, match="即将推出"):
        mgr.enable_plugin("dingtalk", {})


def test_unauthorized_creates_pairing(tmp_path):
    mgr, sent, tasks = _mgr(tmp_path)
    result = mgr.ingest("lark", user_id="ou_1", chat_id="oc_1", text="hello")
    assert result["pairing"] is True
    assert result["code"]
    assert not tasks
    assert sent and "配对码" in sent[0][1]
    assert mgr.list_pairings()


def test_approve_then_message_goes_to_task_manager(tmp_path):
    mgr, sent, tasks = _mgr(tmp_path)
    result = mgr.ingest("lark", user_id="ou_1", chat_id="oc_1", text="hello", display_name="Ada")
    code = result["code"]
    mgr.approve_pairing(code)
    assert any(u["platform_user_id"] == "ou_1" for u in mgr.list_users())
    sent.clear()
    mgr.ingest("lark", user_id="ou_1", chat_id="oc_1", text="写周报")
    assert tasks and tasks[0].text == "写周报"
    assert tasks[0].source == "lark"
    assert tasks[0].reply_chat_id == "oc_1"
    assert tasks[0].session_mode == "single-agent"


def test_reply_uses_graph_summary(tmp_path):
    sent: list[tuple[str, str]] = []

    async def fake_send(chat_id: str, text: str) -> str:
        sent.append((chat_id, text))
        return "m1"

    class TM:
        async def handle(self, req: TaskRequest):
            yield {"type": "step.delta", "delta": "<think>plan</think>"}
            yield {"type": "step.delta", "delta": "被摘要覆盖"}
            yield {"type": "graph.end", "status": "ok", "summary": "周报已写到桌面"}

    mgr = ChannelManager(
        ChannelStore(tmp_path / "channels.db"),
        task_manager=TM(),
        send=fake_send,
        start_lark=lambda *a, **k: None,
        stop_lark=lambda: None,
    )
    mgr.store.authorize_user(
        platform_user_id="ou_1", platform_type="lark", chat_id="oc_1"
    )
    mgr.ingest("lark", user_id="ou_1", chat_id="oc_1", text="写周报")
    assert sent and sent[-1][1] == "周报已写到桌面"


def test_reply_uses_stream_when_no_summary(tmp_path):
    sent: list[tuple[str, str]] = []

    async def fake_send(chat_id: str, text: str) -> str:
        sent.append((chat_id, text))
        return "m1"

    class TM:
        async def handle(self, req: TaskRequest):
            yield {"type": "step.delta", "delta": "<think>思考</think>你好，我是助手"}
            yield {"type": "graph.end", "status": "ok"}

    mgr = ChannelManager(
        ChannelStore(tmp_path / "channels.db"),
        task_manager=TM(),
        send=fake_send,
        start_lark=lambda *a, **k: None,
        stop_lark=lambda: None,
    )
    mgr.store.authorize_user(
        platform_user_id="ou_1", platform_type="lark", chat_id="oc_1"
    )
    mgr.ingest("lark", user_id="ou_1", chat_id="oc_1", text="你好")
    assert sent and sent[-1][1] == "你好，我是助手"


def test_revoke_user(tmp_path):
    mgr, _, tasks = _mgr(tmp_path)
    result = mgr.ingest("lark", user_id="ou_1", chat_id="oc_1", text="hi")
    mgr.approve_pairing(result["code"])
    user = mgr.list_users()[0]
    mgr.revoke_user(user["id"])
    tasks.clear()
    again = mgr.ingest("lark", user_id="ou_1", chat_id="oc_1", text="again")
    assert again.get("pairing") is True
    assert not tasks


def test_remote_denied_skill_after_authorize(tmp_path):
    mgr, sent, tasks = _mgr(tmp_path)
    result = mgr.ingest("lark", user_id="ou_1", chat_id="oc_1", text="hi")
    mgr.approve_pairing(result["code"])
    sent.clear()
    denied = mgr.ingest("lark", user_id="ou_1", chat_id="oc_1", text="用 pptx skill 生成演示文稿")
    assert denied.get("denied") is True
    assert REMOTE_DENIED_MSG in denied["message"]
    assert not tasks


@pytest.mark.asyncio
async def test_http_plugins_and_enable(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_COWORK_CHANNELS_DB", str(tmp_path / "http-channels.db"))
    monkeypatch.setenv("MY_COWORK_CHANNEL_AUTOSTART", "0")
    monkeypatch.delenv("LARK_APP_ID", raising=False)
    monkeypatch.delenv("LARK_APP_SECRET", raising=False)
    app = create_app(task_manager=MagicMock(), bus=None, confirm_hub=MagicMock())
    app.state.channels._start_lark = lambda *a, **k: None
    app.state.channels._stop_lark = lambda: None
    app.state.channels._test_lark = lambda app_id, app_secret: {"success": True, "bot_username": "lark"}

    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        plugins = (await client.get("/api/channel/plugins")).json()
        ids = [p["plugin_id"] for p in plugins]
        assert ids == ["telegram", "lark", "dingtalk"]
        assert plugins[0]["coming_soon"] is True
        assert plugins[2]["coming_soon"] is True

        bad = await client.post("/api/channel/plugins/enable", json={"plugin_id": "telegram"})
        assert bad.status_code == 400

        missing = await client.post("/api/channel/plugins/enable", json={"plugin_id": "lark", "config": {}})
        assert missing.status_code == 400
        assert "App ID" in missing.json()["detail"]

        test = await client.post(
            "/api/channel/plugins/test",
            json={"plugin_id": "lark", "token": "", "extra_config": {"app_id": "cli", "app_secret": "sec"}},
        )
        assert test.json()["success"] is True

        ok = await client.post(
            "/api/channel/plugins/enable",
            json={
                "plugin_id": "lark",
                "config": {"credentials": {"app_id": "cli", "app_secret": "sec"}},
            },
        )
        assert ok.status_code == 200
        enabled = (await client.get("/api/channel/plugins")).json()
        lark = next(p for p in enabled if p["plugin_id"] == "lark")
        assert lark["enabled"] is True
