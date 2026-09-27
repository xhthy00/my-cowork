"""Lark send_message LangChain tool."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.guardrails.approval import ConfirmHub
from app.tools.builtin.lark import send_message as lark_send


class LarkSendArgs(BaseModel):
    chat_id: str = Field(..., description="Feishu/Lark chat_id to send to")
    text: str = Field(..., description="Message text")


def make_lark_send_tool(confirm_hub: ConfirmHub | None = None) -> StructuredTool:
    def _invoke(chat_id: str, text: str) -> str:
        import asyncio

        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                # Sync tool path from ReAct — run coroutine in a new loop thread if needed.
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    fut = pool.submit(asyncio.run, lark_send.send(chat_id, text))
                    msg_id = fut.result()
            else:
                msg_id = asyncio.run(lark_send.send(chat_id, text))
            return f"sent message_id={msg_id}"
        except Exception as exc:
            # Optional notify must not abort the graph — files already written
            # would otherwise never surface as artifacts.
            return f"发送飞书消息失败：{exc}"

    async def _ainvoke(chat_id: str, text: str) -> str:
        if confirm_hub is not None:
            import uuid

            allowed = await confirm_hub.request(
                f"lark.send_message:{uuid.uuid4().hex}",
                "lark.send_message", {"chat_id": chat_id, "text": text},
            )
            if not allowed:
                return "Operation rejected by user"
        try:
            msg_id = await lark_send.send(chat_id, text)
            return f"sent message_id={msg_id}"
        except Exception as exc:
            return f"发送飞书消息失败：{exc}"

    return StructuredTool.from_function(
        func=_invoke,
        coroutine=_ainvoke,
        name="lark_send_message",
        description=(
            "Send a text message via Feishu/Lark to a chat_id. "
            "If credentials are missing, return an error string; do not fail the task."
        ),
        args_schema=LarkSendArgs,
    )
