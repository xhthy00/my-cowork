"""Playwright browser tools adapted from OpenWorker's browser_automation.py.

OpenWorker is MIT licensed. Copyright (c) 2024 Andrew Ng.
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is furnished
to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import os
import re
import socket
import sys
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.guardrails.approval import ConfirmHub
from app.sandbox.path_guard import PathGuard, PathGuardError, resolve_tool_path, resolve_write_path
from app.workspace.overlay import maybe_record_write

_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_SNAPSHOT_JS = """() => {
  const visible = (el) => {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.visibility !== 'hidden' && style.display !== 'none'
      && rect.width > 0 && rect.height > 0;
  };
  const labelFor = (el) => {
    if (el.labels && el.labels.length)
      return Array.from(el.labels).map(l => l.innerText.trim()).filter(Boolean).join(' ');
    const id = el.getAttribute('id');
    if (id) {
      const label = document.querySelector('label[for="' + CSS.escape(id) + '"]');
      if (label) return label.innerText.trim();
    }
    return '';
  };
  const describe = (el, i) => ({
    index: i, tag: el.tagName.toLowerCase(), type: el.getAttribute('type') || '',
    id: el.getAttribute('id') || '', name: el.getAttribute('name') || '',
    role: el.getAttribute('role') || '', aria: el.getAttribute('aria-label') || '',
    label: labelFor(el), placeholder: el.getAttribute('placeholder') || '',
    text: (el.innerText || el.value || '').trim().slice(0, 200),
    href: el.getAttribute('href') || '',
    selectorHint: el.getAttribute('id') ? '#' + CSS.escape(el.getAttribute('id'))
      : (el.getAttribute('name') ? '[name="' + el.getAttribute('name') + '"]' : '')
  });
  return {
    title: document.title, url: location.href,
    text: document.body ? document.body.innerText : '',
    controls: Array.from(document.querySelectorAll(
      'a,button,input,textarea,select,[role="button"],[contenteditable="true"]'
    )).filter(visible).slice(0, 120).map(describe)
  };
}"""


def _check_url(url: str) -> str | None:
    """Reject non-public targets before navigation, following OpenWorker's guard."""
    try:
        parts = urlsplit(url)
        host, port = parts.hostname, parts.port
    except ValueError as exc:
        return f"invalid URL: {exc}"
    if parts.scheme not in {"http", "https"} or not host:
        return "url must start with http:// or https:// and have a host"
    if parts.username or parts.password:
        return "URL credentials are not allowed"
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(
                host, port or (443 if parts.scheme == "https" else 80),
                proto=socket.IPPROTO_TCP,
            )
            addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
        except OSError as exc:
            return f"could not resolve {host}: {exc}"
    if not addresses:
        return f"could not resolve {host}"
    for address in addresses:
        if address.version == 6 and address.ipv4_mapped:
            address = address.ipv4_mapped
        if not address.is_global or (address.version == 4 and address in _CGNAT):
            return f"refusing to open {host} ({address}): non-public address"
    return None


def _snapshot(page: Any, max_chars: int = 20_000) -> dict[str, Any]:
    if page.url.startswith(("http://", "https://")):
        blocked = _check_url(page.url)
        if blocked:
            return {"error": blocked}
    data = page.evaluate(_SNAPSHOT_JS)
    text = re.sub(r"\n{3,}", "\n\n", str(data.get("text") or ""))
    cap = max(1, min(int(max_chars or 20_000), 100_000))
    return {
        "title": data.get("title"), "url": data.get("url"), "text": text[:cap],
        "truncated": len(text) > cap, "controls": data.get("controls") or [],
    }


def _target_locator(page: Any, target: str) -> Any:
    target = target.strip()
    if target.startswith("text="):
        return page.get_by_text(target[5:], exact=False).first
    if target.startswith("role="):
        role, _, name = target[5:].partition(":")
        return page.get_by_role(role.strip(), name=name.strip() or None).first
    return page.locator(target).first


class _BrowserController:
    """Keep the synchronous Playwright page on one dedicated worker thread."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="my-cowork-browser")
        self._lock = threading.RLock()
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    def _close(self) -> None:
        for obj in (self._context, self._browser, self._playwright):
            if obj is not None:
                try:
                    obj.close() if hasattr(obj, "close") else obj.stop()
                except Exception:
                    pass
        self._page = self._context = self._browser = self._playwright = None

    def _page_or_error(self) -> tuple[Any | None, dict[str, Any] | None]:
        if self._page is not None:
            return self._page, None
        try:
            if getattr(sys, "frozen", False) and not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
                # Electron places Chromium beside the packaged Python backend.
                binary_dir = Path(sys.executable).resolve().parent
                for candidate in (
                    binary_dir / "playwright-browsers",
                    binary_dir.parent / "playwright-browsers",
                ):
                    if candidate.is_dir():
                        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(candidate)
                        break
            from playwright.sync_api import sync_playwright

            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=False)
            self._context = self._browser.new_context(viewport={"width": 1280, "height": 900})
            self._page = self._context.new_page()
            return self._page, None
        except Exception as exc:
            self._close()
            return None, {
                "error": "Playwright Chromium is unavailable. Install Playwright and run python -m playwright install chromium.",
                "details": str(exc),
            }

    def call(self, action: str, fn: Callable[[Any], dict[str, Any]]) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            with self._lock:
                page, error = self._page_or_error()
                if error:
                    return error
                try:
                    if action != "navigate" and page.url.startswith(("http://", "https://")):
                        blocked = _check_url(page.url)
                        if blocked:
                            page.goto("about:blank")
                            return {"error": blocked}
                    return fn(page)
                except Exception as exc:
                    return {"error": f"browser {action} failed: {exc}"}
        return self._executor.submit(run).result()

    def close(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            with self._lock:
                self._close()
                return {"ok": True}
        return self._executor.submit(run).result()

    def state(self) -> dict[str, Any]:
        def run() -> dict[str, Any]:
            with self._lock:
                if self._page is None:
                    return {"open": False, "status": "closed", "url": "", "title": ""}
                try:
                    return {"open": True, "status": "open", "url": self._page.url,
                            "title": self._page.title()}
                except Exception as exc:
                    return {"open": True, "status": "error", "error": str(exc)}
        return self._executor.submit(run).result()

    def screenshot_data_url(self) -> dict[str, Any]:
        """Preview the agent's existing page without opening a second browser."""
        def run() -> dict[str, Any]:
            with self._lock:
                if self._page is None:
                    return {"open": False, "image": ""}
                try:
                    if self._page.url.startswith(("http://", "https://")):
                        blocked = _check_url(self._page.url)
                        if blocked:
                            return {"open": True, "error": blocked}
                    png = self._page.screenshot(type="png")
                    return {"open": True, "image": "data:image/png;base64," + base64.b64encode(png).decode("ascii")}
                except Exception as exc:
                    return {"open": True, "error": str(exc)}
        return self._executor.submit(run).result()


_BROWSER = _BrowserController()


class NavigateArgs(BaseModel):
    url: str = Field(description="Public http(s) URL to open")
    wait_until: str = Field(default="domcontentloaded", description="Playwright wait state")


class SnapshotArgs(BaseModel):
    max_chars: int = Field(default=20_000, description="Maximum page text characters")


class TargetArgs(BaseModel):
    target: str = Field(description="CSS selector, text=label, or role=button:Name")


class TypeArgs(TargetArgs):
    text: str = Field(description="Text to enter")
    clear: bool = Field(default=True, description="Replace current value when true")


class SelectArgs(TargetArgs):
    value: str = Field(description="Option value or visible label")


class UploadArgs(TargetArgs):
    path: str = Field(description="Local file path inside an allowed workspace")


class WaitArgs(BaseModel):
    milliseconds: int = Field(default=1000, description="Wait duration or target timeout")
    target: str = Field(default="", description="Optional element to wait for")


class ScreenshotArgs(BaseModel):
    path: str = Field(default="", description="Optional output path in an allowed workspace")


async def _run(action: str, fn: Callable[[Any], dict[str, Any]]) -> str:
    return json.dumps(await asyncio.to_thread(_BROWSER.call, action, fn), ensure_ascii=False)


async def _approve(hub: ConfirmHub | None, name: str, args: dict[str, Any]) -> bool:
    if hub is None:
        return True
    if "url" not in args and hasattr(_BROWSER, "state"):
        state = await asyncio.to_thread(_BROWSER.state)
        if state.get("url") and state["url"] != "about:blank":
            args = {"url": state["url"], **args}
    return await hub.request(f"{name}:{uuid.uuid4().hex}", name, args)


def make_browser_tools(
    guard: PathGuard | None = None,
    confirm_hub: ConfirmHub | None = None,
) -> list[StructuredTool]:
    """Expose the OpenWorker browser action set as LangChain tools."""

    async def browser_navigate(url: str, wait_until: str = "domcontentloaded") -> str:
        blocked = await asyncio.to_thread(_check_url, url)
        if blocked:
            return json.dumps({"error": blocked}, ensure_ascii=False)
        if wait_until not in {"load", "domcontentloaded", "networkidle", "commit"}:
            return json.dumps({"error": "invalid wait_until"})
        if not await _approve(confirm_hub, "browser_navigate", {"url": url}):
            return json.dumps({"error": "user rejected browser navigation"})

        def open_url(page: Any) -> dict[str, Any]:
            page.goto(url, wait_until=wait_until, timeout=30_000)
            blocked_landing = _check_url(page.url)
            if blocked_landing:
                landed = page.url
                page.goto("about:blank")
                return {"error": f"redirected to {landed}: {blocked_landing}"}
            return {"ok": True, "url": page.url}
        return await _run("navigate", open_url)

    async def browser_snapshot(max_chars: int = 20_000) -> str:
        return await _run("snapshot", lambda page: _snapshot(page, max_chars))

    async def browser_click(target: str) -> str:
        if not await _approve(confirm_hub, "browser_click", {"target": target}):
            return json.dumps({"error": "user rejected browser click"})
        def click(page: Any) -> dict[str, Any]:
            _target_locator(page, target).click(timeout=10_000)
            return {"ok": True, "url": page.url}
        return await _run("click", click)

    async def browser_type(target: str, text: str, clear: bool = True) -> str:
        if not await _approve(confirm_hub, "browser_type", {"target": target, "text_length": len(text)}):
            return json.dumps({"error": "user rejected browser typing"})
        def type_text(page: Any) -> dict[str, Any]:
            loc = _target_locator(page, target)
            if clear:
                loc.fill(text, timeout=10_000)
            else:
                loc.type(text, timeout=10_000)
            return {"ok": True, "url": page.url}
        return await _run("type", type_text)

    async def browser_select(target: str, value: str) -> str:
        if not await _approve(confirm_hub, "browser_select", {"target": target, "value": value}):
            return json.dumps({"error": "user rejected browser selection"})
        def select(page: Any) -> dict[str, Any]:
            _target_locator(page, target).select_option(value, timeout=10_000)
            return {"ok": True, "url": page.url}
        return await _run("select", select)

    async def browser_upload_file(target: str, path: str) -> str:
        try:
            source = resolve_tool_path(path)
            if guard is None:
                raise PathGuardError("No browser upload whitelist configured")
            guard.check_path(str(source))
            if not source.is_file():
                return json.dumps({"error": f"file not found: {source}"})
        except PathGuardError as exc:
            return json.dumps({"error": str(exc)})
        if not await _approve(confirm_hub, "browser_upload_file",
                              {"target": target, "path": str(source)}):
            return json.dumps({"error": "user rejected browser upload"})
        def upload(page: Any) -> dict[str, Any]:
            _target_locator(page, target).set_input_files(str(source), timeout=10_000)
            return {"ok": True, "path": str(source), "url": page.url}
        return await _run("upload", upload)

    async def browser_wait(milliseconds: int = 1000, target: str = "") -> str:
        duration = max(1, min(int(milliseconds or 1000), 30_000))
        def wait(page: Any) -> dict[str, Any]:
            if target:
                _target_locator(page, target).wait_for(timeout=duration)
            else:
                page.wait_for_timeout(duration)
            return {"ok": True, "url": page.url}
        return await _run("wait", wait)

    async def browser_screenshot(path: str = "") -> str:
        if path:
            try:
                output = resolve_write_path(path)
                if guard is None:
                    raise PathGuardError("No browser screenshot whitelist configured")
                guard.check_path(str(output))
            except PathGuardError as exc:
                return json.dumps({"error": str(exc)})
        else:
            output = Path(tempfile.gettempdir()) / f"my-cowork-browser-{uuid.uuid4().hex}.png"
        if not await _approve(confirm_hub, "browser_screenshot", {"path": str(output)}):
            return json.dumps({"error": "user rejected browser screenshot"})
        def screenshot(page: Any) -> dict[str, Any]:
            output.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output), full_page=True)
            return {"ok": True, "path": str(output), "url": page.url}
        result = await _run("screenshot", screenshot)
        if path and json.loads(result).get("ok"):
            maybe_record_write(output)
        return result

    async def browser_close() -> str:
        if not await _approve(confirm_hub, "browser_close", {}):
            return json.dumps({"error": "user rejected browser close"})
        return json.dumps(await asyncio.to_thread(_BROWSER.close), ensure_ascii=False)

    async def browser_state() -> str:
        return json.dumps(await asyncio.to_thread(_BROWSER.state), ensure_ascii=False)

    def tool(name: str, description: str, coroutine: Callable[..., Any],
             args_schema: type[BaseModel] | None = None) -> StructuredTool:
        return StructuredTool.from_function(
            coroutine=coroutine, name=name, description=description, args_schema=args_schema,
        )

    return [
        tool("browser_navigate", "Open a public URL in the local Playwright browser.", browser_navigate, NavigateArgs),
        tool("browser_snapshot", "Read rendered page text and visible controls with selector hints.", browser_snapshot, SnapshotArgs),
        tool("browser_click", "Click by CSS, text=label, or role=button:Name.", browser_click, TargetArgs),
        tool("browser_type", "Fill or type into an input, textarea, or editable element.", browser_type, TypeArgs),
        tool("browser_select", "Select a dropdown option by value or visible label.", browser_select, SelectArgs),
        tool("browser_upload_file", "Upload an allowed local file through a file input.", browser_upload_file, UploadArgs),
        tool("browser_wait", "Wait for an element or a short duration.", browser_wait, WaitArgs),
        tool("browser_screenshot", "Save a full-page screenshot and return its path.", browser_screenshot, ScreenshotArgs),
        tool("browser_close", "Close the current browser session.", browser_close),
        tool("browser_state", "Return the current browser session status and URL.", browser_state),
    ]
