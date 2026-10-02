from typing import Any, AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from app.main import create_app
from app.orchestrator.task_manager import TaskManager
from app.runtime.admission import Admission
from app.server.routes.chat import ChatRequest, _active_tasks, _event_stream


class FakeTaskManager:
    def __init__(self, events: list[dict]):
        self.events = events

    async def handle(self, req: Any) -> AsyncIterator[dict[str, Any]]:
        for ev in self.events:
            yield ev


class TestChatRoute:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("end_status", ["ok", "error", "cancelled"])
    async def test_terminal_event_closes_task_and_releases_admission(self, end_status):
        gate = Admission()
        class Manager:
            closed = False
            async def handle(self, req):
                with gate.work(req.text):
                    try:
                        yield {"type": "graph.end", "task_id": "actual-id", "status": end_status}
                    finally:
                        self.closed = True
        manager = Manager()
        events = [event async for event in _event_stream(manager, ChatRequest(text="写邮件", task_id="requested-id"))]
        assert len(events) == 1
        assert manager.closed
        assert gate.pause()["active"] == 0
        assert "actual-id" not in _active_tasks and "requested-id" not in _active_tasks

    @pytest.mark.asyncio
    async def test_disconnected_stream_closes_running_task(self):
        gate = Admission()
        class Manager:
            async def handle(self, req):
                with gate.work(req.text):
                    yield {"type": "graph.start", "task_id": req.task_id}
                    yield {"type": "graph.end", "task_id": req.task_id}
        stream = _event_stream(Manager(), ChatRequest(text="写邮件", task_id="disconnected"))
        await anext(stream)
        assert gate.status()["active"] == 1
        await stream.aclose()
        assert gate.status()["active"] == 0
        assert "disconnected" not in _active_tasks

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
