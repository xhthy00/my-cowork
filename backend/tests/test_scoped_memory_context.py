from __future__ import annotations

import pytest
import sqlite3
from langchain_core.messages import AIMessage, HumanMessage

from app.memory.long_term import LongTermStore
from app.memory.settings import MemorySettings
from app.memory.tools import make_memory_tools
from app.runtime.v2.context_tools import make_context_tools
from app.runtime.v2.session import SessionStore
from app.runtime.todo_context import TodoRuntime, reset_todo_runtime, set_todo_runtime


def test_scoped_memories_and_stable_session_snapshot(tmp_path):
    store = LongTermStore(tmp_path / "memory.db")
    store.memory_settings = MemorySettings(tmp_path / "settings.json")
    store.remember("总是使用中文", scope="global")
    store.remember("项目 A 的部署目录是 /srv/a", scope="workspace", workspace="a")
    store.remember("项目 B 的部署目录是 /srv/b", scope="workspace", workspace="b")

    first = store.prompt_block(workspace="a", session_id="session-a")
    assert "总是使用中文" in first and "/srv/a" in first
    assert "/srv/b" not in first
    store.remember("后来增加的偏好", scope="global")
    assert store.prompt_block(workspace="a", session_id="session-a") == first
    assert "后来增加的偏好" in store.prompt_block(workspace="a", session_id="session-new")
    store.close()

    reopened = LongTermStore(tmp_path / "memory.db")
    assert reopened.prompt_block(workspace="a", session_id="session-a") == first
    assert "/srv/b" not in reopened.prompt_block(workspace="a", session_id="another")
    reopened.close()


def test_legacy_task_note_is_not_promoted_to_global(tmp_path):
    path = tmp_path / "memory.db"
    connection = sqlite3.connect(path)
    connection.execute("""
        CREATE TABLE memory (
          id INTEGER PRIMARY KEY, task_id TEXT, kind TEXT, content TEXT,
          embedding BLOB, created_at REAL, expires_at REAL)
    """)
    connection.execute("INSERT INTO memory(id,task_id,kind,content,created_at) VALUES (1,NULL,'user_note','全局偏好',1)")
    connection.execute("INSERT INTO memory(id,task_id,kind,content,created_at) VALUES (2,'task-private','note','私有任务事实',2)")
    connection.commit()
    connection.close()
    store = LongTermStore(path)
    assert [item["content"] for item in store.list_memories()] == ["全局偏好"]
    assert "私有任务事实" not in store.prompt_block(workspace="another")
    store.close()


def test_agent_system_prompt_includes_memory_without_embeddings(tmp_path):
    from app.runtime.memory_context import reset_long_term_runtime, set_long_term_runtime
    from app.runtime.v2.assemble import assemble_system_messages

    store = LongTermStore(tmp_path / "memory.db")
    store.memory_settings = MemorySettings(tmp_path / "settings.json")
    store.remember("回答使用简体中文", scope="global")
    memory_token = set_long_term_runtime(store)
    runtime_token = set_todo_runtime(TodoRuntime(task_id="t", bus=None, session_id="s"))
    try:
        prompt = assemble_system_messages(user_text="你好", session_id="s")[0].content
        assert "回答使用简体中文" in prompt
        assert "remember" in prompt
    finally:
        reset_todo_runtime(runtime_token)
        reset_long_term_runtime(memory_token)
        store.close()


def test_save_setting_controls_agent_writes_but_not_reads(tmp_path):
    store = LongTermStore(tmp_path / "memory.db")
    settings = MemorySettings(tmp_path / "settings.json")
    store.remember("已有偏好", scope="global")
    tools = {tool.name: tool for tool in make_memory_tools(store, settings)}
    settings.update(enabled=False)
    assert tools["remember"].invoke({"content": "新偏好", "scope": "global"})["saved"] is False
    assert "已有偏好" in store.prompt_block(workspace=None, session_id="s")
    assert len(store.list_memories(all_scopes=True)) == 1
    store.close()


async def _summary(text: str) -> str:
    return text


def test_conversation_read_is_scoped_to_current_session(tmp_path, monkeypatch):
    from app.runtime.v2 import session as session_module

    monkeypatch.setattr(session_module, "_STORE", SessionStore(tmp_path / "sessions.db"))
    session_module.save_thread("one", [HumanMessage(content="first private detail")])
    session_module.save_thread("two", [HumanMessage(content="second private detail")])
    token = set_todo_runtime(TodoRuntime(task_id="t", bus=None, session_id="one"))
    try:
        tool = make_context_tools()[0]
        result = tool.invoke({"start": 0, "limit": 10})
        assert result["session_messages"] == 1
        assert result["messages"][0]["content"] == "first private detail"
        assert "second private detail" not in str(result)
    finally:
        reset_todo_runtime(token)
