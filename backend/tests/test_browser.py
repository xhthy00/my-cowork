"""Browser tool registration, URL protection, and approval boundaries."""

from __future__ import annotations

import json

import pytest

from app.guardrails.approval import ConfirmHub, reset_automation_policy, set_automation_policy
from app.sandbox.path_guard import PathGuard
from app.tools.builtin import browser


def _tools(guard: PathGuard | None = None, hub=None):
    return {tool.name: tool for tool in browser.make_browser_tools(guard, hub)}


def test_browser_exposes_openworker_action_set():
    assert set(_tools()) == {
        "browser_navigate", "browser_snapshot", "browser_click", "browser_type",
        "browser_select", "browser_upload_file", "browser_wait",
        "browser_screenshot", "browser_close", "browser_state",
    }


@pytest.mark.asyncio
async def test_browser_navigation_rejects_private_addresses_before_open(monkeypatch):
    class NeverCalled:
        def call(self, *_args):
            raise AssertionError("browser must not start")

    monkeypatch.setattr(browser, "_BROWSER", NeverCalled())
    result = json.loads(await _tools()["browser_navigate"].ainvoke(
        {"url": "http://127.0.0.1:8080/"}
    ))
    assert "non-public" in result["error"]


@pytest.mark.asyncio
async def test_browser_navigation_checks_redirect_destination(monkeypatch):
    class Page:
        url = "about:blank"

        def goto(self, url, **_kwargs):
            self.url = "http://127.0.0.1/private" if url == "https://public.example/" else url

    page = Page()

    class FakeBrowser:
        def call(self, _action, fn):
            return fn(page)

    monkeypatch.setattr(browser, "_BROWSER", FakeBrowser())
    monkeypatch.setattr(
        browser, "_check_url",
        lambda url: None if url == "https://public.example/" else (
            "private destination" if url.startswith("http://") else None
        ),
    )
    result = json.loads(await _tools()["browser_navigate"].ainvoke(
        {"url": "https://public.example/"}
    ))
    assert "private destination" in result["error"]
    assert page.url == "about:blank"


@pytest.mark.asyncio
async def test_browser_upload_rejects_file_outside_workspace(tmp_path):
    allowed = tmp_path / "allowed"
    denied = tmp_path / "denied"
    allowed.mkdir()
    denied.mkdir()
    source = denied / "secret.txt"
    source.write_text("secret")
    result = json.loads(await _tools(PathGuard([str(allowed)]))[
        "browser_upload_file"
    ].ainvoke({"target": "#file", "path": str(source)}))
    assert "not in the whitelist" in result["error"]


@pytest.mark.asyncio
async def test_browser_type_approval_hides_text(monkeypatch):
    class RejectingHub:
        def __init__(self):
            self.args = None

        async def request(self, _call_id, _tool, args):
            self.args = args
            return False

    hub = RejectingHub()
    result = json.loads(await _tools(hub=hub)["browser_type"].ainvoke(
        {"target": "#password", "text": "secret-value"}
    ))
    assert "rejected" in result["error"]
    assert hub.args == {"target": "#password", "text_length": len("secret-value")}


@pytest.mark.asyncio
async def test_scheduled_auto_approval_covers_browser_type(monkeypatch, tmp_path):
    class Browser:
        def state(self):
            return {"url": "https://cn.bing.com/"}

        def call(self, action, fn):
            assert action == "type"
            return {"ok": True, "url": "https://cn.bing.com/"}

    monkeypatch.setattr(browser, "_BROWSER", Browser())
    events: list[dict] = []
    hub = ConfirmHub(emit=events.append)
    policy = set_automation_policy(str(tmp_path), [], auto_approve_commands=True)
    try:
        result = json.loads(await _tools(hub=hub)["browser_type"].ainvoke(
            {"target": "#sb_form_q", "text": "today's news"}
        ))
        assert result["ok"] is True
        assert events == []
    finally:
        reset_automation_policy(policy)
