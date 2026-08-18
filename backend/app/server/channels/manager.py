"""Channel plugin registry, pairing, and inbound message handling."""

from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

from app.graphs.routing import extract_claimed_office_paths, wants_document
from app.guardrails.policy import skill_usable_via_remote
from app.orchestrator.task_manager import TaskRequest
from app.runtime.context import looks_like_plan_only, looks_like_workspace_dump
from app.server.channels.bus import ChannelBus
from app.server.channels.plugins import lark as lark_plugin
from app.server.channels.plugins import weixin as weixin_plugin
from app.server.channels.store import ChannelStore
from app.skills import find_skill
from app.tools.builtin.lark import send_message as lark_send

REMOTE_DENIED_MSG = "此技能需桌面客户端运行，请打开 app 后再尝试"
CHANNEL_LABELS = {"lark": "飞书", "weixin": "微信"}
PAIRING_HINT = (
    "👋 欢迎使用办公助手！\n\n"
    "🔑 配对码: {code}\n"
    "请在客户端「设置 → 远程连接 → {channel}」中批准此配对。\n"
    "配对码 10 分钟内有效。"
)
PAIRING_OK = "✅ 配对成功！现在可以开始对话了"
WEIXIN_WORKING = "收到，正在处理…"
WEIXIN_PROGRESS_MIN_SECS = 5.0
WEIXIN_FILE_MAX_BYTES = 20 * 1024 * 1024
WEIXIN_FILE_MAX_COUNT = 5
WEIXIN_FILE_TOO_LARGE = "文件过大，已保存在电脑：{path}"
WEIXIN_FILE_MISSING = "未能发送附件，文件不存在：{path}"
WEIXIN_FILE_SEND_FAILED = "未能发送附件（{reason}），已保存在电脑：{path}"
WEIXIN_FILE_TOO_MANY = "附件数量已达上限，其余文件已保存在电脑：{path}"
EVENT_TTL_MS = 5 * 60 * 1000
LARK_REPLY_MAX = 8000
_THINK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_SKILL_MENTION_RE = re.compile(
    r"(?:skill|技能)[\s:：]*([a-zA-Z0-9_-]+)|用\s*([a-zA-Z0-9_-]+)\s*skill",
    re.IGNORECASE,
)

BUILTIN: list[dict[str, Any]] = [
    {
        "plugin_id": "telegram",
        "type": "telegram",
        "name": "Telegram",
        "coming_soon": True,
    },
    {
        "plugin_id": "lark",
        "type": "lark",
        "name": "Lark / 飞书",
        "coming_soon": False,
    },
    {
        "plugin_id": "dingtalk",
        "type": "dingtalk",
        "name": "钉钉",
        "coming_soon": True,
    },
    {
        "plugin_id": "weixin",
        "type": "weixin",
        "name": "微信 ClawBot",
        "coming_soon": False,
    },
]


def _strip_think(text: str) -> str:
    return _THINK_RE.sub("", text or "").strip()


def existing_claimed_office_files(text: str) -> list[str]:
    """Absolute office paths listed in *text* that still exist on disk."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in extract_claimed_office_paths(text):
        path = Path(raw).expanduser()
        try:
            if not path.is_file():
                continue
            key = str(path.resolve())
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def weixin_progress_text(event: dict[str, Any]) -> str | None:
    """Human-readable WeChat progress from graph events (new messages, not edits)."""
    if event.get("type") != "todo_state":
        return None
    todos = event.get("todos") or []
    current = next(
        (t for t in todos if isinstance(t, dict) and t.get("status") == "in_progress"),
        None,
    )
    if not current:
        return None
    title = str(current.get("active_form") or current.get("content") or "").strip()
    if not title:
        return None
    if not title.startswith("正在"):
        return f"正在：{title}"
    return title


CONFIRM_TIMEOUT_HINT = (
    "此操作需要在电脑上确认（例如运行命令）。"
    "请打开 MyCowork 桌面端批准，或改在桌面里提问。"
)
MISSING_DOC_HINT = (
    "未能在电脑上写出文档文件。"
    "请把完整正文再发一次，或改在 MyCowork 桌面端生成。"
)


def _is_missing_doc_error(error: str) -> bool:
    text = error or ""
    lower = text.lower()
    return (
        "未生成文档" in text
        or "未生成 pptx" in lower
        or "写入确认" in text
        or "磁盘上不存在" in text
    )


def _friendly_channel_error(error: str) -> str:
    lower = (error or "").lower()
    if "confirmation request" in lower and "timed out" in lower:
        return CONFIRM_TIMEOUT_HINT
    if _is_missing_doc_error(error):
        return MISSING_DOC_HINT
    return f"任务失败：{error}"


def compose_channel_reply(
    *,
    summary: str = "",
    streamed: str = "",
    error: str = "",
    platform: str = "lark",
) -> str:
    """Pick the user-facing channel reply from graph events."""
    body = _strip_think(summary) or _strip_think(streamed)
    if error:
        if (
            _is_missing_doc_error(error)
            and body
            and not looks_like_workspace_dump(body)
            and not extract_claimed_office_paths(body)
        ):
            text = body
        else:
            text = _friendly_channel_error(error)
    else:
        text = body or "任务已完成。"
    if platform == "weixin":
        return weixin_plugin.strip_html(text)
    if len(text) > LARK_REPLY_MAX:
        return text[: LARK_REPLY_MAX - 1] + "…"
    return text


class ChannelError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class ChannelManager:
    def __init__(
        self,
        store: ChannelStore,
        task_manager: Any = None,
        *,
        send: Callable[..., Any] | None = None,
        test_lark: Callable[..., dict[str, Any]] | None = None,
        start_lark: Callable[..., None] | None = None,
        stop_lark: Callable[[], None] | None = None,
        start_weixin: Callable[..., None] | None = None,
        stop_weixin: Callable[[], None] | None = None,
        bus: ChannelBus | None = None,
    ) -> None:
        self.store = store
        self.task_manager = task_manager
        self._send = send or lark_send.send
        self._test_lark = test_lark or lark_plugin.test_credentials
        self._start_lark = start_lark
        self._stop_lark = stop_lark
        self._start_weixin = start_weixin
        self._stop_weixin = stop_weixin
        self.bus = bus or ChannelBus()
        self._runtime = lark_plugin.LarkWsRuntime()
        self._weixin_runtime = weixin_plugin.WeixinRuntime(store)
        self._runtimes: dict[str, Any] = {}
        self._creds: dict[str, dict[str, Any]] = {}
        self._events: dict[str, int] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._seed_plugins()

    def _seed_plugins(self) -> None:
        for meta in BUILTIN:
            existing = self.store.get_plugin(meta["plugin_id"])
            if existing is None:
                self.store.upsert_plugin(
                    meta["plugin_id"],
                    type=meta["type"],
                    name=meta["name"],
                    status="inactive" if not meta["coming_soon"] else "coming_soon",
                )

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self.bus.bind_loop(loop)

    def _schedule(self, coro: Any) -> None:
        loop = self._loop
        if loop is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, loop)
        else:
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(coro)
            else:
                running.create_task(coro)

    async def _send_text(self, chat_id: str, text: str, platform: str = "lark") -> None:
        if not chat_id:
            return
        if platform == "weixin":
            text = weixin_plugin.strip_html(text)
            runtime = self._runtimes.get("weixin")
            if runtime is not None:
                try:
                    await asyncio.to_thread(runtime.send_text, chat_id, text)
                except Exception as exc:  # noqa: BLE001
                    print(f"channel send failed: {exc}")
                return
        try:
            await self._send(chat_id, text)
        except Exception as exc:  # noqa: BLE001
            print(f"channel send failed: {exc}")

    async def _send_weixin_files(self, chat_id: str, artifacts: list[str]) -> None:
        runtime = self._runtimes.get("weixin")
        sent = 0
        for path in artifacts:
            if sent >= WEIXIN_FILE_MAX_COUNT:
                await self._send_text(
                    chat_id,
                    WEIXIN_FILE_TOO_MANY.format(path=path),
                    platform="weixin",
                )
                continue
            file_path = Path(path)
            if not file_path.is_file():
                await self._send_text(
                    chat_id,
                    WEIXIN_FILE_MISSING.format(path=path),
                    platform="weixin",
                )
                continue
            try:
                size = file_path.stat().st_size
            except OSError:
                await self._send_text(
                    chat_id,
                    WEIXIN_FILE_MISSING.format(path=path),
                    platform="weixin",
                )
                continue
            if size > WEIXIN_FILE_MAX_BYTES:
                await self._send_text(
                    chat_id,
                    WEIXIN_FILE_TOO_LARGE.format(path=path),
                    platform="weixin",
                )
                continue
            if runtime is None:
                continue
            try:
                await asyncio.to_thread(runtime.send_file, chat_id, path)
                sent += 1
            except Exception as exc:  # noqa: BLE001
                print(f"channel send file failed: {exc}")
                reason = str(exc).replace("\n", " ").strip()[:80] or "未知错误"
                await self._send_text(
                    chat_id,
                    WEIXIN_FILE_SEND_FAILED.format(path=path, reason=reason),
                    platform="weixin",
                )

    def _emit_status(self, plugin_id: str) -> None:
        plugins = {p["plugin_id"]: p for p in self.list_plugins()}
        status = plugins.get(plugin_id)
        if status:
            self.bus.emit(
                "channel.plugin-status-changed",
                {"plugin_id": plugin_id, "status": status},
            )

    def list_plugins(self) -> list[dict[str, Any]]:
        rows = {r["plugin_id"]: r for r in self.store.list_plugins()}
        out: list[dict[str, Any]] = []
        for meta in BUILTIN:
            row = rows.get(meta["plugin_id"], {})
            creds = self._creds.get(meta["plugin_id"]) or {}
            if meta["plugin_id"] == "lark":
                has_env = bool(os.environ.get("LARK_APP_ID") and os.environ.get("LARK_APP_SECRET"))
                has_token = bool(row.get("has_token") or creds.get("app_id") or has_env)
                bot_username = "lark" if has_token else None
            elif meta["plugin_id"] == "weixin":
                env_creds = weixin_plugin.credentials_from_env()
                has_env = bool(env_creds.get("bot_token") and env_creds.get("account_id"))
                has_token = bool(
                    row.get("has_token")
                    or (creds.get("bot_token") and creds.get("account_id"))
                    or has_env
                )
                bot_username = str(creds.get("account_id") or "") or None
            else:
                has_token = bool(row.get("has_token"))
                bot_username = None
            coming = bool(meta["coming_soon"])
            out.append(
                {
                    "plugin_id": meta["plugin_id"],
                    "id": meta["plugin_id"],
                    "type": meta["type"],
                    "name": meta["name"],
                    "enabled": bool(row.get("enabled")) and not coming,
                    "connected": bool(row.get("connected")) and not coming,
                    "has_token": has_token and not coming,
                    "status": "coming_soon"
                    if coming
                    else (row.get("status") or "inactive"),
                    "last_connected": row.get("last_connected"),
                    "active_users": len(self.store.list_users(meta["type"])),
                    "bot_username": bot_username,
                    "is_extension": False,
                    "coming_soon": coming,
                    "error": None if (row.get("status") != "error") else (row.get("status")),
                }
            )
        return out

    def test_plugin(
        self,
        plugin_id: str,
        extra_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if plugin_id != "lark":
            return {"success": False, "error": "该渠道尚未开放"}
        cfg = extra_config or {}
        return self._test_lark(
            str(cfg.get("app_id") or ""),
            str(cfg.get("app_secret") or ""),
        )

    def enable_plugin(self, plugin_id: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
        meta = next((m for m in BUILTIN if m["plugin_id"] == plugin_id), None)
        if meta is None:
            raise ChannelError("未知渠道")
        if meta["coming_soon"]:
            raise ChannelError("该渠道即将推出")
        cfg = config or {}
        creds = dict(cfg.get("credentials") or {})
        if plugin_id == "lark":
            if not creds.get("app_id") or not creds.get("app_secret"):
                creds = {**lark_plugin.credentials_from_env(), **{k: v for k, v in creds.items() if v}}
            if not creds.get("app_id") or not creds.get("app_secret"):
                creds = {**self._creds.get("lark", {}), **creds}
            if not creds.get("app_id") or not creds.get("app_secret"):
                raise ChannelError("请输入 App ID 和 App Secret")
            self._creds["lark"] = {
                "app_id": str(creds["app_id"]).strip(),
                "app_secret": str(creds["app_secret"]).strip(),
                "encrypt_key": str(creds.get("encrypt_key") or "").strip(),
                "verification_token": str(creds.get("verification_token") or "").strip(),
            }
            os.environ["LARK_APP_ID"] = self._creds["lark"]["app_id"]
            os.environ["LARK_APP_SECRET"] = self._creds["lark"]["app_secret"]
            if self._creds["lark"]["verification_token"]:
                os.environ["LARK_VERIFY_TOKEN"] = self._creds["lark"]["verification_token"]
            if self._creds["lark"]["encrypt_key"]:
                os.environ["LARK_ENCRYPT_KEY"] = self._creds["lark"]["encrypt_key"]
            self.store.upsert_plugin(
                "lark",
                type="lark",
                name="Lark / 飞书",
                enabled=1,
                has_token=1,
                connected=0,
                status="connecting",
            )
            self._start_runtime()
            if self._start_lark is not None:
                now = int(time.time() * 1000)
                self.store.upsert_plugin(
                    "lark",
                    type="lark",
                    name="Lark / 飞书",
                    enabled=1,
                    has_token=1,
                    connected=1,
                    status="active",
                    last_connected=now,
                )
            self._emit_status("lark")
            return {"ok": True}
        if plugin_id == "weixin":
            self._enable_weixin(creds)
            return {"ok": True}
        raise ChannelError("该渠道尚未开放")

    def _resolve_weixin_creds(self, creds: dict[str, Any]) -> dict[str, Any]:
        extra = creds.get("extra") if isinstance(creds.get("extra"), dict) else {}
        env = weixin_plugin.credentials_from_env()
        stored = {k: v for k, v in (self._creds.get("weixin") or {}).items() if v}
        merged: dict[str, Any] = {**env, **stored}
        account = creds.get("account_id") or creds.get("accountId")
        token = creds.get("bot_token") or creds.get("botToken")
        if account:
            merged["account_id"] = str(account).strip()
        if token:
            merged["bot_token"] = str(token).strip()
        base = extra.get("baseUrl") or creds.get("baseUrl") or creds.get("base_url")
        if base:
            merged["base_url"] = str(base).strip()
        merged.setdefault("base_url", weixin_plugin.DEFAULT_BASE_URL)
        return merged

    def _enable_weixin(self, creds: dict[str, Any]) -> None:
        resolved = self._resolve_weixin_creds(creds)
        if not resolved.get("bot_token") or not resolved.get("account_id"):
            raise ChannelError("请先使用微信扫码登录")
        self._creds["weixin"] = resolved
        os.environ["WEIXIN_BOT_TOKEN"] = str(resolved["bot_token"])
        os.environ["WEIXIN_ACCOUNT_ID"] = str(resolved["account_id"])
        if resolved.get("base_url"):
            os.environ["WEIXIN_BASE_URL"] = str(resolved["base_url"])
        self.store.upsert_plugin(
            "weixin",
            type="weixin",
            name="微信 ClawBot",
            enabled=1,
            has_token=1,
            connected=0,
            status="connecting",
        )
        self._start_weixin_runtime()
        self._emit_status("weixin")

    def _start_weixin_runtime(self) -> None:
        creds = self._creds.get("weixin") or weixin_plugin.credentials_from_env()

        def on_message(payload: dict[str, Any]) -> None:
            self.ingest(
                "weixin",
                user_id=str(payload.get("user_id") or ""),
                chat_id=str(payload.get("chat_id") or ""),
                text=str(payload.get("text") or ""),
                display_name=str(payload.get("display_name") or ""),
                event_id=str(payload.get("event_id") or ""),
            )

        def on_status(status: str, error: str | None) -> None:
            connected = 1 if status == "connected" else 0
            st = "active" if status == "connected" else ("error" if status == "error" else "connecting")
            self.store.upsert_plugin(
                "weixin",
                type="weixin",
                name="微信 ClawBot",
                enabled=1,
                connected=connected,
                status=st,
                last_connected=int(time.time() * 1000) if connected else None,
            )
            self._emit_status("weixin")

        if self._start_weixin is not None:
            self._start_weixin(creds, on_message, on_status)
            self._runtimes.pop("weixin", None)
            on_status("connected", None)
            return
        self._weixin_runtime.start(
            bot_token=str(creds.get("bot_token") or ""),
            account_id=str(creds.get("account_id") or ""),
            base_url=str(creds.get("base_url") or weixin_plugin.DEFAULT_BASE_URL),
            on_message=on_message,
            on_status=on_status,
        )
        self._runtimes["weixin"] = self._weixin_runtime

    def _start_runtime(self) -> None:
        creds = self._creds.get("lark") or lark_plugin.credentials_from_env()

        def on_message(payload: dict[str, Any]) -> None:
            self.ingest(
                "lark",
                user_id=str(payload.get("user_id") or ""),
                chat_id=str(payload.get("chat_id") or ""),
                text=str(payload.get("text") or ""),
                display_name=str(payload.get("display_name") or ""),
                event_id=str(payload.get("event_id") or ""),
            )

        def on_status(status: str, error: str | None) -> None:
            connected = 1 if status == "connected" else 0
            st = "active" if status == "connected" else ("error" if status == "error" else "connecting")
            self.store.upsert_plugin(
                "lark",
                type="lark",
                name="Lark / 飞书",
                enabled=1,
                connected=connected,
                status=st,
                last_connected=int(time.time() * 1000) if connected else None,
            )
            self._emit_status("lark")

        if self._start_lark is not None:
            self._start_lark(creds, on_message, on_status)
            if on_status:
                on_status("connected", None)
            return
        self._runtime.start(
            app_id=creds["app_id"],
            app_secret=creds["app_secret"],
            encrypt_key=creds.get("encrypt_key") or "",
            verification_token=creds.get("verification_token") or "",
            on_message=on_message,
            on_status=on_status,
        )

    def disable_plugin(self, plugin_id: str) -> dict[str, Any]:
        if plugin_id == "weixin":
            if self._stop_weixin is not None:
                self._stop_weixin()
            else:
                self._weixin_runtime.stop()
            self._runtimes.pop("weixin", None)
            self.store.upsert_plugin(
                "weixin",
                type="weixin",
                name="微信 ClawBot",
                enabled=0,
                connected=0,
                status="inactive",
            )
            self._emit_status("weixin")
            return {"ok": True}
        if plugin_id != "lark":
            raise ChannelError("该渠道尚未开放")
        if self._stop_lark is not None:
            self._stop_lark()
        else:
            self._runtime.stop()
        self.store.upsert_plugin(
            "lark",
            type="lark",
            name="Lark / 飞书",
            enabled=0,
            connected=0,
            status="inactive",
        )
        self._emit_status("lark")
        return {"ok": True}

    def restore_enabled(self) -> None:
        self._restore_lark()
        self._restore_weixin()

    def _restore_lark(self) -> None:
        row = self.store.get_plugin("lark")
        if not row or not row.get("enabled"):
            return
        creds = self._creds.get("lark") or lark_plugin.credentials_from_env()
        if not creds.get("app_id") or not creds.get("app_secret"):
            return
        self._creds["lark"] = creds
        try:
            self._start_runtime()
        except Exception as exc:  # noqa: BLE001
            self.store.upsert_plugin(
                "lark",
                type="lark",
                name="Lark / 飞书",
                enabled=1,
                connected=0,
                status="error",
            )
            print(f"lark restore failed: {exc}")

    def _restore_weixin(self) -> None:
        row = self.store.get_plugin("weixin")
        if not row or not row.get("enabled"):
            return
        creds = self._resolve_weixin_creds(self._creds.get("weixin") or {})
        if not creds.get("bot_token") or not creds.get("account_id"):
            return
        self._creds["weixin"] = creds
        try:
            self._start_weixin_runtime()
        except Exception as exc:  # noqa: BLE001
            self.store.upsert_plugin(
                "weixin",
                type="weixin",
                name="微信 ClawBot",
                enabled=1,
                connected=0,
                status="error",
            )
            print(f"weixin restore failed: {exc}")

    def _dedupe(self, event_id: str) -> bool:
        if not event_id:
            return False
        now = int(time.time() * 1000)
        expired = [k for k, ts in self._events.items() if now - ts > EVENT_TTL_MS]
        for k in expired:
            del self._events[k]
        if event_id in self._events:
            return True
        self._events[event_id] = now
        return False

    def ingest(
        self,
        platform: str,
        *,
        user_id: str,
        chat_id: str,
        text: str,
        display_name: str = "",
        event_id: str = "",
    ) -> dict[str, Any]:
        if self._dedupe(event_id):
            return {"ok": True, "deduped": True}
        if not text.strip():
            return {"ok": True, "ignored": True}

        user = self.store.get_user(platform, user_id)
        if user is None:
            pairing = self.store.create_pairing(
                platform_user_id=user_id,
                platform_type=platform,
                display_name=display_name or user_id,
                chat_id=chat_id,
            )
            self.bus.emit("channel.pairing-requested", pairing)
            hint = PAIRING_HINT.format(
                code=pairing["code"],
                channel=CHANNEL_LABELS.get(platform, platform),
            )
            self._schedule(self._send_text(chat_id, hint, platform=platform))
            return {"ok": True, "pairing": True, "code": pairing["code"]}

        self.store.touch_user(platform, user_id, chat_id)
        skill_id = None
        m = _SKILL_MENTION_RE.search(text)
        if m:
            skill_id = m.group(1) or m.group(2)
        skill = find_skill(skill_id) if skill_id else None
        if skill is not None and not skill_usable_via_remote(skill):
            self._schedule(self._send_text(chat_id, REMOTE_DENIED_MSG, platform=platform))
            return {"ok": False, "denied": True, "message": REMOTE_DENIED_MSG}

        settings = self.store.get_settings(platform)
        assistant_id = (settings.get("assistant") or {}).get("assistant_id")
        skill_ids = settings.get("enabled_skill_ids") or None
        if skill and skill.prompt:
            task_text = (
                skill.prompt.format(text=text, **skill.params)
                if "{text}" in skill.prompt
                else skill.prompt
            )
        else:
            task_text = text
        history = self.store.get_chat_history(platform, user_id, chat_id) or None
        self._schedule(
            self._run_and_reply(
                TaskRequest(
                    text=task_text,
                    source=platform,
                    reply_chat_id=chat_id or None,
                    assistant_id=assistant_id,
                    enabled_skill_ids=skill_ids,
                    session_mode="single-agent",
                    history=history,
                ),
                chat_id,
                platform,
                user_id=user_id,
                user_text=text,
            )
        )
        return {"ok": True}

    def ingest_webhook(self, body: dict[str, Any]) -> dict[str, Any]:
        event = body.get("event") or body
        message = event.get("message") or {}
        chat_id = str(
            message.get("chat_id")
            or event.get("chat_id")
            or ""
        )
        content_raw = message.get("content") or event.get("text") or ""
        text = ""
        if isinstance(content_raw, dict):
            text = str(content_raw.get("text") or "")
        elif isinstance(content_raw, str):
            import json

            try:
                parsed = json.loads(content_raw)
                text = str(parsed.get("text") or content_raw)
            except json.JSONDecodeError:
                text = content_raw
        text = text.strip()
        sender = event.get("sender") or {}
        sender_id = sender.get("sender_id") or {}
        user_id = str(
            sender_id.get("open_id")
            or sender_id.get("user_id")
            or chat_id
        )
        header = body.get("header") or {}
        event_id = str(header.get("event_id") or body.get("uuid") or "")
        return self.ingest(
            "lark",
            user_id=user_id,
            chat_id=chat_id,
            text=text,
            display_name=str(sender_id.get("open_id") or user_id),
            event_id=event_id,
        )

    async def _run_and_reply(
        self,
        task_req: TaskRequest,
        chat_id: str,
        platform: str = "lark",
        *,
        user_id: str = "",
        user_text: str = "",
    ) -> None:
        tm = self.task_manager
        if tm is None:
            return
        if platform == "weixin":
            await self._send_text(chat_id, WEIXIN_WORKING, platform=platform)
        chunks: list[str] = []
        summary = ""
        error = ""
        artifacts: list[str] = []
        last_progress = WEIXIN_WORKING
        last_progress_at = time.monotonic() if platform == "weixin" else 0.0
        try:
            async for event in tm.handle(task_req):
                etype = event.get("type")
                if platform == "weixin":
                    progress = weixin_progress_text(event)
                    now = time.monotonic()
                    if (
                        progress
                        and progress != last_progress
                        and now - last_progress_at >= WEIXIN_PROGRESS_MIN_SECS
                    ):
                        await self._send_text(chat_id, progress, platform=platform)
                        last_progress = progress
                        last_progress_at = now
                    if etype == "artifact.file":
                        path = str(event.get("path") or "").strip()
                        if path and path not in artifacts:
                            artifacts.append(path)
                if etype == "step.delta":
                    delta = str(event.get("delta") or "")
                    if delta:
                        chunks.append(delta)
                elif etype == "graph.end":
                    if event.get("status") == "error":
                        error = str(event.get("error") or "未知错误")
                    summary = str(event.get("summary") or "")
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
        stream = "".join(chunks)
        text = compose_channel_reply(
            summary=summary,
            streamed=stream,
            error=error,
            platform=platform,
        )
        if platform == "weixin":
            for blob in (text, summary, stream):
                for path in existing_claimed_office_files(blob):
                    if path not in artifacts:
                        artifacts.append(path)
            if (
                not artifacts
                and wants_document(user_text)
                and (
                    extract_claimed_office_paths(text)
                    or extract_claimed_office_paths(summary)
                    or extract_claimed_office_paths(stream)
                    or looks_like_workspace_dump(text)
                    or looks_like_plan_only(user_text, text)
                )
            ):
                text = MISSING_DOC_HINT
        await self._send_text(chat_id, text, platform=platform)
        if platform == "weixin" and artifacts:
            await self._send_weixin_files(chat_id, artifacts)
        if user_id and user_text.strip() and text.strip():
            self.store.append_chat_turns(
                platform,
                user_id,
                chat_id,
                [
                    {"role": "user", "content": user_text},
                    {"role": "assistant", "content": text},
                ],
            )

    def list_pairings(self) -> list[dict[str, Any]]:
        return self.store.list_pairings()

    def approve_pairing(self, code: str) -> dict[str, Any]:
        rec = self.store.get_pairing(code)
        if rec is None:
            raise ChannelError("配对码无效或已过期")
        now = int(time.time() * 1000)
        if int(rec["expires_at"]) < now:
            self.store.delete_pairing(code)
            raise ChannelError("配对码已过期")
        user = self.store.authorize_user(
            platform_user_id=rec["platform_user_id"],
            platform_type=rec["platform_type"],
            display_name=rec.get("display_name") or "",
            chat_id=rec.get("chat_id") or "",
        )
        self.store.delete_pairing(code)
        self.bus.emit("channel.user-authorized", user)
        chat_id = rec.get("chat_id") or ""
        self._schedule(self._send_text(chat_id, PAIRING_OK, platform=rec.get("platform_type") or "lark"))
        return {"ok": True}

    def reject_pairing(self, code: str) -> dict[str, Any]:
        rec = self.store.get_pairing(code)
        if rec:
            self.store.delete_pairing(code)
        return {"ok": True}

    def list_users(self) -> list[dict[str, Any]]:
        return self.store.list_users()

    def revoke_user(self, user_id: str) -> dict[str, Any]:
        if not self.store.revoke_user(user_id):
            raise ChannelError("用户不存在", 404)
        return {"ok": True}

    def get_settings(self, platform: str) -> dict[str, Any]:
        return self.store.get_settings(platform)

    def set_assistant(self, platform: str, assistant_id: str) -> dict[str, Any]:
        self.store.set_assistant(platform, assistant_id)
        return {"ok": True}

    def set_default_model(self, platform: str, model_id: str, use_model: str) -> dict[str, Any]:
        self.store.set_default_model(platform, model_id, use_model)
        return {"ok": True}
