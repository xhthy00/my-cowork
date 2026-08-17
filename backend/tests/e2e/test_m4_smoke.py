"""M4 smoke: webhook remote policy + scheduler + middleware (mocked Lark)."""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from app.main import create_app
from app.orchestrator.scheduler import SkillScheduler
from app.orchestrator.task_manager import TaskRequest
from app.skills import find_skill


def _sign(ts: str, token: str) -> str:
    return hmac.new(
        token.encode(),
        f"{ts}\n{token}".encode(),
        hashlib.sha256,
    ).hexdigest()


@pytest.mark.asyncio
async def test_m4_remote_safe_skill_allowed_via_webhook(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LARK_VERIFY_TOKEN", "tok")
    monkeypatch.setenv("LARK_IPS", "203.0.113.10")

    # Bundled example skill with no confirm-gated tool whitelist → remote OK
    skill = find_skill("skill-creator")
    assert skill is not None

    events = [{"type": "graph.end", "status": "ok"}]

    async def _handle(req: TaskRequest):
        assert req.source == "lark"
        assert req.reply_chat_id == "oc_ok"
        for e in events:
            yield e

    tm = MagicMock()
    tm.handle = _handle
    replies: list[str] = []

    async def fake_send(chat_id: str, text: str) -> str:
        replies.append(text)
        return "ok"

    app = create_app(task_manager=tm, bus=None, confirm_hub=MagicMock())
    app.state.lark_send = fake_send
    app.state.channels._send = fake_send
    app.state.channels.store.authorize_user(
        platform_user_id="oc_ok",
        platform_type="lark",
        chat_id="oc_ok",
    )

    ts = "1710000000"
    transport = httpx.ASGITransport(app=app, client=("203.0.113.10", 1))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/webhook/lark",
            headers={
                "X-Lark-Request-Timestamp": ts,
                "X-Lark-Signature": _sign(ts, "tok"),
            },
            json={
                "event": {
                    "message": {
                        "chat_id": "oc_ok",
                        "content": '{"text":"请用 skill-creator skill"}',
                    }
                }
            },
        )
    assert res.status_code == 200
    assert res.json().get("ok") is True

    import asyncio

    await asyncio.sleep(0.05)
    assert replies


@pytest.mark.asyncio
async def test_m4_cron_skill_registers_and_runs(tmp_path: Path):
    submitted: list[TaskRequest] = []

    async def _submit(req: TaskRequest) -> str:
        submitted.append(req)
        return "cron-1"

    sched = SkillScheduler(db_path=tmp_path / "m4.db", submit=_submit)
    skill_dir = tmp_path / "cron_heartbeat"
    skill_dir.mkdir()
    (skill_dir / "skill.yaml").write_text(
        "id: cron_heartbeat\nname: Cron Heartbeat\n"
        "schedule: '* * * * *'\nprompt: cron heartbeat tick\n"
        "allowed_tools:\n  - builtin.http.request\n",
        encoding="utf-8",
    )
    ids = sched.register_discovered(tmp_path)
    assert "skill:cron_heartbeat" in ids
    await sched.run_skill("cron_heartbeat", prompt="cron heartbeat tick")
    assert submitted and submitted[0].source == "cron"
    sched.shutdown()
