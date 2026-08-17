from typing import Any, AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from app.main import create_app
from app.orchestrator.task_manager import TaskManager


class FakeTaskManager:
    def __init__(self, events: list[dict]):
        self.events = events

    async def handle(self, req: Any) -> AsyncIterator[dict[str, Any]]:
        for ev in self.events:
            yield ev


class TestChatRoute:
    @pytest.mark.asyncio
    async def test_chat_sse_stream(self):
        events = [
            {"type": "graph.start", "task_id": "t1"},
            {"type": "graph.step", "task_id": "t1", "node": "supervisor"},
            {"type": "graph.end", "task_id": "t1", "status": "ok"},
        ]
        app = create_app(task_manager=FakeTaskManager(events), bus=None)

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            async with client.stream("POST", "/api/chat", json={"text": "hello"}) as response:
                chunks = []
                async for chunk in response.aiter_text():
                    chunks.append(chunk)

        body = "".join(chunks)
        assert "data:" in body
        assert '"type":"graph.step"' in body
        assert response.headers["content-type"].startswith("text/event-stream")

    @pytest.mark.asyncio
    async def test_chat_requires_text(self):
        app = create_app(task_manager=FakeTaskManager([]), bus=None)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/chat", json={})
        assert response.status_code == 422