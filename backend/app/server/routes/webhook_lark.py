"""L9 Feishu webhook: verify signature, IP allowlist, submit TaskRequest."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.guardrails.policy import skill_usable_via_remote
from app.orchestrator.task_manager import TaskRequest
from app.skills import SkillMeta, find_skill
from app.server.channels.manager import compose_channel_reply
from app.tools.builtin.lark import send_message as lark_send

router = APIRouter()

REMOTE_DENIED_MSG = "此技能需桌面客户端运行，请打开 app 后再尝试"

# Default empty → allow all (tests inject via env). Production should set CIDRs/IPs.
_SKILL_MENTION_RE = re.compile(
    r"(?:skill|技能)[\s:：]*([a-zA-Z0-9_-]+)|用\s*([a-zA-Z0-9_-]+)\s*skill",
    re.IGNORECASE,
)


def _lark_ips() -> set[str]:
    raw = os.environ.get("LARK_IPS", "")
    return {p.strip() for p in raw.split(",") if p.strip()}


def _verify_token() -> str:
    return os.environ.get("LARK_VERIFY_TOKEN") or os.environ.get("LARK_ENCRYPT_KEY") or ""


def verify_lark_signature(timestamp: str, signature: str, token: str | None = None) -> bool:
    """Verify a Feishu webhook event signature.

    Algorithm: ``HMAC-SHA256(key=token, msg=timestamp + "\\n" + token)``,
    hex-encoded, then compared with ``X-Lark-Signature`` in constant time.
    Spec: https://open.feishu.cn/document/server-docs/event-subscription-guide/overview
    """
    secret = token if token is not None else _verify_token()
    if not secret or not timestamp or not signature:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}\n{secret}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _extract_text_and_chat(body: dict[str, Any]) -> tuple[str, str]:
    """Parse Feishu event payload → (text, chat_id)."""
    # url_verification handled elsewhere
    event = body.get("event") or body
    message = event.get("message") or {}
    chat_id = str(
        message.get("chat_id")
        or event.get("chat_id")
        or (event.get("sender") or {}).get("sender_id", {}).get("open_id")
        or ""
    )
    content_raw = message.get("content") or event.get("text") or ""
    text = ""
    if isinstance(content_raw, dict):
        text = str(content_raw.get("text") or "")
    elif isinstance(content_raw, str):
        try:
            parsed = json.loads(content_raw)
            text = str(parsed.get("text") or content_raw)
        except json.JSONDecodeError:
            text = content_raw
    return text.strip(), chat_id


def _match_skill(text: str) -> SkillMeta | None:
    m = _SKILL_MENTION_RE.search(text)
    if not m:
        return None
    skill_id = m.group(1) or m.group(2)
    return find_skill(skill_id) if skill_id else None


def _client_ip(request: Request) -> str:
    if request.client is None:
        return ""
    return request.client.host or ""


async def _run_and_reply(
    task_manager: Any,
    task_req: TaskRequest,
    reply_chat_id: str,
    send=lark_send.send,
) -> None:
    summary = ""
    streamed: list[str] = []
    error = ""
    try:
        async for event in task_manager.handle(task_req):
            etype = event.get("type")
            if etype == "step.delta":
                delta = str(event.get("delta") or "")
                if delta:
                    streamed.append(delta)
            elif etype == "graph.end":
                if event.get("status") == "error":
                    error = str(event.get("error") or "未知错误")
                summary = str(event.get("summary") or "")
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
    text = compose_channel_reply(
        summary=summary,
        streamed="".join(streamed),
        error=error,
    )
    try:
        await send(reply_chat_id, text)
    except Exception as exc:  # noqa: BLE001
        print(f"lark reply failed: {exc}")


@router.post("/webhook/lark")
async def webhook_lark(request: Request) -> JSONResponse:
    # IP allowlist (optional when LARK_IPS unset — local/dev)
    allowed = _lark_ips()
    ip = _client_ip(request)
    if allowed and ip not in allowed and ip not in {"127.0.0.1", "::1", "testclient"}:
        return JSONResponse({"detail": "forbidden"}, status_code=403)

    body: dict[str, Any] = await request.json()

    # Challenge handshake for event subscription setup
    if body.get("type") == "url_verification" or ("challenge" in body and not body.get("event")):
        return JSONResponse({"challenge": body.get("challenge")})

    timestamp = request.headers.get("X-Lark-Request-Timestamp") or request.headers.get(
        "x-lark-request-timestamp", ""
    )
    signature = request.headers.get("X-Lark-Signature") or request.headers.get(
        "x-lark-signature", ""
    )
    token = _verify_token()
    if token and not verify_lark_signature(timestamp, signature, token):
        return JSONResponse({"detail": "invalid signature"}, status_code=401)

    text, chat_id = _extract_text_and_chat(body)
    if not text:
        return JSONResponse({"ok": True, "ignored": True})

    channels = getattr(request.app.state, "channels", None)
    if channels is not None:
        send = getattr(request.app.state, "lark_send", lark_send.send)
        channels._send = send
        result = channels.ingest_webhook(body)
        return JSONResponse(result)

    skill = _match_skill(text)
    if skill is not None and not skill_usable_via_remote(skill):
        # Best-effort notify; do not block webhook on send failures in tests without creds
        send = getattr(request.app.state, "lark_send", lark_send.send)
        try:
            await send(chat_id, REMOTE_DENIED_MSG)
        except Exception:  # noqa: BLE001
            pass
        return JSONResponse(
            {"ok": False, "denied": True, "message": REMOTE_DENIED_MSG},
            status_code=200,
        )

    if skill and skill.prompt:
        if "{text}" in skill.prompt:
            task_text = skill.prompt.format(text=text, **skill.params)
        else:
            task_text = skill.prompt
    else:
        task_text = text

    task_manager = request.app.state.task_manager
    task_req = TaskRequest(
        text=task_text,
        source="lark",
        reply_chat_id=chat_id or None,
    )
    send = getattr(request.app.state, "lark_send", lark_send.send)

    # Non-blocking: ack webhook immediately, run task + reply in background
    asyncio.create_task(_run_and_reply(task_manager, task_req, chat_id, send=send))
    return JSONResponse({"ok": True})
