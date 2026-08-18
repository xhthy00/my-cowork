"""WeChat iLink Bot channel — ported from AionCore weixin plugin."""

from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Iterator

import httpx

from app.server.channels.plugins.weixin_media import (
    DEFAULT_CDN_BASE_URL,
    MEDIA_TYPE_FILE,
    WEIXIN_CDN_TIMEOUT,
    aes128_ecb_pkcs7,
    aes_key_for_send,
    aeskey_hex,
    md5_hex,
    random_aes_key,
    random_filekey,
)

DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
LOGIN_HTTP_TIMEOUT = 40.0
QR_POLL_INTERVAL = 2.0
QR_LOGIN_TIMEOUT = 300.0
WEIXIN_POLL_TIMEOUT = 35.0
WEIXIN_API_TIMEOUT = 15.0
WEIXIN_MAX_BACKOFF = 600
ITEM_TYPE_TEXT = 1
ITEM_TYPE_IMAGE = 2
ITEM_TYPE_VOICE = 3
ITEM_TYPE_FILE = 4
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HEX_ENT_RE = re.compile(r"&#x([0-9a-fA-F]+);")
_DEC_ENT_RE = re.compile(r"&#(\d+);")

OnMessage = Callable[[dict[str, Any]], None]
OnStatus = Callable[[str, str | None], None]


def credentials_from_env() -> dict[str, str]:
    return {
        "account_id": os.environ.get("WEIXIN_ACCOUNT_ID", "").strip(),
        "bot_token": os.environ.get("WEIXIN_BOT_TOKEN", "").strip(),
        "base_url": os.environ.get("WEIXIN_BASE_URL", "").strip() or DEFAULT_BASE_URL,
    }


def backoff_delay(consecutive_failures: int) -> float:
    n = max(0, int(consecutive_failures))
    secs = min(2 ** n if n < 64 else WEIXIN_MAX_BACKOFF, WEIXIN_MAX_BACKOFF)
    return float(secs)


def strip_html(text: str) -> str:
    result = text or ""
    while True:
        stripped = _HTML_TAG_RE.sub("", result)
        if stripped == result:
            break
        result = stripped
    result = (
        result.replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&apos;", "'")
        .replace("&nbsp;", " ")
    )
    result = _HEX_ENT_RE.sub(
        lambda m: chr(int(m.group(1), 16)) if 0 < int(m.group(1), 16) <= 0x10FFFF else m.group(0),
        result,
    )
    result = _DEC_ENT_RE.sub(
        lambda m: chr(int(m.group(1))) if 0 < int(m.group(1)) <= 0x10FFFF else m.group(0),
        result,
    )
    result = result.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return result.replace("<", "").replace(">", "")


def extract_content(items: list[dict[str, Any]] | None) -> tuple[str, str, bool]:
    text_parts: list[str] = []
    has_media = False
    for item in items or []:
        item_type = item.get("type")
        if item_type == ITEM_TYPE_TEXT:
            text = str((item.get("text_item") or {}).get("text") or "").strip()
            if text:
                text_parts.append(text)
        elif item_type == ITEM_TYPE_VOICE:
            text = str((item.get("voice_item") or {}).get("text") or "").strip()
            if text:
                text_parts.append(text)
        elif item_type in (ITEM_TYPE_IMAGE, ITEM_TYPE_FILE):
            has_media = True
    combined = "\n\n".join(text_parts)
    content_type = "command" if combined.startswith("/") else "text"
    return content_type, combined, has_media


def display_name_for(user_id: str) -> str:
    if len(user_id) > 6:
        return user_id[-6:]
    return user_id


class WeixinApi:
    """HTTP client for the WeChat iLink Bot API."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        bot_token: str = "",
        *,
        client: httpx.Client | None = None,
        wechat_uin: str | None = None,
        cdn_base_url: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        while self.base_url.endswith("/"):
            self.base_url = self.base_url.rstrip("/")
        self.bot_token = bot_token
        cdn = (
            cdn_base_url
            or os.environ.get("WEIXIN_CDN_BASE_URL", "").strip()
            or DEFAULT_CDN_BASE_URL
        )
        self.cdn_base_url = cdn.rstrip("/")
        self._client = client
        self._owns_client = client is None
        if wechat_uin is not None:
            self.wechat_uin = wechat_uin
        else:
            self.wechat_uin = base64.b64encode(os.urandom(4)).decode("ascii")

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def _http(self, timeout: float) -> httpx.Client:
        if self._client is not None:
            return self._client
        self._client = httpx.Client(timeout=timeout)
        return self._client

    def _parse_json_dict(self, endpoint: str, resp: httpx.Response) -> dict[str, Any]:
        raw = (resp.text or "").strip()
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{endpoint} parse failed: {raw[:300]}") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"{endpoint} parse failed")
        inner = data.get("data")
        if isinstance(inner, dict):
            return {**data, **inner}
        return data

    def _ilink_get(self, endpoint: str, params: dict[str, str], timeout: float = LOGIN_HTTP_TIMEOUT) -> dict[str, Any]:
        url = f"{self.base_url}/{endpoint}"
        resp = self._http(timeout).get(
            url,
            params=params,
            headers={"iLink-App-ClientVersion": "1"},
            timeout=timeout,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"{endpoint} HTTP {resp.status_code}: {resp.text}")
        data = resp.json()
        if not isinstance(data, dict):
            raise RuntimeError(f"{endpoint} parse failed")
        return data

    def _authenticated_post(
        self,
        endpoint: str,
        body: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{endpoint}"
        resp = self._http(timeout).post(
            url,
            json=body,
            headers={
                "Content-Type": "application/json",
                "AuthorizationType": "ilink_bot_token",
                "Authorization": f"Bearer {self.bot_token}",
                "X-WECHAT-UIN": self.wechat_uin,
            },
            timeout=timeout,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"{endpoint} HTTP {resp.status_code}: {resp.text}")
        return self._parse_json_dict(endpoint, resp)

    def get_bot_qrcode(self) -> dict[str, Any]:
        data = self._ilink_get("ilink/bot/get_bot_qrcode", {"bot_type": "3"})
        if data.get("qrcode"):
            return data
        wrapped = self._ilink_get("ilink/bot/get_bot_qrcode", {"bot_type": "3"})
        inner = wrapped.get("data")
        if isinstance(inner, dict):
            return inner
        raise RuntimeError("get_bot_qrcode returned no data")

    def get_qrcode_status(self, qrcode: str) -> dict[str, Any]:
        data = self._ilink_get("ilink/bot/get_qrcode_status", {"qrcode": qrcode})
        if data.get("status") is not None:
            return data
        wrapped = self._ilink_get("ilink/bot/get_qrcode_status", {"qrcode": qrcode})
        inner = wrapped.get("data")
        if isinstance(inner, dict):
            return inner
        raise RuntimeError("get_qrcode_status returned no data")

    def get_updates(self, buf: str) -> dict[str, Any]:
        timeout = WEIXIN_POLL_TIMEOUT + 10
        return self._authenticated_post(
            "ilink/bot/getupdates",
            {"get_updates_buf": buf, "base_info": {"channel_version": "my-cowork-0.1.0"}},
            timeout,
        )

    def send_message(self, to_user_id: str, text: str, context_token: str | None) -> None:
        self.send_items(
            to_user_id,
            [{"type": ITEM_TYPE_TEXT, "text_item": {"text": text}}],
            context_token,
        )

    def send_items(
        self,
        to_user_id: str,
        item_list: list[dict[str, Any]],
        context_token: str | None,
    ) -> None:
        msg: dict[str, Any] = {
            "from_user_id": "",
            "to_user_id": to_user_id,
            "client_id": str(uuid.uuid4()),
            "message_type": 2,
            "message_state": 2,
            "item_list": item_list,
        }
        if context_token:
            msg["context_token"] = context_token
        self._authenticated_post(
            "ilink/bot/sendmessage",
            {"msg": msg, "base_info": {"channel_version": "my-cowork-0.1.0"}},
            WEIXIN_API_TIMEOUT,
        )

    def get_upload_url(
        self,
        to_user_id: str,
        *,
        filekey: str,
        rawsize: int,
        rawfilemd5: str,
        filesize: int,
        aeskey_hex: str,
    ) -> dict[str, Any]:
        body = {
            "filekey": filekey,
            "media_type": MEDIA_TYPE_FILE,
            "to_user_id": to_user_id,
            "rawsize": rawsize,
            "rawfilemd5": rawfilemd5,
            "filesize": filesize,
            "no_need_thumb": True,
            "aeskey": aeskey_hex,
            "base_info": {"channel_version": "my-cowork-0.1.0"},
        }
        resp = self._authenticated_post(
            "ilink/bot/getuploadurl",
            body,
            WEIXIN_API_TIMEOUT,
        )
        if (resp.get("ret") or 0) != 0 or (resp.get("errcode") or 0) != 0:
            raise RuntimeError(f"getuploadurl failed: {resp}")
        if not (resp.get("upload_param") or resp.get("upload_full_url")):
            raise RuntimeError(f"getuploadurl returned no upload URL: {resp}")
        return resp

    def upload_cdn(
        self,
        ciphertext: bytes,
        *,
        filekey: str,
        upload_param: str = "",
        upload_full_url: str = "",
    ) -> str:
        full = (upload_full_url or "").strip()
        if full:
            resp = self._http(WEIXIN_CDN_TIMEOUT).post(
                full,
                content=ciphertext,
                headers={"Content-Type": "application/octet-stream"},
                timeout=WEIXIN_CDN_TIMEOUT,
            )
        else:
            url = f"{self.cdn_base_url}/upload"
            resp = self._http(WEIXIN_CDN_TIMEOUT).post(
                url,
                params={"encrypted_query_param": upload_param, "filekey": filekey},
                content=ciphertext,
                headers={"Content-Type": "application/octet-stream"},
                timeout=WEIXIN_CDN_TIMEOUT,
            )
        if resp.status_code != 200:
            err = resp.headers.get("x-error-message") or resp.text
            raise RuntimeError(f"cdn upload HTTP {resp.status_code}: {err}")
        param = str(resp.headers.get("x-encrypted-param") or "").strip()
        if not param:
            raise RuntimeError("cdn upload missing x-encrypted-param")
        return param

    def send_file(self, to_user_id: str, path: str, context_token: str | None) -> None:
        if not context_token:
            raise RuntimeError("missing context_token")
        file_path = Path(path)
        plaintext = file_path.read_bytes()
        rawsize = len(plaintext)
        key = random_aes_key()
        filekey = random_filekey()
        ciphertext = aes128_ecb_pkcs7(plaintext, key)
        digest = md5_hex(plaintext)
        resp = self.get_upload_url(
            to_user_id,
            filekey=filekey,
            rawsize=rawsize,
            rawfilemd5=digest,
            filesize=len(ciphertext),
            aeskey_hex=aeskey_hex(key),
        )
        download_param = self.upload_cdn(
            ciphertext,
            filekey=filekey,
            upload_param=str(resp.get("upload_param") or ""),
            upload_full_url=str(resp.get("upload_full_url") or ""),
        )
        self.send_items(
            to_user_id,
            [
                {
                    "type": ITEM_TYPE_FILE,
                    "file_item": {
                        "media": {
                            "encrypt_query_param": download_param,
                            "aes_key": aes_key_for_send(key),
                            "encrypt_type": 1,
                        },
                        "file_name": file_path.name,
                        "md5": digest,
                        "len": str(rawsize),
                    },
                }
            ],
            context_token,
        )


def sse_event_json(event: str, payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def login_flow(
    *,
    api: WeixinApi | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
    should_stop: Callable[[], bool] | None = None,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield (event_name, payload) for the QR login SSE stream."""
    owns = api is None
    client = api or WeixinApi(DEFAULT_BASE_URL, "")
    try:
        try:
            qr_data = client.get_bot_qrcode()
        except Exception as exc:  # noqa: BLE001
            yield "error", {"message": f"Failed to fetch QR code: {exc}"}
            return
        ticket = str(qr_data.get("qrcode") or "")
        if not ticket:
            yield "error", {"message": "QR code response missing ticket"}
            return
        qr_content = str(qr_data.get("qrcode_img_content") or "")
        if not qr_content:
            yield "error", {"message": "QR code response missing qrcode_img_content"}
            return
        yield "qr", {"qrcodeData": qr_content}

        deadline = now() + QR_LOGIN_TIMEOUT
        scanned_sent = False
        while True:
            if should_stop and should_stop():
                return
            if now() >= deadline:
                yield "error", {"message": "QR code login timeout"}
                return
            sleep(QR_POLL_INTERVAL)
            if should_stop and should_stop():
                return
            try:
                status = client.get_qrcode_status(ticket)
            except Exception as exc:  # noqa: BLE001
                err_str = str(exc)
                if "timed out" in err_str.lower() or "Timeout" in err_str:
                    continue
                yield "error", {"message": f"Status poll failed: {exc}"}
                return
            state = str(status.get("status") or "wait")
            if state == "scaned" and not scanned_sent:
                scanned_sent = True
                yield "scanned", {}
            elif state == "confirmed":
                yield "done", {
                    "accountId": str(status.get("ilink_bot_id") or ""),
                    "botToken": str(status.get("bot_token") or ""),
                    "baseUrl": str(status.get("baseurl") or DEFAULT_BASE_URL),
                }
                return
            elif state == "expired":
                yield "error", {"message": "QR code expired"}
                return
    finally:
        if owns:
            client.close()


class WeixinRuntime:
    """Long-poll getupdates on a daemon thread."""

    def __init__(self, store: Any | None = None, *, api: WeixinApi | None = None) -> None:
        self._store = store
        self._api = api
        self._owns_api = False
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._context: dict[str, str] = {}
        self.running = False

    def start(
        self,
        *,
        bot_token: str,
        account_id: str,
        base_url: str = DEFAULT_BASE_URL,
        on_message: OnMessage,
        on_status: OnStatus | None = None,
    ) -> None:
        self.stop()
        self._stop.clear()
        if self._api is None:
            self._api = WeixinApi(
                base_url or DEFAULT_BASE_URL,
                bot_token,
                cdn_base_url=os.environ.get("WEIXIN_CDN_BASE_URL", "").strip() or None,
            )
            self._owns_api = True
        else:
            self._api.bot_token = bot_token
            self._api.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        buf = ""
        if self._store is not None:
            cfg = self._store.get_plugin_config("weixin")
            buf = str(cfg.get("get_updates_buf") or "")
        self.running = True
        if on_status:
            on_status("connected", None)

        def loop() -> None:
            self._poll_loop(buf, on_message, on_status)

        self._thread = threading.Thread(target=loop, name="weixin-ilink", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5)
        self._thread = None
        self.running = False
        self._context.clear()
        if self._owns_api and self._api is not None:
            self._api.close()
            self._api = None
            self._owns_api = False

    def send_text(self, chat_id: str, text: str) -> None:
        api = self._api
        if api is None:
            raise RuntimeError("Plugin not initialized")
        token = self._get_context(chat_id)
        api.send_message(chat_id, text, token)

    def send_file(self, chat_id: str, path: str) -> None:
        api = self._api
        if api is None:
            raise RuntimeError("Plugin not initialized")
        token = self._get_context(chat_id)
        if not token:
            raise RuntimeError("missing context_token")
        api.send_file(chat_id, path, token)

    def _get_context(self, user_id: str) -> str | None:
        if self._store is not None:
            stored = self._store.get_context_token("weixin", user_id)
            if stored:
                return stored
        return self._context.get(user_id)

    def _set_context(self, user_id: str, token: str) -> None:
        self._context[user_id] = token
        if self._store is not None:
            self._store.set_context_token("weixin", user_id, token)

    def _save_buf(self, buf: str) -> None:
        if self._store is None:
            return
        cfg = self._store.get_plugin_config("weixin")
        cfg["get_updates_buf"] = buf
        self._store.set_plugin_config("weixin", cfg)

    def _poll_loop(
        self,
        buf: str,
        on_message: OnMessage,
        on_status: OnStatus | None,
    ) -> None:
        api = self._api
        if api is None:
            return
        consecutive = 0
        while not self._stop.is_set():
            try:
                resp = api.get_updates(buf)
            except Exception as exc:  # noqa: BLE001
                consecutive += 1
                if consecutive == 1:
                    print(f"WeChat poll started failing: {exc}")
                if consecutive >= 3 and on_status:
                    on_status("error", str(exc))
                self._stop.wait(backoff_delay(consecutive))
                continue
            ret = resp.get("ret") or 0
            errcode = resp.get("errcode") or 0
            if ret != 0 or errcode != 0:
                consecutive += 1
                if consecutive == 1:
                    print(f"getupdates API error ret={ret} errcode={errcode}")
                if consecutive >= 3 and on_status:
                    on_status("error", f"getupdates ret={ret} errcode={errcode}")
                self._stop.wait(backoff_delay(consecutive))
                continue
            if consecutive:
                print(f"WeChat poll recovered after {consecutive} failures")
            consecutive = 0
            new_buf = resp.get("get_updates_buf")
            if isinstance(new_buf, str):
                buf = new_buf
                self._save_buf(buf)
            for msg in resp.get("msgs") or []:
                if not isinstance(msg, dict):
                    continue
                self._handle_message(msg, on_message)

    def _handle_message(self, msg: dict[str, Any], on_message: OnMessage) -> None:
        from_user_id = str(msg.get("from_user_id") or "")
        if not from_user_id:
            return
        ctx = str(msg.get("context_token") or "")
        if ctx:
            self._set_context(from_user_id, ctx)
        _, text, _has_media = extract_content(msg.get("item_list") or [])
        if not text:
            return
        on_message(
            {
                "user_id": from_user_id,
                "chat_id": from_user_id,
                "text": text,
                "display_name": display_name_for(from_user_id),
                "event_id": str(msg.get("msg_id") or ""),
            }
        )
