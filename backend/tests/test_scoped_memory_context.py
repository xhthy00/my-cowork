from __future__ import annotations

import pytest
import sqlite3
from langchain_core.messages import AIMessage, HumanMessage

from app.memory.long_term import LongTermStore
from app.memory.settings import MemorySettings
from app.memory.tools import make_memory_tools
from app.runtime.v2.compact import compact_session_history
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


@pytest.mark.asyncio
async def test_compaction_preserves_canonical_transcript_and_reload(tmp_path):
    store = SessionStore(tmp_path / "sessions.db")
    original = [message for i in range(8) for message in
                (HumanMessage(content=f"request {i} " + "x" * 100),
                 AIMessage(content=f"answer {i} " + "y" * 100))]
    store.save("s", original)

    async def summarize(messages):
        return f"Summary of {len(messages)} messages"

    outbound, state = await compact_session_history(
        store.load("s"), threshold=100, summarize=summarize,
    )
    assert state is not None and state["boundary_index"] > 0
    assert outbound[0].type == "system"
    assert "request 0" in outbound[0].content
    store.save_compaction("s", state)
    transcript = store.write_compaction_transcript("s", store.load("s"), state["boundary_index"])
    assert "request 0" in open(transcript, encoding="utf-8").read()
    reloaded = SessionStore(tmp_path / "sessions.db")
    assert len(reloaded.load("s")) == len(original)
    assert reloaded.load_compaction("s") == state
    reloaded.clear("s")
    assert reloaded.load_compaction("s") is None


@pytest.mark.asyncio
async def test_second_compaction_carries_previous_summary_forward():
    original = [message for i in range(6) for message in
                (HumanMessage(content=f"turn {i}"), AIMessage(content="answer " + "x" * 300))]
    first, state = await compact_session_history(original, threshold=100,
        summarize=lambda messages: _summary(f"First span: {len(messages)}"))
    assert state is not None and first[0].type == "system"
    extended = [*original, *[message for i in range(6, 12) for message in
                (HumanMessage(content=f"turn {i}"), AIMessage(content="answer " + "y" * 300))]]
    seen: list[str] = []

    async def summarize(messages):
        seen.extend(str(message.content) for message in messages)
        return "Second summary"

    _, second = await compact_session_history(extended, state, threshold=100, summarize=summarize)
    assert second is not None and second["boundary_index"] > state["boundary_index"]
    assert any("First span" in text for text in seen)
    assert "turn 0" in second["summary_text"]


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


@pytest.mark.asyncio
async def test_single_agent_compaction_keeps_full_saved_history(tmp_path, monkeypatch):
    from app.graphs import single_agent as single_module
    from app.graphs.state import WorkforceState
    from app.runtime.v2 import session as session_module
    from tests.conftest import FakeChatModel, make_ai

    store = SessionStore(tmp_path / "sessions.db")
    monkeypatch.setattr(session_module, "_STORE", store)
    old = [message for i in range(5) for message in
           (HumanMessage(content=f"old request {i}"),
            AIMessage(content="old answer " + "x" * 300))]
    store.save("conversation", old)
    original_compact = single_module.compact_session_history

    async def force_compact(messages, state, *, llm, threshold):
        return await original_compact(messages, state, threshold=100,
                                      summarize=lambda _: _summary("之前已完成调研"))

    monkeypatch.setattr(single_module, "compact_session_history", force_compact)
    model = FakeChatModel(responses=[make_ai("这是本轮回答。") for _ in range(8)])
    graph = single_module.compile_single_agent_graph(model=model, tools=[])
    await graph.ainvoke(WorkforceState(
        messages=[HumanMessage(content="继续")], task_id="new-task",
        session_id="conversation", session_mode="single-agent",
        user_text="继续", round=0,
    ))
    saved = store.load("conversation")
    assert [message.content for message in saved[:len(old)]] == [message.content for message in old]
    assert sum(1 for message in saved if message.type == "human" and message.content == "继续") == 1
    assert any(message.type == "ai" and "本轮回答" in message.content for message in saved)
    assert store.load_compaction("conversation") is not None
