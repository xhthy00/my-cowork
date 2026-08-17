"""Tests for AuditStore + ConfirmHub / CommandFilter hooks."""

from pathlib import Path

import asyncio

import pytest

from app.guardrails.approval import ConfirmHub
from app.guardrails.audit import AuditStore
from app.guardrails.command_filter import CommandFilter, CommandForbidden


def test_audit_store_log_and_list(tmp_path: Path):
    store = AuditStore(tmp_path / "audit.db")
    store.log(kind="confirm_request", tool="fs.write", call_id="c1", task_id="t1")
    store.log(
        kind="confirm_resolve",
        tool="fs.write",
        call_id="c1",
        ok=True,
        task_id="t1",
    )
    rows = store.list_recent(limit=10)
    assert len(rows) == 2
    kinds = {r["kind"] for r in rows}
    assert kinds == {"confirm_request", "confirm_resolve"}
    store.close()


@pytest.mark.asyncio
async def test_confirm_hub_audits_request_and_resolve(tmp_path: Path):
    audit = AuditStore(tmp_path / "audit.db")
    hub = ConfirmHub(timeout_seconds=0.5, audit=audit)
    task = asyncio.create_task(hub.request("c1", "fs.write", {"path": "/tmp/a"}))
    await asyncio.sleep(0)
    hub.resolve("c1", True)
    assert await task is True
    kinds = [r["kind"] for r in audit.list_recent()]
    assert "confirm_request" in kinds
    assert "confirm_resolve" in kinds
    resolve = next(r for r in audit.list_recent() if r["kind"] == "confirm_resolve")
    assert resolve["ok"] is True
    assert resolve["tool"] == "fs.write"
    audit.close()


def test_command_filter_audits_forbidden(tmp_path: Path):
    audit = AuditStore(tmp_path / "audit.db")
    filt = CommandFilter(audit=audit)
    with pytest.raises(CommandForbidden):
        filt.check("rm -rf /")
    rows = audit.list_recent()
    assert len(rows) == 1
    assert rows[0]["kind"] == "command_forbidden"
    audit.close()
