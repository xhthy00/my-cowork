"""Budget admission uses the real callback dispatcher, including pause/resume."""
import asyncio
from uuid import uuid4

import pytest
from langchain_core.callbacks.manager import ahandle_event
from langchain_core.messages import HumanMessage
from langchain_core.outputs import LLMResult

from app.llm.budget import Budget, BudgetExhausted
from app.llm.budget_callback import BudgetTokenCallback, BudgetGateCallback
from app.llm.budget_context import BudgetRuntime, set_budget_runtime, reset_budget_runtime
from app.observability.trace import TraceBus


def test_overrun_is_still_accounted():
    budget = Budget(50, 200_000)
    budget.consume_tokens(190_000)
    with pytest.raises(BudgetExhausted):
        budget.consume_tokens(20_000)
    assert budget.tokens == 210_000
    assert budget.exhausted


def test_unlimited_still_counts_and_limits_steps():
    budget = Budget(1, None)
    budget.consume_tokens(10_000_000)
    assert budget.tokens == 10_000_000
    budget.consume_step()
    with pytest.raises(BudgetExhausted):
        budget.consume_step()


@pytest.mark.asyncio
async def test_real_dispatch_records_overrun_and_blocks_next_call(monkeypatch):
    monkeypatch.setattr("app.llm.budget_callback.count_tokens", lambda _: 100)
    bus = TraceBus()
    events = []
    bus.subscribe(events.append)
    budget = Budget(50, 200_000)
    budget.consume_tokens(190_000)
    rt = BudgetRuntime("task", bus, budget)
    token = set_budget_runtime(rt)
    callbacks = [BudgetGateCallback(), BudgetTokenCallback()]
    try:
        run_id = uuid4()
        await ahandle_event(callbacks, "on_chat_model_start", "ignore_chat_model", {}, [[HumanMessage(content="hello")]], run_id=run_id)
        await ahandle_event(callbacks, "on_llm_end", "ignore_llm", LLMResult(generations=[], llm_output={"token_usage": {"total_tokens": 20_000}}), run_id=run_id)
        assert budget.tokens == 210_000
        assert any(e["type"] == "budget.update" and e["tokens"] == 210_000 for e in events)
        pending = asyncio.create_task(ahandle_event(callbacks, "on_chat_model_start", "ignore_chat_model", {}, [[HumanMessage(content="next")]], run_id=uuid4()))
        await asyncio.sleep(0)
        assert not pending.done()
        assert rt.paused
        assert any(e["type"] == "budget.paused" for e in events)
        with pytest.raises(ValueError):
            rt.resume(200_000)
        rt.resume(300_000)
        await asyncio.wait_for(pending, 1)
        assert budget.tokens == 210_000
        assert not rt.paused
    finally:
        reset_budget_runtime(token)


@pytest.mark.asyncio
async def test_parallel_inputs_wait_for_settlement_before_asking_for_budget():
    rt = BudgetRuntime("task", TraceBus(), Budget(50, 1000))
    await rt.admit("a", 700)
    pending = asyncio.create_task(rt.admit("b", 700))
    await asyncio.sleep(0)
    assert not pending.done()
    assert not rt.paused
    rt.budget.consume_tokens(200)
    rt.release("a")
    await asyncio.wait_for(pending, 1)


@pytest.mark.asyncio
async def test_paused_wait_can_be_cancelled():
    rt = BudgetRuntime("task", TraceBus(), Budget(50, 100))
    pending = asyncio.create_task(rt.admit("a", 200))
    await asyncio.sleep(0)
    assert rt.paused
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending


@pytest.mark.asyncio
async def test_manager_resumes_same_task_without_replaying_tool(monkeypatch, tmp_path):
    from app.orchestrator.task_manager import TaskManager, TaskRequest
    from app.orchestrator.task_store import TaskStore
    from app.runtime.v2.loop import _invoke_tool
    from langchain_core.tools import StructuredTool
    from app.llm.budget_context import record_llm_tokens

    writes = []
    tool = StructuredTool.from_function(lambda: writes.append("write") or "ok", name="write", description="test write")
    async def graph(task, graph, bus, *, budget_runtime, **kwargs):
        token = set_budget_runtime(budget_runtime)
        try:
            await _invoke_tool(tool, {})
            record_llm_tokens(120)
            await budget_runtime.admit("next", 10)
            await _invoke_tool(tool, {})
            bus.emit({"task_id": task.task_id, "type": "graph.end", "status": "done"})
            yield {}
        finally:
            reset_budget_runtime(token)
    monkeypatch.setattr("app.orchestrator.task_manager.run_graph", graph)
    store = TaskStore(tmp_path / "tasks.db")
    manager = TaskManager(None, [], TraceBus(), task_store=store)
    manager.set_budget_settings({"max_tokens": 100})
    request = TaskRequest("test", session_id="chat")
    manager.prepare_task(request)
    manager.set_budget_settings({"max_tokens": None})
    events = []
    async def run():
        async for event in manager.handle(request):
            events.append(event)
    execution = asyncio.create_task(run())
    for _ in range(100):
        if manager.status(request.task_id) == "PAUSED":
            break
        await asyncio.sleep(.01)
    assert manager.status(request.task_id) == "PAUSED"
    assert manager.session_busy("chat")
    assert writes == ["write"]
    assert manager._budgets[request.task_id].budget.tokens == 120
    assert store.load_budget_snapshot(request.task_id)["tokens"] == 120
    assert store.load_budget_snapshot(request.task_id)["paused"] is True
    # A paused app/chat execution still owns its maintenance lease. New work
    # is rejected before reserving a model/budget/status; resuming keeps it.
    from app.task_support.admission import MaintenanceBusy
    assert manager.admission.pause()["active"] == 1
    rejected = TaskRequest("blocked", session_id="other")
    with pytest.raises(MaintenanceBusy):
        await manager.submit(rejected)
    assert rejected.task_id is None
    assert manager.admission.status()["active"] == 1
    manager.resume_budget(request.task_id, 200)
    await asyncio.wait_for(execution, 2)
    assert writes == ["write", "write"]
    assert manager.status(request.task_id) == "DONE"
    assert manager.admission.status()["active"] == 0
    assert {e["task_id"] for e in events} == {request.task_id}
    store.close()
    reopened = TaskStore(tmp_path / "tasks.db")
    assert reopened.get_budget_settings(200_000) == {"max_tokens": None}
    reopened.close()


def test_chat_budget_validation():
    from app.server.routes.chat import ChatRequest, _task_request
    from pydantic import ValidationError
    for value in [0, -1, 1.5, True, "200"]:
        with pytest.raises(ValidationError):
            ChatRequest(text="hi", task_budget={"max_tokens": value})
    assert _task_request(ChatRequest(text="hi")).task_budget is None
    assert _task_request(ChatRequest(text="hi", task_budget={"max_tokens": None})).task_budget == {"max_tokens": None}


@pytest.mark.asyncio
async def test_real_act_loop_preserves_completed_and_pending_tool_calls(monkeypatch):
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatResult, ChatGeneration
    from langchain_core.tools import StructuredTool
    from app.runtime.v2.loop import run_act_loop
    from app.llm.budget_callback import instrument_model_for_budget
    writes = []
    class Model(BaseChatModel):
        calls: int = 0
        @property
        def _llm_type(self):
            return "budget-test"
        def bind_tools(self, tools, **kwargs):
            return self
        def _generate(self, messages, **kwargs):
            raise AssertionError("async only")
        async def _agenerate(self, messages, **kwargs):
            self.calls += 1
            msg = AIMessage(content="done" if self.calls == 3 else "", usage_metadata={"input_tokens": 20, "output_tokens": 80, "total_tokens": 100},
                tool_calls=[] if self.calls == 3 else [{"id": str(self.calls), "name": "write", "args": {}}])
            return ChatResult(generations=[ChatGeneration(message=msg)])
    model = instrument_model_for_budget(Model())
    monkeypatch.setattr("app.llm.budget_callback.count_tokens", lambda _: 10)
    rt = BudgetRuntime("real-loop", TraceBus(), Budget(50, 150))
    token = set_budget_runtime(rt)
    tool = StructuredTool.from_function(lambda: writes.append("write") or "ok", name="write", description="test")
    execution = asyncio.create_task(run_act_loop(model, [tool], [HumanMessage(content="write twice")]))
    try:
        for _ in range(100):
            if rt.paused:
                break
            await asyncio.sleep(.01)
        assert rt.paused
        assert model.calls == 2
        assert writes == ["write"]
        rt.resume(500)
        result = await asyncio.wait_for(execution, 2)
        assert writes == ["write", "write"]
        assert model.calls == 3
        assert rt.budget.tokens == 300
        assert result[-1].content == "done"
    finally:
        execution.cancel()
        reset_budget_runtime(token)


def test_partial_stream_error_counts_prompt_and_partial_output(monkeypatch):
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration
    monkeypatch.setattr("app.llm.budget_callback.count_tokens", lambda _: 10)
    rt = BudgetRuntime("partial", TraceBus(), Budget(50, None))
    token = set_budget_runtime(rt)
    cb = BudgetTokenCallback()
    run_id = uuid4()
    try:
        cb.on_chat_model_start({}, [[HumanMessage(content="test")]], run_id=run_id)
        cb.on_llm_error(RuntimeError("stream broke"), run_id=run_id,
            response=LLMResult(generations=[[ChatGeneration(message=AIMessage(content="partial"))]]))
        assert rt.budget.tokens == 20
    finally:
        reset_budget_runtime(token)


@pytest.mark.asyncio
async def test_budget_api_lists_and_resumes_only_live_paused_tasks(tmp_path):
    import httpx
    from fastapi import FastAPI
    from app.server.routes.chat import router
    from app.orchestrator.task_manager import TaskManager
    from app.orchestrator.task_store import TaskStore
    store = TaskStore(tmp_path / "tasks.db")
    manager = TaskManager(None, [], TraceBus(), task_store=store)
    app = FastAPI()
    app.state.task_manager = manager
    app.include_router(router)
    manager._set_status("remote", "PAUSED", source="lark", text="task title")
    rt = BudgetRuntime("remote", manager.bus, Budget(50, 100), paused=True)
    rt.budget.tokens = 120
    manager._budgets["remote"] = rt
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/budget/settings")).json() == {"max_tokens": 200000}
        assert (await client.put("/api/budget/settings", json={"max_tokens": None})).status_code == 200
        assert (await client.get("/api/budget/settings")).json() == {"max_tokens": None}
        assert (await client.put("/api/budget/settings", json={"max_tokens": 0})).status_code == 422
        waiting = (await client.get("/api/budget/paused")).json()
        assert waiting["tasks"][0]["task_id"] == "remote"
        assert (await client.post("/api/chat/remote/budget/resume", json={"max_tokens": 100})).status_code == 409
        assert (await client.post("/api/chat/remote/budget/resume", json={"max_tokens": None})).status_code == 200
        assert rt.budget.tokens == 120
        assert (await client.get("/api/budget/paused")).json() == {"tasks": []}
        assert (await client.post("/api/chat/missing/budget/resume", json={"max_tokens": None})).status_code == 409
    store.close()


def test_restart_does_not_reset_schedule_budget_or_replay_a_paused_task(tmp_path):
    from app.orchestrator.task_manager import TaskManager, TaskRequest
    from app.orchestrator.task_store import TaskStore
    store = TaskStore(tmp_path / "tasks.db")
    store.save_budget_snapshot("active", {"max_tokens": 300000, "tokens": 250000, "steps": 2, "paused": False})
    store.save_budget_snapshot("paused", {"max_tokens": 200000, "tokens": 210000, "steps": 2, "paused": True})
    manager = TaskManager(None, [], TraceBus(), task_store=store)
    request = TaskRequest("resume", task_id="active", source="schedule", resume_execution=True)
    manager.prepare_task(request)
    assert request.budget_snapshot["tokens"] == 250000
    assert request.budget_snapshot["max_tokens"] == 300000
    with pytest.raises(ValueError, match="重启"):
        manager.prepare_task(TaskRequest("resume", task_id="paused", source="schedule", resume_execution=True))
    store.close()


@pytest.mark.asyncio
async def test_cancelling_paused_manager_releases_busy_session(monkeypatch):
    from app.orchestrator.task_manager import TaskManager, TaskRequest
    async def graph(task, graph, bus, *, budget_runtime, **kwargs):
        await budget_runtime.admit("model", 1000)
        raise AssertionError("Cancelled task must not run")
        yield {}
    monkeypatch.setattr("app.orchestrator.task_manager.run_graph", graph)
    manager = TaskManager(None, [], TraceBus(), max_total_tokens=100)
    request = TaskRequest("test", task_id="cancel", session_id="chat")
    async def run():
        return [event async for event in manager.handle(request)]
    execution = asyncio.create_task(run())
    for _ in range(50):
        if manager._tasks.get("cancel", {}).get("status") == "PAUSED":
            break
        await asyncio.sleep(.01)
    assert manager.status("cancel") == "PAUSED"
    assert manager.cancel("cancel")
    events = await asyncio.wait_for(execution, 1)
    assert events[-1]["status"] == "cancelled"
    assert manager.status("cancel") == "CANCELLED"
    assert not manager.session_busy("chat")
    assert not manager.paused_budgets()
