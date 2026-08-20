"""Minimal CDP / HTTP browser tools. Uses Electron CDP pool when MY_COWORK_CDP_PORT is set."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.tools.builtin.web_fetch import web_fetch

_TIMEOUT = 15.0
_STATE: dict[str, str] = {"url": ""}


def _cdp_port() -> int | None:
    raw = (os.environ.get("MY_COWORK_CDP_PORT") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


async def _cdp_json(path: str, method: str = "GET") -> Any:
    port = _cdp_port()
    if port is None:
        return None
    url = f"http://127.0.0.1:{port}{path}"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        if method == "PUT":
            res = await client.put(url)
        else:
            res = await client.get(url)
        res.raise_for_status()
        if res.headers.get("content-type", "").startswith("application/json"):
            return res.json()
        return res.text


class NavArgs(BaseModel):
    url: str = Field(description="http(s) URL to open")


class ClickArgs(BaseModel):
    selector: str = Field(description="CSS selector or visible text to click (best-effort)")


async def browser_navigate(url: str) -> str:
    target = (url or "").strip()
    if not target.startswith(("http://", "https://")):
        return "[ERROR] url must be http(s). Do not invent URLs."
    _STATE["url"] = target
    port = _cdp_port()
    if port is not None:
        try:
            await _cdp_json("/json/new?" + quote(target, safe=""), method="PUT")
            return f"Opened in CDP browser on port {port}: {target}"
        except Exception as exc:
            return f"CDP navigate failed ({exc}); current URL set to {target}. Use browser_snapshot."
    return f"No CDP browser. URL recorded as {target}. Use browser_snapshot / web_fetch."


async def browser_snapshot() -> str:
    url = _STATE.get("url") or ""
    if not url:
        return "[ERROR] No current page. Call browser_navigate first."
    return await web_fetch(url)


async def browser_click(selector: str) -> str:
    _ = selector
    if _cdp_port() is None:
        return (
            "[ERROR] Interactive click requires a CDP browser "
            "(Electron cdp:launch / MY_COWORK_CDP_PORT). Ask the user to open the browser pool."
        )
    return (
        "CDP click is best-effort in this build. If a login wall is visible, "
        "ask the user to complete it in the opened Chrome window, then call browser_snapshot."
    )


def make_browser_tools() -> list[StructuredTool]:
    return [
        StructuredTool.from_function(
            coroutine=browser_navigate,
            name="browser_navigate",
            description="Open a URL in the CDP browser pool (or record it for snapshot/fetch).",
            args_schema=NavArgs,
        ),
        StructuredTool.from_function(
            coroutine=browser_snapshot,
            name="browser_snapshot",
            description="Read the current page as text (fetch). Call after browser_navigate.",
        ),
        StructuredTool.from_function(
            coroutine=browser_click,
            name="browser_click",
            description="Click an element on the CDP page. Ask the user to log in when blocked.",
            args_schema=ClickArgs,
        ),
    ]
