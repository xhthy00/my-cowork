"""Tests for TraceStore SQLite persistence + TraceBus wiring."""

import asyncio
import threading
from pathlib import Path

import pytest

from app.observability.trace import TraceBus
from app.observability.trace_store import TraceStore


def test_trace_store_append_and_query(tmp_path: Path):
    store = TraceStore(tmp_path / "trace.db")
    rid = store.append(
        {"type": "graph.start", "task_id": "t1", "node": "coordinator"}
    )
    assert rid > 0
    store.append({"type": "graph.step", "task_id": "t1", "node": "developer_agent"})
    store.append({"type": "graph.end", "task_id": "t2", "status": "ok"})

    rows = store.list_for_task("t1")
    assert len(rows) == 2
    assert rows[0]["type"] == "graph.start"
    assert rows[0]["event"]["task_id"] == "t1"
    assert rows[1]["type"] == "graph.step"
    assert store.list_for_task("t2")[0]["type"] == "graph.end"
    store.close()


@pytest.mark.asyncio
async def test_worker_events_keep_task_context_and_persist_on_owner_thread(tmp_path):
    from app.runtime.todo_context import TodoRuntime, set_todo_runtime, reset_todo_runtime

    store = TraceStore(tmp_path / 'trace.db')
    bus = TraceBus()
    owner = threading.get_ident()
    threads = []
    bus.subscribe(store.append)
    bus.subscribe(lambda event: threads.append(threading.get_ident()))

    async def emit_for_task(task_id):
        token = set_todo_runtime(TodoRuntime(task_id=task_id, bus=bus))
        try:
            def worker():
                assert threading.get_ident() != owner
                bus.emit({'type': 'memory.saved', 'payload': {'id': task_id}})
            await asyncio.to_thread(worker)
        finally:
            reset_todo_runtime(token)

    try:
        await asyncio.gather(emit_for_task('one'), emit_for_task('two'))
        for task_id in ('one', 'two'):
            rows = store.list_for_task(task_id)
            assert len(rows) == 1
            assert rows[0]['event']['payload']['task_id'] == task_id
        assert threads == [owner, owner]
    finally:
        store.close()


def test_bus_created_before_event_loop_can_deliver_worker_events(tmp_path):
    store = TraceStore(tmp_path / 'trace.db')
    bus = TraceBus()
    bus.subscribe(store.append)

    async def run():
        bus.bind_loop()
        await asyncio.to_thread(bus.emit, {'type': 'memory.saved', 'task_id': 'abc'})
        assert len(store.list_for_task('abc')) == 1

    try:
        asyncio.run(run())
    finally:
        store.close()


def test_trace_bus_subscribe_persists(tmp_path: Path):
    store = TraceStore(tmp_path / "trace.db")
    bus = TraceBus()
    bus.subscribe(store.append)
    bus.emit({"type": "graph.start", "task_id": "abc"})
    bus.emit({"type": "budget.update", "task_id": "abc", "tokens": 10})
    rows = store.list_for_task("abc")
    assert [r["type"] for r in rows] == ["graph.start", "budget.update"]
    store.close()
