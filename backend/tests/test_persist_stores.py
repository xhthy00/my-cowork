"""TaskStore + ShortTermStore SQLite persistence."""

from pathlib import Path

from app.memory.short_term import ShortTermStore
from app.orchestrator.task_store import TaskStore


def test_task_store_persist(tmp_path: Path):
    db = tmp_path / "tasks.db"
    store = TaskStore(db)
    store.upsert("t1", "RUNNING", text="hello")
    store.upsert("t1", "DONE", text="hello")
    store.close()

    store2 = TaskStore(db)
    assert store2.get_status("t1") == "DONE"
    assert store2.get("t1")["text"] == "hello"
    store2.close()


def test_short_term_sqlite_persist(tmp_path: Path):
    db = tmp_path / "memory.db"
    store = ShortTermStore(db)
    store.append("t1", {"role": "user", "content": "hi"})
    store.append("t1", {"role": "assistant", "content": "yo"})
    store.close()

    store2 = ShortTermStore(db)
    msgs = store2.get("t1")
    assert len(msgs) == 2
    assert msgs[0]["content"] == "hi"
    store2.clear("t1")
    assert store2.get("t1") == []
    store2.close()
