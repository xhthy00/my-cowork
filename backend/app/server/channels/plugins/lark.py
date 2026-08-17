"""Feishu long-connection adapter (lark-oapi WebSocket)."""

from __future__ import annotations

import asyncio
import os
import threading
from typing import Any, Callable

import requests

TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"

OnMessage = Callable[[dict[str, Any]], None]
OnStatus = Callable[[str, str | None], None]
StopFn = Callable[[], None]


def test_credentials(
    app_id: str,
    app_secret: str,
    *,
    post: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Exchange App ID/Secret for a tenant token — AionUi testPlugin equivalent."""
    if not app_id.strip() or not app_secret.strip():
        return {"success": False, "error": "请输入 App ID 和 App Secret"}
    http_post = post or requests.post
    try:
        resp = http_post(
            TOKEN_URL,
            json={"app_id": app_id.strip(), "app_secret": app_secret.strip()},
            timeout=10,
        )
        data = resp.json() if resp.content else {}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": str(exc)}
    if data.get("code") != 0 or not data.get("tenant_access_token"):
        return {"success": False, "error": str(data.get("msg") or "连接失败")}
    return {"success": True, "bot_username": "lark"}


def _parse_p2_event(event: Any) -> dict[str, Any]:
    """Normalize P2ImMessageReceiveV1 (or similar) into a dict ingest payload."""
    if isinstance(event, dict):
        header = event.get("header")
        ev = event.get("event") or event
        message = ev.get("message") if isinstance(ev, dict) else None
        sender = ev.get("sender") if isinstance(ev, dict) else None
    else:
        header = getattr(event, "header", None)
        ev = getattr(event, "event", None) or event
        message = getattr(ev, "message", None)
        sender = getattr(ev, "sender", None)

    def _g(obj: Any, *names: str, default: Any = "") -> Any:
        if obj is None:
            return default
        if isinstance(obj, dict):
            cur: Any = obj
            for n in names:
                if not isinstance(cur, dict):
                    return default
                cur = cur.get(n)
            return cur if cur is not None else default
        cur = obj
        for n in names:
            cur = getattr(cur, n, None)
            if cur is None:
                return default
        return cur

    content = _g(message, "content")
    text = ""
    if isinstance(content, dict):
        text = str(content.get("text") or "")
    elif isinstance(content, str):
        import json

        try:
            parsed = json.loads(content)
            text = str(parsed.get("text") or content)
        except json.JSONDecodeError:
            text = content
    chat_id = str(_g(message, "chat_id") or "")
    user_id = str(
        _g(sender, "sender_id", "open_id")
        or _g(sender, "sender_id", "user_id")
        or chat_id
    )
    event_id = str(_g(header, "event_id") or _g(message, "message_id") or "")
    return {
        "text": text.strip(),
        "chat_id": chat_id,
        "user_id": user_id,
        "display_name": user_id,
        "event_id": event_id,
    }


class LarkWsRuntime:
    """Owns the blocking lark_oapi.ws.Client on a daemon thread."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._client: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.running = False

    def start(
        self,
        *,
        app_id: str,
        app_secret: str,
        encrypt_key: str = "",
        verification_token: str = "",
        on_message: OnMessage,
        on_status: OnStatus | None = None,
    ) -> None:
        self.stop()
        ready = threading.Event()
        error: list[BaseException] = []

        def _run() -> None:
            import lark_oapi.ws.client as ws_mod
            from lark_oapi.event.dispatcher_handler import EventDispatcherHandler

            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                ws_mod.loop = loop
                self._loop = loop

                def _handler(event: Any) -> None:
                    try:
                        on_message(_parse_p2_event(event))
                    except Exception as exc:  # noqa: BLE001
                        print(f"lark ws handler failed: {exc}")

                handler = (
                    EventDispatcherHandler.builder(encrypt_key or "", verification_token or "")
                    .register_p2_im_message_receive_v1(_handler)
                    .build()
                )
                client = ws_mod.Client(
                    app_id,
                    app_secret,
                    event_handler=handler,
                    auto_reconnect=True,
                )
                if on_status:
                    client.on_reconnecting = lambda: on_status("connecting", None)
                    client.on_reconnected = lambda: on_status("connected", None)
                self._client = client
                self.running = True
                if on_status:
                    on_status("connecting", None)
            except Exception as exc:  # noqa: BLE001
                error.append(exc)
                self.running = False
                if on_status:
                    on_status("error", str(exc))
                return
            finally:
                ready.set()
            try:
                client.start()
            except Exception as exc:  # noqa: BLE001
                error.append(exc)
                self.running = False
                if on_status:
                    on_status("error", str(exc))

        self._thread = threading.Thread(target=_run, name="lark-ws", daemon=True)
        self._thread.start()
        ready.wait(timeout=8)
        if error:
            raise error[0]
        if on_status and self.running:
            on_status("connected", None)

    def stop(self) -> None:
        client = self._client
        loop = self._loop
        self.running = False
        self._client = None
        if client is not None and loop is not None and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(client._disconnect(), loop)  # noqa: SLF001
            except Exception:  # noqa: BLE001
                pass
        self._loop = None
        self._thread = None


def credentials_from_env() -> dict[str, str]:
    return {
        "app_id": os.environ.get("LARK_APP_ID") or "",
        "app_secret": os.environ.get("LARK_APP_SECRET") or os.environ.get("LARK_SECRET") or "",
        "encrypt_key": os.environ.get("LARK_ENCRYPT_KEY") or "",
        "verification_token": os.environ.get("LARK_VERIFY_TOKEN") or "",
    }
