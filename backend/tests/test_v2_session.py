"""v2 session thread persistence."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.runtime.v2.session import SessionStore, append_run, load_thread, save_thread


def test_session_roundtrip_keeps_tool_calls(tmp_path):
    store = SessionStore(tmp_path / "sessions.db")
    messages = [
        HumanMessage(content="调研政策"),
        AIMessage(
            content="",
            tool_calls=[{"id": "c1", "name": "web_search", "args": {"query": "政策"}}],
        ),
        ToolMessage(content='[{"url":"https://example.gov"}]', tool_call_id="c1", name="web_search"),
        AIMessage(content="根据检索，政策已调整。"),
    ]
    store.save("sess-1", messages)
    loaded = store.load("sess-1")
    assert len(loaded) == 4
    assert loaded[0].content == "调研政策"
    assert loaded[1].tool_calls
    assert loaded[1].tool_calls[0]["name"] == "web_search"
    assert loaded[2].content.startswith("[{")
    store.clear("sess-1")
    assert store.load("sess-1") == []


def test_append_run_merges(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_COWORK_DATA_DIR", str(tmp_path))
    from app.runtime.v2 import session as session_mod

    session_mod._STORE = SessionStore(tmp_path / "s.db")
    save_thread("s", [HumanMessage(content="a")])
    append_run("s", [AIMessage(content="b")])
    loaded = load_thread("s")
    assert [m.content for m in loaded] == ["a", "b"]
