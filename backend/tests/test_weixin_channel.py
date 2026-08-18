"""WeChat iLink channel — aligned with AionCore weixin plugin tests."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

import httpx
import pytest

from app.main import create_app
from app.orchestrator.task_manager import TaskRequest
from app.server.channels.manager import (
    CONFIRM_TIMEOUT_HINT,
    ChannelError,
    ChannelManager,
    MISSING_DOC_HINT,
    WEIXIN_FILE_MISSING,
    WEIXIN_FILE_SEND_FAILED,
    WEIXIN_FILE_TOO_LARGE,
    WEIXIN_WORKING,
    compose_channel_reply,
    weixin_progress_text,
)
from app.server.channels.plugins import weixin as weixin_plugin
from app.server.channels.plugins import weixin_media
from app.server.channels.store import ChannelStore


def _mgr(tmp_path, *, start_weixin=None):
    sent: list[tuple[str, str]] = []
    tasks: list[TaskRequest] = []

    async def fake_send(chat_id: str, text: str) -> str:
        sent.append((chat_id, text))
        return "m1"

    class TM:
        async def handle(self, req: TaskRequest):
            tasks.append(req)
            yield {"type": "graph.end", "status": "ok", "summary": "<b>你好</b>"}

    mgr = ChannelManager(
        ChannelStore(tmp_path / "channels.db"),
        task_manager=TM(),
        send=fake_send,
        start_lark=lambda *a, **k: None,
        stop_lark=lambda: None,
        start_weixin=start_weixin if start_weixin is not None else (lambda *a, **k: None),
        stop_weixin=lambda: None,
    )
    return mgr, sent, tasks


class FakeLoginApi:
    def __init__(self, statuses: list[dict], qr: dict | None = None) -> None:
        self.statuses = list(statuses)
        self.qr = qr or {"qrcode": "ticket", "qrcode_img_content": "IMG-CONTENT"}

    def get_bot_qrcode(self) -> dict:
        return self.qr

    def get_qrcode_status(self, qrcode: str) -> dict:
        assert qrcode == "ticket"
        if not self.statuses:
            return {"status": "wait"}
        return self.statuses.pop(0)

    def close(self) -> None:
        return None


def test_backoff_delay_caps_at_600s():
    assert weixin_plugin.backoff_delay(10) == 600
    assert weixin_plugin.backoff_delay(0) == 1
    assert weixin_plugin.backoff_delay(1) == 2
    assert weixin_plugin.backoff_delay(9) == 512


def test_extract_content_text_voice_empty_image():
    _, text, media = weixin_plugin.extract_content(
        [{"type": 1, "text_item": {"text": "hello"}}]
    )
    assert text == "hello"
    assert media is False

    _, voice, _ = weixin_plugin.extract_content(
        [{"type": 3, "voice_item": {"text": "转写"}}]
    )
    assert voice == "转写"

    _, both, _ = weixin_plugin.extract_content(
        [
            {"type": 1, "text_item": {"text": "a"}},
            {"type": 3, "voice_item": {"text": "b"}},
        ]
    )
    assert both == "a\n\nb"

    _, empty, _ = weixin_plugin.extract_content([])
    assert empty == ""

    _, none, has_media = weixin_plugin.extract_content(
        [{"type": 2, "image_item": {"url": "x"}}]
    )
    assert none == ""
    assert has_media is True


def test_login_flow_scaned_then_confirmed_camelcase_and_baseurl():
    api = FakeLoginApi(
        [
            {"status": "scaned"},
            {
                "status": "confirmed",
                "bot_token": "tok",
                "ilink_bot_id": "bot-id",
                "baseurl": "https://custom.ilink.example",
            },
        ]
    )
    events = list(weixin_plugin.login_flow(api=api, sleep=lambda _: None, now=lambda: 0.0))
    assert events[0] == ("qr", {"qrcodeData": "IMG-CONTENT"})
    assert events[1] == ("scanned", {})
    assert events[2] == (
        "done",
        {
            "accountId": "bot-id",
            "botToken": "tok",
            "baseUrl": "https://custom.ilink.example",
        },
    )


def test_login_flow_expired():
    api = FakeLoginApi([{"status": "expired"}])
    events = list(weixin_plugin.login_flow(api=api, sleep=lambda _: None, now=lambda: 0.0))
    assert events[-1] == ("error", {"message": "QR code expired"})


def test_login_flow_missing_img_content():
    api = FakeLoginApi([], qr={"qrcode": "ticket"})
    events = list(weixin_plugin.login_flow(api=api, sleep=lambda _: None, now=lambda: 0.0))
    assert events[0][0] == "error"
    assert "qrcode_img_content" in events[0][1]["message"]


def test_sendmessage_omits_context_token_when_empty():
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        assert request.headers["AuthorizationType"] == "ilink_bot_token"
        assert request.headers["Authorization"] == "Bearer tok"
        assert request.headers["X-WECHAT-UIN"] == "AAAAAAAA"
        return httpx.Response(200, json={"ret": 0})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    api = weixin_plugin.WeixinApi(
        "https://ilinkai.weixin.qq.com",
        "tok",
        client=client,
        wechat_uin="AAAAAAAA",
    )
    api.send_message("user1", "hi", "ctx-1")
    api.send_message("user1", "hi", None)
    api.send_message("user1", "hi", "")
    assert captured[0]["msg"]["context_token"] == "ctx-1"
    assert captured[0]["msg"]["message_type"] == 2
    assert captured[0]["msg"]["message_state"] == 2
    assert captured[0]["msg"]["item_list"][0]["type"] == 1
    assert "context_token" not in captured[1]["msg"]
    assert "context_token" not in captured[2]["msg"]
    client.close()


def test_empty_from_user_id_does_not_ingest():
    runtime = weixin_plugin.WeixinRuntime()
    got: list[dict] = []
    runtime._handle_message(
        {
            "from_user_id": "",
            "msg_id": "m1",
            "item_list": [{"type": 1, "text_item": {"text": "hi"}}],
        },
        got.append,
    )
    assert got == []
    runtime._handle_message(
        {
            "from_user_id": "wxid_abcdef123456",
            "msg_id": "m2",
            "item_list": [{"type": 2}],
        },
        got.append,
    )
    assert got == []
    runtime._handle_message(
        {
            "from_user_id": "wxid_abcdef123456",
            "msg_id": "m3",
            "context_token": "ctx",
            "item_list": [{"type": 1, "text_item": {"text": "你好"}}],
        },
        got.append,
    )
    assert got[0]["user_id"] == "wxid_abcdef123456"
    assert got[0]["text"] == "你好"
    assert got[0]["display_name"] == "123456"
    assert got[0]["event_id"] == "m3"
    assert runtime._context["wxid_abcdef123456"] == "ctx"


def test_context_token_persisted(tmp_path):
    store = ChannelStore(tmp_path / "channels.db")
    runtime = weixin_plugin.WeixinRuntime(store)
    runtime._handle_message(
        {
            "from_user_id": "wxid_user",
            "msg_id": "m1",
            "context_token": "ctx-persist",
            "item_list": [{"type": 1, "text_item": {"text": "hi"}}],
        },
        lambda *_: None,
    )
    assert store.get_context_token("weixin", "wxid_user") == "ctx-persist"


def test_unauthorized_weixin_sends_pairing_hint(tmp_path):
    mgr, sent, tasks = _mgr(tmp_path)
    result = mgr.ingest("weixin", user_id="wx_1", chat_id="wx_1", text="hello")
    assert result["pairing"] is True
    assert not tasks
    assert sent and "配对码" in sent[0][1]
    assert "设置 → 远程连接 → 微信" in sent[0][1]


def test_weixin_reply_strips_html(tmp_path):
    mgr, sent, _tasks = _mgr(tmp_path)
    mgr.store.authorize_user(platform_user_id="wx_1", platform_type="weixin", chat_id="wx_1")
    mgr.ingest("weixin", user_id="wx_1", chat_id="wx_1", text="你好")
    assert sent[0][1] == WEIXIN_WORKING
    assert sent[-1][1] == "你好"
    assert "<b>" not in sent[-1][1]


def test_weixin_followup_includes_history(tmp_path):
    mgr, _sent, tasks = _mgr(tmp_path)
    mgr.store.authorize_user(platform_user_id="wx_1", platform_type="weixin", chat_id="wx_1")
    mgr.ingest("weixin", user_id="wx_1", chat_id="wx_1", text="调研大模型备案")
    assert tasks[0].history is None
    mgr.ingest("weixin", user_id="wx_1", chat_id="wx_1", text="帮我生成一份 Word")
    hist = tasks[1].history
    assert hist is not None
    assert hist[0] == {"role": "user", "content": "调研大模型备案"}
    assert hist[1] == {"role": "assistant", "content": "你好"}
    contents = [t["content"] for t in hist]
    assert WEIXIN_WORKING not in contents


def test_chat_history_keeps_context_token(tmp_path):
    store = ChannelStore(tmp_path / "channels.db")
    store.set_context_token("weixin", "wx_1", "ctx-1")
    store.append_chat_turns(
        "weixin",
        "wx_1",
        "wx_1",
        [
            {"role": "user", "content": "调研备案"},
            {"role": "assistant", "content": "结论如下"},
        ],
    )
    assert store.get_context_token("weixin", "wx_1") == "ctx-1"
    assert store.get_chat_history("weixin", "wx_1", "wx_1")[0]["content"] == "调研备案"


def test_chat_history_expires_after_idle(tmp_path, monkeypatch):
    monkeypatch.setattr("app.server.channels.store.HISTORY_IDLE_TTL_MS", 1)
    store = ChannelStore(tmp_path / "channels.db")
    store.append_chat_turns(
        "weixin",
        "wx_1",
        "wx_1",
        [{"role": "user", "content": "旧话题"}, {"role": "assistant", "content": "旧回复"}],
    )
    store._conn.execute("UPDATE channel_sessions SET history_updated_at = 1")
    store._conn.commit()
    assert store.get_chat_history("weixin", "wx_1", "wx_1") == []


def test_weixin_progress_text_from_todo_state():
    assert weixin_progress_text({"type": "step.delta", "delta": "x"}) is None
    assert weixin_progress_text(
        {"type": "todo_state", "todos": [{"content": "检索备案资料", "status": "in_progress"}]}
    ) == "正在：检索备案资料"
    assert weixin_progress_text(
        {
            "type": "todo_state",
            "todos": [{"active_form": "正在检索备案资料", "status": "in_progress"}],
        }
    ) == "正在检索备案资料"


def test_weixin_sends_todo_progress(tmp_path, monkeypatch):
    monkeypatch.setattr("app.server.channels.manager.WEIXIN_PROGRESS_MIN_SECS", 0)
    sent: list[tuple[str, str]] = []

    async def fake_send(chat_id: str, text: str) -> str:
        sent.append((chat_id, text))
        return "m1"

    class TM:
        async def handle(self, req: TaskRequest):
            yield {
                "type": "todo_state",
                "todos": [{"content": "检索备案资料", "status": "in_progress"}],
            }
            yield {"type": "graph.end", "status": "ok", "summary": "调研完成"}

    mgr = ChannelManager(
        ChannelStore(tmp_path / "channels.db"),
        task_manager=TM(),
        send=fake_send,
        start_lark=lambda *a, **k: None,
        stop_lark=lambda: None,
        start_weixin=lambda *a, **k: None,
        stop_weixin=lambda: None,
    )
    mgr.store.authorize_user(platform_user_id="wx_1", platform_type="weixin", chat_id="wx_1")
    mgr.ingest("weixin", user_id="wx_1", chat_id="wx_1", text="帮我调研备案")
    texts = [t for _, t in sent]
    assert texts[0] == WEIXIN_WORKING
    assert "正在：检索备案资料" in texts
    assert texts[-1] == "调研完成"


def test_compose_channel_reply_weixin_strips_html_no_lark_truncation():
    long_text = "x" * 9000
    assert compose_channel_reply(summary=f"<b>{long_text}</b>", platform="weixin") == long_text
    truncated = compose_channel_reply(summary=long_text, platform="lark")
    assert truncated.endswith("…")
    assert len(truncated) == 8000


def test_compose_channel_reply_maps_confirm_timeout():
    raw = "Confirmation request exec.bash:cf1c4f7593e14ed48ca05f35b4f4073a timed out after 600.0s"
    text = compose_channel_reply(error=raw, platform="weixin")
    assert text == CONFIRM_TIMEOUT_HINT
    assert "timed out" not in text
    assert "exec.bash" not in text


def test_compose_channel_reply_prefers_body_over_missing_doc_error():
    from app.server.channels.manager import MISSING_DOC_HINT

    err = "未生成文档文件。请重试；若弹出写入确认，请点击允许。"
    text = compose_channel_reply(
        error=err,
        streamed="衣物、药品、儿童用品清单……",
        platform="weixin",
    )
    assert "写入确认" not in text
    assert "衣物" in text
    empty = compose_channel_reply(error=err, platform="weixin")
    assert empty == MISSING_DOC_HINT
    dump = (
        "Working Directory: e950532f\n"
        "Final Output Directory: /tmp/out\n"
        "officecli 1.0.144 is ready"
    )
    hidden = compose_channel_reply(error=err, streamed=dump, platform="weixin")
    assert hidden == MISSING_DOC_HINT
    assert "officecli" not in hidden
    claimed = (
        "最终交付文件\n"
        "- 路径：`/Users/me/runs/x/江苏兴化旅游攻略.docx`"
    )
    claimed_hidden = compose_channel_reply(error=err, streamed=claimed, platform="weixin")
    assert claimed_hidden == MISSING_DOC_HINT
    assert "兴化" not in claimed_hidden


def test_enable_weixin_requires_scan(tmp_path, monkeypatch):
    monkeypatch.delenv("WEIXIN_BOT_TOKEN", raising=False)
    monkeypatch.delenv("WEIXIN_ACCOUNT_ID", raising=False)
    mgr, _, _ = _mgr(tmp_path)
    with pytest.raises(ChannelError, match="请先使用微信扫码登录"):
        mgr.enable_plugin("weixin", {})


def test_enable_weixin_reuses_stored_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("WEIXIN_BOT_TOKEN", raising=False)
    monkeypatch.delenv("WEIXIN_ACCOUNT_ID", raising=False)
    mgr, _, _ = _mgr(tmp_path)
    mgr.enable_plugin(
        "weixin",
        {"credentials": {"account_id": "acc", "bot_token": "tok"}},
    )
    assert mgr.list_plugins()[-1]["plugin_id"] == "weixin"
    weixin = next(p for p in mgr.list_plugins() if p["plugin_id"] == "weixin")
    assert weixin["enabled"] is True
    mgr.disable_plugin("weixin")
    mgr.enable_plugin("weixin", {"credentials": {}})
    weixin = next(p for p in mgr.list_plugins() if p["plugin_id"] == "weixin")
    assert weixin["enabled"] is True


def test_get_updates_buf_persisted(tmp_path):
    store = ChannelStore(tmp_path / "channels.db")
    store.upsert_plugin("weixin", type="weixin", name="微信 ClawBot")
    calls = {"n": 0}

    class FakeApi:
        bot_token = ""
        base_url = ""

        def get_updates(self, buf: str) -> dict:
            calls["n"] += 1
            if calls["n"] == 1:
                return {"ret": 0, "errcode": 0, "get_updates_buf": "NEXT-BUF", "msgs": []}
            time.sleep(0.05)
            return {"ret": 0, "errcode": 0, "get_updates_buf": "NEXT-BUF", "msgs": []}

        def close(self) -> None:
            return None

    runtime = weixin_plugin.WeixinRuntime(store, api=FakeApi())
    runtime.start(bot_token="t", account_id="a", on_message=lambda *_: None)
    deadline = time.time() + 2
    while time.time() < deadline:
        if store.get_plugin_config("weixin").get("get_updates_buf") == "NEXT-BUF":
            break
        time.sleep(0.05)
    runtime.stop()
    assert store.get_plugin_config("weixin").get("get_updates_buf") == "NEXT-BUF"


def test_qrcode_second_request_unwraps_data():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        assert "bot_type=3" in str(request.url)
        assert request.headers["iLink-App-ClientVersion"] == "1"
        if calls["n"] == 1:
            return httpx.Response(200, json={"ret": 0})
        return httpx.Response(
            200,
            json={"data": {"qrcode": "ticket", "qrcode_img_content": "IMG"}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    api = weixin_plugin.WeixinApi("https://ilinkai.weixin.qq.com", "", client=client)
    data = api.get_bot_qrcode()
    assert data["qrcode"] == "ticket"
    assert data["qrcode_img_content"] == "IMG"
    assert calls["n"] == 2
    client.close()


@pytest.mark.asyncio
async def test_weixin_login_sse_camelcase(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_COWORK_CHANNELS_DB", str(tmp_path / "http-channels.db"))
    monkeypatch.setenv("MY_COWORK_CHANNEL_AUTOSTART", "0")

    def fake_login_flow(**_kwargs):
        yield "qr", {"qrcodeData": "IMG"}
        yield "scanned", {}
        yield "done", {
            "accountId": "acc",
            "botToken": "tok",
            "baseUrl": "https://ilinkai.weixin.qq.com",
        }

    monkeypatch.setattr(
        "app.server.routes.channels.weixin_plugin.login_flow",
        fake_login_flow,
    )
    app = create_app(task_manager=MagicMock(), bus=None, confirm_hub=MagicMock())
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("GET", "/api/channel/weixin/login") as resp:
            assert resp.status_code == 200
            body = ""
            async for chunk in resp.aiter_text():
                body += chunk
                if "event: done" in body:
                    break
    assert "event: qr" in body
    assert "qrcodeData" in body
    assert "event: scanned" in body
    assert "accountId" in body
    assert "botToken" in body
    assert "baseUrl" in body


def test_ciphertext_size_pkcs7():
    assert weixin_media.ciphertext_size(0) == 16
    assert weixin_media.ciphertext_size(15) == 16
    assert weixin_media.ciphertext_size(16) == 32
    assert weixin_media.ciphertext_size(248731) == 248736


def test_aes_key_for_send_is_base64_of_hex_ascii():
    key = bytes.fromhex("00112233445566778899aabbccddeeff")
    assert (
        weixin_media.aes_key_for_send(key)
        == "MDAxMTIyMzM0NDU1NjY3Nzg4OTlhYWJiY2NkZGVlZmY="
    )


def test_aes128_ecb_roundtrip():
    key = b"0123456789abcdef"
    plaintext = b"hello office docx"
    ciphertext = weixin_media.aes128_ecb_pkcs7(plaintext, key)
    assert len(ciphertext) == weixin_media.ciphertext_size(len(plaintext))
    assert weixin_media.aes128_ecb_decrypt(ciphertext, key) == plaintext


def test_send_file_upload_chain(tmp_path, monkeypatch):
    key = bytes.fromhex("00112233445566778899aabbccddeeff")
    filekey = "aa" * 16
    monkeypatch.setattr(weixin_plugin, "random_aes_key", lambda: key)
    monkeypatch.setattr(weixin_plugin, "random_filekey", lambda: filekey)
    path = tmp_path / "报价单.docx"
    plaintext = b"office-bytes"
    path.write_bytes(plaintext)
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.url.path.endswith("getuploadurl"):
            captured["upload"] = json.loads(request.content)
            return httpx.Response(200, json={"ret": 0, "upload_param": "UP-PARAM"})
        if request.url.path.endswith("/upload"):
            captured["cdn_ct"] = request.headers.get("content-type")
            captured["cdn_body"] = bytes(request.content)
            captured["cdn_url"] = url
            return httpx.Response(200, headers={"x-encrypted-param": "DL-PARAM"})
        if request.url.path.endswith("sendmessage"):
            captured["send"] = json.loads(request.content)
            return httpx.Response(200, json={})
        return httpx.Response(404, text="missing")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    api = weixin_plugin.WeixinApi(
        "https://ilinkai.weixin.qq.com",
        "tok",
        client=client,
        cdn_base_url="https://cdn.test/c2c",
    )
    api.send_file("wx_user", str(path), "ctx-token")
    client.close()

    upload = captured["upload"]
    assert isinstance(upload, dict)
    assert upload["media_type"] == 3
    assert upload["aeskey"] == key.hex()
    assert upload["filekey"] == filekey
    assert upload["rawsize"] == len(plaintext)
    assert upload["filesize"] == weixin_media.ciphertext_size(len(plaintext))
    assert upload["rawfilemd5"] == weixin_media.md5_hex(plaintext)
    assert upload["no_need_thumb"] is True

    assert captured["cdn_ct"] == "application/octet-stream"
    assert "encrypted_query_param=UP-PARAM" in str(captured["cdn_url"])
    ciphertext = weixin_media.aes128_ecb_pkcs7(plaintext, key)
    assert captured["cdn_body"] == ciphertext

    send = captured["send"]
    assert isinstance(send, dict)
    item = send["msg"]["item_list"][0]
    assert send["msg"]["from_user_id"] == ""
    assert send["msg"]["context_token"] == "ctx-token"
    assert send["base_info"]["channel_version"] == "my-cowork-0.1.0"
    assert item["type"] == 4
    assert item["file_item"]["file_name"] == "报价单.docx"
    assert item["file_item"]["len"] == str(len(plaintext))
    assert item["file_item"]["md5"] == weixin_media.md5_hex(plaintext)
    assert item["file_item"]["media"]["encrypt_query_param"] == "DL-PARAM"
    assert item["file_item"]["media"]["aes_key"] == weixin_media.aes_key_for_send(key)
    assert item["file_item"]["media"]["encrypt_type"] == 1


def test_send_file_prefers_upload_full_url(tmp_path, monkeypatch):
    key = bytes.fromhex("00112233445566778899aabbccddeeff")
    filekey = "bb" * 16
    monkeypatch.setattr(weixin_plugin, "random_aes_key", lambda: key)
    monkeypatch.setattr(weixin_plugin, "random_filekey", lambda: filekey)
    path = tmp_path / "备案.docx"
    path.write_bytes(b"office-bytes")
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.url.path.endswith("getuploadurl"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "ret": 0,
                        "upload_full_url": "https://cdn.test/full-upload?k=1",
                    }
                },
            )
        if url.startswith("https://cdn.test/full-upload"):
            captured["cdn_url"] = url
            captured["cdn_body"] = bytes(request.content)
            return httpx.Response(200, headers={"x-encrypted-param": "DL-FULL"})
        if request.url.path.endswith("sendmessage"):
            captured["send"] = request.content
            return httpx.Response(200, content=b"")
        return httpx.Response(404, text="missing")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    api = weixin_plugin.WeixinApi(
        "https://ilinkai.weixin.qq.com",
        "tok",
        client=client,
        cdn_base_url="https://cdn.test/c2c",
    )
    api.send_file("wx_user", str(path), "ctx-token")
    client.close()

    assert captured["cdn_url"] == "https://cdn.test/full-upload?k=1"
    assert "encrypted_query_param" not in str(captured["cdn_url"])
    send_raw = captured["send"]
    assert isinstance(send_raw, (bytes, bytearray))
    send = json.loads(send_raw)
    assert send["msg"]["item_list"][0]["file_item"]["media"]["encrypt_query_param"] == "DL-FULL"


def test_runtime_send_file_requires_context_token(tmp_path):
    store = ChannelStore(tmp_path / "channels.db")
    api = MagicMock()
    runtime = weixin_plugin.WeixinRuntime(store, api=api)
    runtime._api = api
    with pytest.raises(RuntimeError, match="missing context_token"):
        runtime.send_file("wx_1", str(tmp_path / "a.docx"))
    api.send_file.assert_not_called()


def _weixin_file_mgr(tmp_path, events, runtime):
    sent: list[tuple[str, str]] = []

    async def fake_send(chat_id: str, text: str) -> str:
        sent.append((chat_id, text))
        return "m1"

    class TM:
        async def handle(self, req: TaskRequest):
            for event in events:
                yield event

    mgr = ChannelManager(
        ChannelStore(tmp_path / "channels.db"),
        task_manager=TM(),
        send=fake_send,
        start_lark=lambda *a, **k: None,
        stop_lark=lambda: None,
        start_weixin=lambda *a, **k: None,
        stop_weixin=lambda: None,
    )
    mgr._runtimes["weixin"] = runtime
    mgr.store.authorize_user(platform_user_id="wx_1", platform_type="weixin", chat_id="wx_1")
    return mgr, sent


def test_weixin_sends_artifact_file_after_text(tmp_path):
    art = tmp_path / "out.docx"
    art.write_bytes(b"doc")
    runtime = MagicMock()
    mgr, _sent = _weixin_file_mgr(
        tmp_path,
        [
            {"type": "artifact.file", "path": str(art)},
            {"type": "artifact.file", "path": str(art)},
            {"type": "graph.end", "status": "ok", "summary": "已生成 Word"},
        ],
        runtime,
    )
    mgr.ingest("weixin", user_id="wx_1", chat_id="wx_1", text="帮我生成 Word")
    texts = [c.args[1] for c in runtime.send_text.call_args_list]
    assert texts[0] == WEIXIN_WORKING
    assert texts[-1] == "已生成 Word"
    runtime.send_file.assert_called_once_with("wx_1", str(art))
    seq = [c[0] for c in runtime.method_calls if c[0] in {"send_text", "send_file"}]
    assert seq[-2] == "send_text"
    assert seq[-1] == "send_file"


def test_weixin_hides_workspace_dump_when_no_file(tmp_path):
    dump = (
        "Working Directory: e950532f\n"
        "Final Output Directory: /tmp/out\n"
        "officecli 1.0.144 is ready\n"
        "Execution Plan: Batch 1"
    )
    runtime = MagicMock()
    mgr, _sent = _weixin_file_mgr(
        tmp_path,
        [{"type": "graph.end", "status": "ok", "summary": dump}],
        runtime,
    )
    mgr.ingest("weixin", user_id="wx_1", chat_id="wx_1", text="整理宜昌旅游攻略 word 版本发我")
    texts = [c.args[1] for c in runtime.send_text.call_args_list]
    assert MISSING_DOC_HINT in texts
    assert all("officecli" not in t for t in texts)
    runtime.send_file.assert_not_called()


def test_weixin_sends_claimed_path_without_artifact_event(tmp_path):
    art = tmp_path / "江苏兴化旅游攻略.docx"
    art.write_bytes(b"doc")
    summary = f"最终交付文件\n- 路径：`{art}`"
    runtime = MagicMock()
    mgr, _sent = _weixin_file_mgr(
        tmp_path,
        [{"type": "graph.end", "status": "ok", "summary": summary}],
        runtime,
    )
    mgr.ingest(
        "weixin",
        user_id="wx_1",
        chat_id="wx_1",
        text="整理兴化旅游攻略 word 版本发我",
    )
    runtime.send_file.assert_called_once_with("wx_1", str(art.resolve()))


def test_weixin_claimed_missing_path_uses_hint(tmp_path):
    missing = tmp_path / "gone.docx"
    summary = f"最终交付文件\n- 路径：`{missing}`"
    runtime = MagicMock()
    mgr, _sent = _weixin_file_mgr(
        tmp_path,
        [{"type": "graph.end", "status": "ok", "summary": summary}],
        runtime,
    )
    mgr.ingest(
        "weixin",
        user_id="wx_1",
        chat_id="wx_1",
        text="整理兴化旅游攻略 word 版本发我",
    )
    texts = [c.args[1] for c in runtime.send_text.call_args_list]
    assert MISSING_DOC_HINT in texts
    runtime.send_file.assert_not_called()


def test_weixin_missing_and_oversize_artifacts_hint(tmp_path, monkeypatch):
    monkeypatch.setattr("app.server.channels.manager.WEIXIN_FILE_MAX_BYTES", 8)
    missing = tmp_path / "gone.docx"
    huge = tmp_path / "huge.docx"
    huge.write_bytes(b"0123456789")
    runtime = MagicMock()
    mgr, _sent = _weixin_file_mgr(
        tmp_path,
        [
            {"type": "artifact.file", "path": str(missing)},
            {"type": "artifact.file", "path": str(huge)},
            {"type": "graph.end", "status": "ok", "summary": "完成"},
        ],
        runtime,
    )
    mgr.ingest("weixin", user_id="wx_1", chat_id="wx_1", text="生成")
    runtime.send_file.assert_not_called()
    texts = [c.args[1] for c in runtime.send_text.call_args_list]
    assert "完成" in texts
    assert WEIXIN_FILE_MISSING.format(path=str(missing)) in texts
    assert WEIXIN_FILE_TOO_LARGE.format(path=str(huge)) in texts


def test_weixin_send_file_failure_keeps_text(tmp_path):
    art = tmp_path / "out.docx"
    art.write_bytes(b"doc")
    runtime = MagicMock()
    runtime.send_file.side_effect = RuntimeError("cdn boom")
    mgr, _sent = _weixin_file_mgr(
        tmp_path,
        [
            {"type": "artifact.file", "path": str(art)},
            {"type": "graph.end", "status": "ok", "summary": "已生成"},
        ],
        runtime,
    )
    mgr.ingest("weixin", user_id="wx_1", chat_id="wx_1", text="生成")
    texts = [c.args[1] for c in runtime.send_text.call_args_list]
    assert "已生成" in texts
    assert WEIXIN_FILE_SEND_FAILED.format(path=str(art), reason="cdn boom") in texts
    runtime.send_file.assert_called_once()
