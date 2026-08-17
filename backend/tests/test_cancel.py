"""Cancel task mid-run."""

import asyncio
from dataclasses import dataclass
from typing import TypedDict

import pytest
from langgraph.graph import END, START, StateGraph

from app.observability.trace import TraceBus
from app.orchestrator.task_manager import TaskManager, TaskRequest
from app.runtime.graph_runner import run_graph


@dataclass
class _Task:
    task_id: str
    text: str
    session_mode: str = "single-agent"
    memory_enabled: bool = False


def _slow_graph():
    class _S(TypedDict, total=False):
        count: int

    async def step(state):
        await asyncio.sleep(0.05)
        return {"count": state.get("count", 0) + 1}

    builder = StateGraph(_S)
    builder.add_node("step", step)
    builder.add_edge(START, "step")
    builder.add_conditional_edges("step", lambda state: "step")
    graph = builder.compile()
    graph.recursion_limit = 200
    return graph


@pytest.mark.asyncio
async def test_run_graph_cancel_event():
    graph = _slow_graph()
    bus = TraceBus()
    cancel = asyncio.Event()
    events: list[dict] = []

    async def _cancel_soon():
        await asyncio.sleep(0.08)
        cancel.set()

    asyncio.create_task(_cancel_soon())
    async for ev in run_graph(
        _Task(task_id="c1", text="loop"),
        graph,
        bus,
        cancel_event=cancel,
    ):
        events.append(ev)

    assert any(e.get("type") == "graph.end" and e.get("status") == "cancelled" for e in events)


@pytest.mark.asyncio
async def test_task_manager_cancel():
    graph = _slow_graph()
    bus = TraceBus()
    tm = TaskManager(graph=graph, tools=[], bus=bus, single_agent_graph=graph)

    async def _consume():
        out = []
        async for ev in tm.handle(
            TaskRequest(text="loop", session_mode="single-agent", memory_enabled=False)
        ):
            out.append(ev)
            if ev.get("type") == "graph.start":
                # cancel after start
                for tid, meta in list(tm._tasks.items()):
                    if meta["status"] == "RUNNING":
                        tm.cancel(tid)
        return out

    events = await asyncio.wait_for(_consume(), timeout=5)
    assert any(e.get("status") == "cancelled" for e in events if e.get("type") == "graph.end")
    # status should be CANCELLED for the task
    tid = next(iter(tm._tasks))
    assert tm.status(tid) == "CANCELLED"
