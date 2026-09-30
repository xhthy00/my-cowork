"""Scoped retrieval for a session's canonical transcript after compaction."""

from __future__ import annotations

import re

from langchain_core.tools import BaseTool, tool

from app.runtime.todo_context import get_todo_runtime
from app.runtime.v2.session import load_thread


def make_context_tools() -> list[BaseTool]:
    @tool
    def conversation_read(
        start: int = 0, limit: int = 10, content_offset: int = 0,
        chars_per_message: int = 8_000,
    ) -> dict:
        """Read exact earlier messages in this conversation after context compaction.

        Use start/limit for message pagination and content_offset for a long
        message. Only the current session can be read.
        """
        runtime = get_todo_runtime()
        session_id = str(runtime.session_id or runtime.task_id or "") if runtime else ""
        if not session_id:
            return {"error": "当前没有可读取的会话"}
        messages = load_thread(session_id)
        start = max(0, min(int(start), len(messages)))
        limit = max(1, min(int(limit), 40))
        offset = max(0, int(content_offset))
        chars = max(100, min(int(chars_per_message), 20_000))
        rows = []
        for index in range(start, min(len(messages), start + limit)):
            message = messages[index]
            content = str(getattr(message, "content", "") or "")
            content = re.sub(r"<think>[\s\S]*?</think>", "", content, flags=re.I)
            content = re.sub(r"<think>[\s\S]*$", "", content, flags=re.I)
            rows.append({
                "index": index,
                "role": str(getattr(message, "type", "") or ""),
                "name": str(getattr(message, "name", "") or ""),
                "content": content[offset:offset + chars],
                "content_length": len(content),
                "has_more_content": offset + chars < len(content),
                "tool_calls": getattr(message, "tool_calls", None) or [],
            })
        return {"session_messages": len(messages), "messages": rows,
                "next_start": start + len(rows)}

    return [conversation_read]
