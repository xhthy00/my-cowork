"""Tests for Feishu webhook route (ingest + pairing)."""

from __future__ import annotations

import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.main import create_app
from app.server.routes.webhook_lark import REMOTE_DENIED_MSG, verify_lark_signature


def _sign(timestamp: str, token: str) -> str:
    return hmac.new(
        token.encode("utf-8"),
        f"{timestamp}\n{token}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


@pytest.fixture()
def token(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("LARK_VERIFY_TOKEN", "secret-token")
    monkeypatch.setenv("LARK_IPS", "203.0.113.10")
    return "secret-token"


def _app(task_manager=None, lark_send=None):
    tm = task_manager or AsyncMock()
    if not hasattr(tm, "handle"):
        tm.handle = MagicMock()
    app = create_app(task_manager=tm, bus=None, confirm_hub=MagicMock())
    app.state.channels._start_lark = lambda *a, **k: None
    app.state.channels._stop_lark = lambda: None
    if lark_send is not None:
        app.state.lark_send = lark_send
        app.state.channels._send = lark_send
    return app, tm


def _authorize(app, user_id: str, chat_id: str) -> None:
    app.state.channels.store.authorize_user(
        platform_user_id=user_id,
        platform_type="lark",
        chat_id=chat_id,
    )


@pytest.mark.asyncio
async def test_unauthorized_creates_pairing(token: str):
    sent: list[tuple[str, str]] = []

    async def fake_send(chat_id: str, text: str) -> str:
        sent.append((chat_id, text))
        return "m1"

    app, tm = _app(lark_send=fake_send)
    ts = "1710000000"
    transport = httpx.ASGITransport(app=app, client=("203.0.113.10", 1))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/webhook/lark",
            headers={
                "X-Lark-Request-Timestamp": ts,
                "X-Lark-Signature": _sign(ts, token),
            },
            json={
                "event": {
                    "message": {
                        "chat_id": "oc_1",
                        "content": '{"text":"run http_ping please"}',
                    }
                }
            },
        )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body.get("pairing") is True
    import asyncio

    await asyncio.sleep(0.05)
    assert sent and "配对码" in sent[0][1]
    assert not isinstance(tm.handle, AsyncMock) or tm.handle.await_count == 0


@pytest.mark.asyncio
async def test_authorized_submits_task(token: str):
    events = [{"type": "graph.end", "status": "ok"}]

    async def _handle(_req):
        for e in events:
            yield e

    tm = MagicMock()
    tm.handle = _handle
    sent: list[tuple[str, str]] = []

    async def fake_send(chat_id: str, text: str) -> str:
        sent.append((chat_id, text))
        return "m1"

    app, _ = _app(tm, fake_send)
    _authorize(app, "oc_1", "oc_1")
    ts = "1710000000"
    transport = httpx.ASGITransport(app=app, client=("203.0.113.10", 1))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/webhook/lark",
            headers={
                "X-Lark-Request-Timestamp": ts,
                "X-Lark-Signature": _sign(ts, token),
            },
            json={
                "event": {
                    "message": {
                        "chat_id": "oc_1",
                        "content": '{"text":"run http_ping please"}',
                    }
                }
            },
        )
    assert res.status_code == 200
    assert res.json()["ok"] is True
    import asyncio

    await asyncio.sleep(0.05)
    assert sent and sent[0][0] == "oc_1"


@pytest.mark.asyncio
async def test_invalid_signature_401(token: str):
    app, _ = _app()
    transport = httpx.ASGITransport(app=app, client=("203.0.113.10", 1))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/webhook/lark",
            headers={
                "X-Lark-Request-Timestamp": "1710000000",
                "X-Lark-Signature": "deadbeef",
            },
            json={"event": {"message": {"chat_id": "oc_1", "content": '{"text":"hi"}'}}},
        )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_ip_not_in_allowlist_403(token: str):
    app, _ = _app()
    transport = httpx.ASGITransport(app=app, client=("198.51.100.1", 1))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/webhook/lark",
            headers={
                "X-Lark-Request-Timestamp": "1710000000",
                "X-Lark-Signature": _sign("1710000000", token),
            },
            json={"event": {"message": {"chat_id": "oc_1", "content": '{"text":"hi"}'}}},
        )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_office_skill_denied_via_lark(token: str):
    sent: list[tuple[str, str]] = []

    async def fake_send(chat_id: str, text: str) -> str:
        sent.append((chat_id, text))
        return "m1"

    app, tm = _app(lark_send=fake_send)
    _authorize(app, "oc_deny", "oc_deny")
    ts = "1710000000"
    transport = httpx.ASGITransport(app=app, client=("203.0.113.10", 1))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/webhook/lark",
            headers={
                "X-Lark-Request-Timestamp": ts,
                "X-Lark-Signature": _sign(ts, token),
            },
            json={
                "event": {
                    "message": {
                        "chat_id": "oc_deny",
                        "content": '{"text":"用 pptx skill 生成演示文稿"}',
                    }
                }
            },
        )
    assert res.status_code == 200
    body = res.json()
    assert body.get("denied") is True
    assert REMOTE_DENIED_MSG in body["message"]
    import asyncio

    await asyncio.sleep(0.05)
    assert sent and REMOTE_DENIED_MSG in sent[0][1]
    assert not isinstance(tm.handle, AsyncMock) or tm.handle.await_count == 0


def test_verify_signature_helper():
    ts = "123"
    token = "tok"
    sig = _sign(ts, token)
    assert verify_lark_signature(ts, sig, token) is True
    assert verify_lark_signature(ts, "nope", token) is False
