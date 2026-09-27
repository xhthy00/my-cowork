import asyncio

import httpx
import pytest

from app.guardrails.human_input import HumanInputHub
from app.main import create_app
from app.server.channels.manager import ChannelManager
from app.server.channels.store import ChannelStore
from app.runtime.todo_context import TodoRuntime, reset_todo_runtime, set_todo_runtime
from app.runtime.v2.loop import run_act_loop
from app.tools.builtin.human import make_ask_human_tool
from tests.conftest import FakeChatModel, make_ai


@pytest.mark.asyncio
async def test_agent_question_waits_for_matching_reply():
    events = []
    asked = asyncio.Event()

    def emit(event):
        events.append(event)
        asked.set()

    hub = HumanInputHub(emit)
    tool = make_ask_human_tool(hub)
    token = set_todo_runtime(TodoRuntime(task_id="task-a", bus=None, agent_id="developer_agent"))
    try:
        waiting = asyncio.create_task(tool.ainvoke({"question": "选择格式？", "options": ["PDF", "Word"]}))
        await asyncio.wait_for(asked.wait(), timeout=2)
        ask = events[0]
        assert ask["type"] == "human.ask"
        assert ask["agent"] == "developer_agent"
        assert not waiting.done()
        assert not hub.reply("task-b", ask["question_id"], "PDF")
        assert hub.reply("task-a", ask["question_id"], "Word")
        assert await waiting == "Word"
        assert hub.pending("task-a") == []
        assert not hub.reply("task-a", ask["question_id"], "PDF")
    finally:
        reset_todo_runtime(token)


@pytest.mark.asyncio
async def test_structured_fields_reach_the_pending_question():
    events = []
    hub = HumanInputHub(events.append)
    tool = make_ask_human_tool(hub)
    token = set_todo_runtime(TodoRuntime(task_id="task-form", bus=None))
    try:
        waiting = asyncio.create_task(tool.ainvoke({
            "question": "请补充通知内容",
            "fields": [
                {"label": "通知事项", "kind": "single", "options": ["价格调整", "系统维护"], "required": True},
                {"label": "发送日期", "kind": "text", "required": True},
            ],
        }))
        for _ in range(100):
            if events:
                break
            await asyncio.sleep(0.01)
        assert events[0]["fields"][0] == {
            "label": "通知事项", "kind": "single", "options": ["价格调整", "系统维护"],
            "required": True, "placeholder": "",
        }
        assert len(hub.pending("task-form")[0]["fields"]) == 2
        assert hub.reply("task-form", events[0]["question_id"], "1. 通知事项：价格调整\n2. 发送日期：10月1日")
        assert "10月1日" in await waiting
    finally:
        reset_todo_runtime(token)


@pytest.mark.asyncio
async def test_cancel_releases_agent_wait():
    hub = HumanInputHub(lambda _event: None)
    waiting = asyncio.create_task(hub.ask("task-a", "single_agent", "继续吗？"))
    await asyncio.sleep(0)
    hub.cancel_task("task-a")
    with pytest.raises(asyncio.CancelledError):
        await waiting
    assert hub.pending("task-a") == []


@pytest.mark.asyncio
async def test_question_history_survives_restart_without_false_pending(tmp_path):
    db = tmp_path / "human.db"
    first = HumanInputHub(lambda _event: None, db_path=db)
    waiting = asyncio.create_task(first.ask("task-a", "single_agent", "选择方案？", ["A", "B"]))
    await asyncio.sleep(0)
    question_id = first.pending("task-a")[0]["question_id"]
    second = HumanInputHub(lambda _event: None, db_path=db)
    assert second.pending("task-a") == []
    assert second.history("task-a")[0]["status"] == "interrupted"
    assert second.history("task-a")[0]["question_id"] == question_id
    assert not second.reply("task-a", question_id, "A")
    first.cancel_task("task-a")
    with pytest.raises(asyncio.CancelledError):
        await waiting


@pytest.mark.asyncio
async def test_other_branches_wait_until_user_decides():
    events = []
    hub = HumanInputHub(events.append)
    asking = asyncio.create_task(hub.ask("task-a", "developer_agent", "选 A 还是 B？"))
    await asyncio.sleep(0)
    other_branch = asyncio.create_task(hub.wait_until_clear("task-a"))
    await asyncio.sleep(0)
    assert not other_branch.done()
    assert hub.reply("task-a", events[0]["question_id"], "B")
    assert await asking == "B"
    await asyncio.wait_for(other_branch, timeout=1)


@pytest.mark.asyncio
async def test_act_loop_continues_after_human_answer():
    events = []
    hub = HumanInputHub(events.append)
    model = FakeChatModel(responses=[
        make_ai(tool_calls=[{
            "name": "ask_human",
            "args": {"question": "选哪种？", "options": ["A", "B"]},
            "id": "call-1",
        }]),
        make_ai("按 B 继续完成"),
    ])
    token = set_todo_runtime(TodoRuntime(task_id="task-loop", bus=None))
    try:
        running = asyncio.create_task(run_act_loop(model, [make_ask_human_tool(hub)], []))
        for _ in range(100):
            if events:
                break
            await asyncio.sleep(0.01)
        assert events and not running.done()
        assert hub.reply("task-loop", events[0]["question_id"], "B")
        result = await asyncio.wait_for(running, timeout=2)
        assert result[-1].content == "按 B 继续完成"
        assert any(getattr(item, "content", "") == "B" for item in result)
    finally:
        reset_todo_runtime(token)


@pytest.mark.asyncio
async def test_reply_route_requires_live_matching_question():
    hub = HumanInputHub(lambda _event: None)

    class Manager:
        human_input_hub = hub

    app = create_app(task_manager=Manager())
    waiting = asyncio.create_task(hub.ask("task-a", "single_agent", "选择？"))
    await asyncio.sleep(0)
    question_id = hub.pending("task-a")[0]["question_id"]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        pending = await client.get("/api/chat/task-a/pending-questions")
        assert pending.status_code == 200
        assert pending.json()["questions"][0]["question_id"] == question_id
        wrong = await client.post(
            "/api/chat/task-b/human-reply",
            json={"question_id": question_id, "answer": "A"},
        )
        assert wrong.status_code == 409
        good = await client.post(
            "/api/chat/task-a/human-reply",
            json={"question_id": question_id, "answer": "B"},
        )
        assert good.status_code == 200
        duplicate = await client.post(
            "/api/chat/task-a/human-reply",
            json={"question_id": question_id, "answer": "A"},
        )
        assert duplicate.status_code == 409
    assert await waiting == "B"


@pytest.mark.asyncio
async def test_remote_channel_reply_resumes_original_task(tmp_path):
    emitted = []
    hub = HumanInputHub(emitted.append)
    sent = []

    class Manager:
        human_input_hub = hub
        runs = 0

        async def handle(self, _request):
            self.runs += 1
            waiting = asyncio.create_task(hub.ask("task-remote", "single_agent", "选格式？", ["PDF", "Word"]))
            await asyncio.sleep(0)
            yield emitted[0]
            answer = await waiting
            yield {"type": "graph.end", "status": "ok", "summary": f"已选 {answer}"}

    async def send(_chat_id, content):
        sent.append(content)

    task_manager = Manager()
    channels = ChannelManager(ChannelStore(tmp_path / "channels.db"), task_manager, send=send)
    channels.store.authorize_user(platform_user_id="u1", platform_type="lark", chat_id="c1")
    channels.ingest("lark", user_id="u1", chat_id="c1", text="做报告")
    for _ in range(100):
        if any("选格式" in item for item in sent):
            break
        await asyncio.sleep(0.01)
    assert any("1. PDF" in item for item in sent)
    channels.ingest("lark", user_id="u1", chat_id="c1", text="2")
    for _ in range(100):
        if any("已选 Word" in item for item in sent):
            break
        await asyncio.sleep(0.01)
    assert any("已选 Word" in item for item in sent)
    assert task_manager.runs == 1
