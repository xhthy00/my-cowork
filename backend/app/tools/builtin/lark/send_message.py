"""L3 Feishu/Lark IM send_message."""

from __future__ import annotations

import os
from typing import Any, Protocol


class LarkMessageClient(Protocol):
    def create_message(self, chat_id: str, text: str) -> str: ...


class _SdkClient:
    """Thin wrapper around lark-oapi im.v1.message.create."""

    def __init__(self, app_id: str, app_secret: str) -> None:
        import lark_oapi as lark
        from lark_oapi.api.im.v1 import (
            CreateMessageRequest,
            CreateMessageRequestBody,
        )

        self._lark = lark
        self._CreateMessageRequest = CreateMessageRequest
        self._CreateMessageRequestBody = CreateMessageRequestBody
        self._client = (
            lark.Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .build()
        )

    def create_message(self, chat_id: str, text: str) -> str:
        import json

        body = (
            self._CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("text")
            .content(json.dumps({"text": text}, ensure_ascii=False))
            .build()
        )
        request = (
            self._CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(body)
            .build()
        )
        response = self._client.im.v1.message.create(request)
        if not response.success():
            raise RuntimeError(
                f"lark send_message failed: code={response.code} msg={response.msg}"
            )
        data: Any = response.data
        return str(getattr(data, "message_id", "") or "")


def _default_client() -> LarkMessageClient:
    app_id = os.environ.get("LARK_APP_ID") or ""
    app_secret = os.environ.get("LARK_APP_SECRET") or os.environ.get("LARK_SECRET") or ""
    if not app_id or not app_secret:
        raise RuntimeError(
            "未配置飞书应用凭证，无法发消息。"
            "请打开 设置 → 远程连接 → 飞书，填写 App ID 与 App Secret 后测试并连接。"
        )
    return _SdkClient(app_id, app_secret)


async def send(
    chat_id: str,
    text: str,
    *,
    client: LarkMessageClient | None = None,
) -> str:
    """Send a text message to *chat_id* and return the message id."""
    c = client or _default_client()
    return c.create_message(chat_id, text)
