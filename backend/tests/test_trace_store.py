"""Tests for TraceStore SQLite persistence + TraceBus wiring."""

from pathlib import Path

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


def test_trace_bus_subscribe_persists(tmp_path: Path):
    store = TraceStore(tmp_path / "trace.db")
    bus = TraceBus()
    bus.subscribe(store.append)
    bus.emit({"type": "graph.start", "task_id": "abc"})
    bus.emit({"type": "budget.update", "task_id": "abc", "tokens": 10})
    rows = store.list_for_task("abc")
    assert [r["type"] for r in rows] == ["graph.start", "budget.update"]
    store.close()
