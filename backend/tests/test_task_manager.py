import asyncio
from dataclasses import dataclass

import pytest

from app.graphs.workforce import compile_workforce_graph
from app.observability.trace import TraceBus
from app.orchestrator.task_manager import TaskManager, TaskRequest


@dataclass
class _Task:
    task_id: str
    text: str


def _make_graph():
    return compile_workforce_graph({})


class TestTaskManagerSubmit:
    @pytest.mark.asyncio
    async def test_submit_returns_task_id_and_finishes_done(self):
        # Trivial greeting skips workforce execution.
        tm = TaskManager(graph=_make_graph(), tools=[], bus=TraceBus())
        req = TaskRequest(text="hello")
        task_id = await tm.submit(req)

        assert tm.status(task_id) == "NEW"

        for _ in range(50):
            if tm.status(task_id) in ("DONE", "FAILED"):
                break
            await asyncio.sleep(0.01)

        assert tm.status(task_id) == "DONE"

    @pytest.mark.asyncio
    async def test_submit_failed_on_missing_worker(self):
        # Non-trivial ask → fallback subtask → stub worker raises.
        tm = TaskManager(graph=_make_graph(), tools=[], bus=TraceBus())
        req = TaskRequest(text="写一个文件 hello.txt 到桌面")
        task_id = await tm.submit(req)

        for _ in range(100):
            if tm.status(task_id) in ("DONE", "FAILED"):
                break
            await asyncio.sleep(0.02)

        assert tm.status(task_id) == "FAILED"


class TestTaskManagerHandle:
    @pytest.mark.asyncio
    async def test_handle_yields_events_and_ends_done(self):
        tm = TaskManager(graph=_make_graph(), tools=[], bus=TraceBus())
        req = TaskRequest(text="hello", task_id="t-handle")

        events = [ev async for ev in tm.handle(req)]

        assert events[0]["type"] == "graph.start"
        assert events[-1]["type"] == "graph.end"
        assert tm.status("t-handle") == "DONE"

    @pytest.mark.asyncio
    async def test_handle_routes_single_agent_graph(self):
        from app.agents.factory import create_single_agent
        from app.graphs.single_agent import compile_single_agent_graph
        from tests.conftest import FakeChatModel, make_ai

        sa_model = FakeChatModel(responses=[make_ai(content="solo ok")])
        sa_graph = compile_single_agent_graph(
            create_single_agent("prompt", sa_model, tools=[])
        )
        tm = TaskManager(
            graph=_make_graph(),
            tools=[],
            bus=TraceBus(),
            single_agent_graph=sa_graph,
        )
        req = TaskRequest(
            text="hello",
            task_id="t-sa",
            session_mode="single-agent",
        )
        events = [ev async for ev in tm.handle(req)]
        assert events[-1]["type"] == "graph.end"
        assert events[-1].get("status") != "error"
        assert tm.status("t-sa") == "DONE"
        assert any(
            e["type"] == "agent.create" and e.get("agent_id") == "single_agent"
            for e in events
        )


class TestTaskManagerStatus:
    @pytest.mark.asyncio
    async def test_status_missing_task_raises(self):
        tm = TaskManager(graph=_make_graph(), tools=[], bus=TraceBus())
        with pytest.raises(KeyError):
            tm.status("missing")
