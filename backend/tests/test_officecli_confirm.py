"""ConfirmHub officecli first-approve-then-auto."""

from __future__ import annotations

import asyncio

import pytest

from app.guardrails.approval import ConfirmHub


@pytest.mark.asyncio
async def test_officecli_auto_after_first_approve():
    events: list[dict] = []
    hub = ConfirmHub(emit=events.append)

    async def approve_first():
        await asyncio.sleep(0.01)
        assert events, "expected confirm request"
        call_id = events[0]["call_id"]
        hub.resolve(call_id, True)

    t = asyncio.create_task(approve_first())
    ok1 = await hub.request("c1", "exec.bash", {"cmd": "officecli --version"})
    await t
    assert ok1 is True
    assert hub._officecli_auto_ok is True

    # Second officecli call should not emit.
    before = len(events)
    ok2 = await hub.request("c2", "exec.bash", {"cmd": "officecli create a.pptx"})
    assert ok2 is True
    assert len(events) == before

    # Non-officecli still requires confirm.
    async def reject():
        await asyncio.sleep(0.01)
        hub.resolve(events[-1]["call_id"], False)

    t2 = asyncio.create_task(reject())
    ok3 = await hub.request("c3", "exec.bash", {"cmd": "ls"})
    await t2
    assert ok3 is False


@pytest.mark.asyncio
async def test_clear_officecli_auto():
    hub = ConfirmHub(emit=lambda _e: None)
    hub._officecli_auto_ok = True
    hub.clear_officecli_auto()
    assert hub._officecli_auto_ok is False
