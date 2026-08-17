import pytest
from dataclasses import dataclass
from typing import TypedDict

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from app.observability.trace import TraceBus
from app.runtime.budget import Budget, BudgetExhausted
from app.runtime.checkpointer import get_checkpointer, get_latest_state
from app.runtime.graph_runner import run_graph
from tests.conftest import FakeChatModel, make_ai


@dataclass
class _Task:
    task_id: str
    text: str
    session_mode: str = "workforce"
    memory_enabled: bool = True


class TestBudget:
    def test_budget_raises_on_51st_step(self):
        budget = Budget(max_steps=50, max_total_tokens=10**9)
        for _ in range(50):
            budget.consume_step()
        with pytest.raises(BudgetExhausted):
            budget.consume_step()

    def test_budget_raises_on_token_exceed(self):
        budget = Budget(max_steps=10**9, max_total_tokens=10)
        budget.consume_tokens(7)
        budget.consume_tokens(3)
        with pytest.raises(BudgetExhausted):
            budget.consume_tokens(1)

    def test_budget_under_limit_no_raise(self):
        budget = Budget(max_steps=3, max_total_tokens=100)
        budget.consume_step()
        budget.consume_tokens(50)
        budget.consume_step()
        assert budget.steps == 2
        assert budget.tokens == 50


def _looping_graph(recursion_limit: int = 200):
    """A graph with a single node that always routes back to itself."""

    class _S(TypedDict, total=False):
        count: int

    def step(state):
        return {"count": state.get("count", 0) + 1}

    builder = StateGraph(_S)
    builder.add_node("step", step)
    builder.add_edge(START, "step")
    builder.add_conditional_edges("step", lambda state: "step")
    builder.add_edge("step", "step")  # not used but keeps schema valid
    graph = builder.compile()
    graph.recursion_limit = recursion_limit
    return graph


class TestRunGraphBudgetTruncation:
    @pytest.mark.asyncio
    async def test_run_graph_emits_budget_exhausted(self):
        graph = _looping_graph(recursion_limit=200)

        budget = Budget(max_steps=3, max_total_tokens=10**9)
        bus = TraceBus()
        received = []
        bus.subscribe(lambda ev: received.append(ev))

        events = []
        with pytest.raises(BudgetExhausted):
            async for ev in run_graph(
                _Task(task_id="t", text="loop forever please", session_mode="single-agent"),
                graph,
                bus,
                budget=budget,
            ):
                events.append(ev)

        assert any(e["type"] == "budget.exhausted" for e in events)
        assert events[-1]["type"] == "graph.end"
        assert "budget exhausted" in events[-1]["error"].lower() or "exhausted" in events[-1]["error"].lower()


class TestCheckpointer:
    def test_get_checkpointer_returns_memory_saver(self):
        cp = get_checkpointer()
        assert cp is not None

    def test_checkpoint_reads_latest_state(self):
        cp = get_checkpointer()

        class _S(TypedDict, total=False):
            messages: list

        def echo(state):
            return {"messages": state["messages"] + [AIMessage(content="echo")]}

        builder = StateGraph(_S)
        builder.add_node("echo", echo)
        builder.add_edge(START, "echo")
        builder.add_edge("echo", END)
        graph = builder.compile(checkpointer=cp)

        config = {"configurable": {"thread_id": "t-cp"}}
        graph.invoke({"messages": [HumanMessage(content="hi")]}, config=config)

        state = get_latest_state(cp, "t-cp")
        assert state is not None
        contents = [str(m.content) for m in state["messages"]]
        assert "hi" in contents
        assert "echo" in contents

    def test_sqlite_checkpointer_persists(self, tmp_path):
        db = tmp_path / "checkpoints.db"
        cp = get_checkpointer(db, sync=True)

        class _S(TypedDict, total=False):
            messages: list

        def echo(state):
            return {"messages": state["messages"] + [AIMessage(content="sqlite")]}

        builder = StateGraph(_S)
        builder.add_node("echo", echo)
        builder.add_edge(START, "echo")
        builder.add_edge("echo", END)
        graph = builder.compile(checkpointer=cp)
        config = {"configurable": {"thread_id": "t-sql"}}
        graph.invoke({"messages": [HumanMessage(content="hi")]}, config=config)

        cp2 = get_checkpointer(db, sync=True)
        state = get_latest_state(cp2, "t-sql")
        assert state is not None
        assert any("sqlite" in str(m.content) for m in state["messages"])
