import asyncio
from dataclasses import dataclass

import pytest

from app.graphs.single_agent import compile_single_agent_graph
from app.graphs.workforce import compile_workforce_graph
from app.observability.trace import TraceBus
from app.orchestrator.task_manager import TaskManager, TaskRequest
from tests.conftest import FakeChatModel, make_ai


@dataclass
class _Task:
    task_id: str
    text: str


def _make_graph():
    return compile_workforce_graph(
        workers={},
        planner_llm=FakeChatModel(responses=[make_ai("ok")] * 8),
    )


def _make_single(model: FakeChatModel):
    return compile_single_agent_graph(
        model=model,
        tools=[],
        synthesize_llm=FakeChatModel(responses=[make_ai("ok")] * 8),
    )


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
        sa_model = FakeChatModel(responses=[make_ai(content="solo ok")] * 8)
        sa_graph = _make_single(sa_model)
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


class TestTaskManagerIsolation:
    @pytest.mark.asyncio
    async def test_concurrent_handles_do_not_mix_events(self):
        sa_model = FakeChatModel(
            responses=[make_ai(content="solo a"), make_ai(content="solo b")] * 8
        )
        sa_graph = _make_single(sa_model)
        tm = TaskManager(
            graph=_make_graph(),
            tools=[],
            bus=TraceBus(),
            single_agent_graph=sa_graph,
        )

        async def collect(task_id: str) -> list[dict]:
            return [
                ev
                async for ev in tm.handle(
                    TaskRequest(
                        text="hello",
                        task_id=task_id,
                        session_mode="single-agent",
                    )
                )
            ]

        a, b = await asyncio.gather(collect("task-a"), collect("task-b"))
        assert [ev["type"] for ev in a].count("graph.start") == 1
        assert [ev["type"] for ev in b].count("graph.start") == 1
        assert not any(ev.get("task_id") == "task-b" for ev in a)
        assert not any(ev.get("task_id") == "task-a" for ev in b)

    @pytest.mark.asyncio
    async def test_handle_drops_foreign_bus_events(self):
        bus = TraceBus()
        tm = TaskManager(graph=_make_graph(), tools=[], bus=bus)
        leaked = {"type": "step.delta", "task_id": "foreign", "delta": "leak"}

        events = []
        async for ev in tm.handle(TaskRequest(text="hello", task_id="task-a")):
            events.append(ev)
            if ev["type"] == "graph.start":
                bus.emit(leaked)

        assert events[0]["type"] == "graph.start"
        assert events[-1]["type"] == "graph.end"
        assert not any(
            ev.get("task_id") == "foreign" or ev.get("delta") == "leak" for ev in events
        )


class TestTaskManagerStatus:
    @pytest.mark.asyncio
    async def test_status_missing_task_raises(self):
        tm = TaskManager(graph=_make_graph(), tools=[], bus=TraceBus())
        with pytest.raises(KeyError):
            tm.status("missing")
