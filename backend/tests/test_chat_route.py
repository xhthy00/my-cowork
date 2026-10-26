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


@pytest.mark.asyncio
async def test_human_wait_sends_heartbeats_and_resumes_same_question(monkeypatch):
    import asyncio
    import app.server.routes.chat as route
    from app.guardrails.human_input import HumanInputHub

    monkeypatch.setattr(route, '_HEARTBEAT_SECONDS', 0.01)
    questions = []
    hub = HumanInputHub(questions.append)
    class Manager:
        starts = 0
        answer = None
        async def handle(self, req):
            self.starts += 1
            yield {'type': 'graph.start', 'task_id': req.task_id}
            self.answer = await hub.ask(req.task_id, 'agent', 'Choose?', ['Continue'])
            yield {'type': 'graph.end', 'task_id': req.task_id, 'status': 'ok'}
    manager = Manager()
    stream = _event_stream(manager, ChatRequest(text='wait', task_id='idle-human'))
    try:
        assert 'graph.start' in await anext(stream)
        for _ in range(3):
            assert await anext(stream) == ': ping\n\n'
            assert len(hub.pending('idle-human')) == 1
        question_id = questions[0]['question_id']
        assert hub.reply('idle-human', question_id, 'Continue')
        assert 'graph.end' in await anext(stream)
    finally:
        await stream.aclose()
    assert manager.starts == 1 and manager.answer == 'Continue'
    assert not hub.pending('idle-human')
    assert 'idle-human' not in _active_tasks


@pytest.mark.asyncio
@pytest.mark.parametrize('stop', [False, True])
async def test_idle_stream_cleanup_cancels_pending_step(monkeypatch, stop):
    import asyncio
    import app.server.routes.chat as route

    monkeypatch.setattr(route, '_HEARTBEAT_SECONDS', 0.01)
    class Manager:
        closed = False
        cancelled = False
        async def handle(self, req):
            try:
                yield {'type': 'graph.start', 'task_id': req.task_id}
                await asyncio.Event().wait()
            finally:
                self.closed = True
        def cancel(self, task_id):
            self.cancelled = True
    manager = Manager()
    stream = _event_stream(manager, ChatRequest(text='wait', task_id='idle-cleanup'))
    await anext(stream)
    assert await anext(stream) == ': ping\n\n'
    if stop:
        _active_tasks['idle-cleanup'] = False
        assert 'cancelled' in await anext(stream)
    await stream.aclose()
    assert manager.closed
    assert manager.cancelled == stop
    assert 'idle-cleanup' not in _active_tasks


@pytest.mark.asyncio
async def test_idle_stream_propagates_agent_failure_and_cleans_up(monkeypatch):
    import asyncio
    import app.server.routes.chat as route

    monkeypatch.setattr(route, '_HEARTBEAT_SECONDS', 0.01)
    fail = asyncio.Event()
    class Manager:
        closed = False
        async def handle(self, req):
            try:
                yield {'type': 'graph.start', 'task_id': req.task_id}
                await fail.wait()
                raise RuntimeError('agent failure')
            finally:
                self.closed = True
    manager = Manager()
    stream = _event_stream(manager, ChatRequest(text='wait', task_id='idle-error'))
    await anext(stream)
    assert await anext(stream) == ': ping\n\n'
    fail.set()
    with pytest.raises(RuntimeError, match='agent failure'):
        await anext(stream)
    assert manager.closed and 'idle-error' not in _active_tasks
