from app.memory.short_term import ShortTermStore


class TestShortTermStore:
    def test_get_empty_for_unknown_task(self):
        store = ShortTermStore()
        assert store.get("task-1") == []

    def test_append_and_get(self):
        store = ShortTermStore()
        store.append("task-1", {"role": "user", "content": "hi"})
        store.append("task-1", {"role": "assistant", "content": "hello"})
        assert store.get("task-1") == [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]

    def test_task_isolation(self):
        store = ShortTermStore()
        store.append("task-1", "msg-a")
        store.append("task-2", "msg-b")
        assert store.get("task-1") == ["msg-a"]
        assert store.get("task-2") == ["msg-b"]

    def test_clear_removes_only_target_task(self):
        store = ShortTermStore()
        store.append("task-1", "msg-a")
        store.append("task-2", "msg-b")
        store.clear("task-1")
        assert store.get("task-1") == []
        assert store.get("task-2") == ["msg-b"]
