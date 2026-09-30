import asyncio

import pytest

from app.llm.model_config import ModelConfig, ModelRegistry, model_scope, current_model_config
from app.llm.budget_context import context_window_limit


def config(id="a", **overrides):
    return ModelConfig(id=id, provider="openai_compat", model=id, api_key="fake-key", **overrides)


def test_registry_replacement_keeps_existing_snapshot_and_clears_default():
    registry = ModelRegistry()
    registry.replace([config(context_window=64000)], "a")
    original = registry.resolve()
    registry.replace([config("b", context_window=128000)], "b")
    assert registry.resolve().model == "b"
    assert original.model == "a"
    registry.replace([], None)
    with pytest.raises(ValueError, match="模型"):
        registry.resolve()
    assert "fake-key" not in repr(original)


@pytest.mark.asyncio
async def test_interleaved_tasks_keep_separate_context_limits():
    ready = asyncio.Event()
    async def first():
        with model_scope(config(context_window=64000)):
            ready.set()
            await asyncio.sleep(0.02)
            assert context_window_limit() == 64000
    async def second():
        await ready.wait()
        with model_scope(config("b", context_window=128000)):
            await asyncio.sleep(0)
            assert context_window_limit() == 128000
    await asyncio.gather(first(), second())
    assert current_model_config() is None


def test_registry_validates_before_replacing():
    registry = ModelRegistry()
    registry.replace([config()], "a")
    with pytest.raises(ValueError):
        registry.replace([config("b")], "missing")
    assert registry.resolve().id == "a"


@pytest.mark.asyncio
async def test_task_switch_does_not_change_running_graph_or_planner(monkeypatch):
    from app.observability.trace import TraceBus
    from app.orchestrator.task_manager import TaskManager, TaskRequest, TaskRuntime
    import app.orchestrator.task_manager as manager_module
    registry = ModelRegistry()
    registry.replace([config(context_window=64000), config("b", context_window=128000)], "a")
    entered = asyncio.Event()
    release = asyncio.Event()
    seen = []
    async def run(task, graph, bus, **kwargs):
        if task.task_id == "first":
            entered.set()
            await release.wait()
        seen.append((task.task_id, graph, kwargs["planner_llm"], context_window_limit()))
        event = {"type": "graph.end", "task_id": task.task_id, "status": "ok"}
        bus.emit(event)
        yield event
    monkeypatch.setattr(manager_module, "run_graph", run)
    tm = TaskManager(graph="legacy", tools=[], bus=TraceBus(),
        model_registry=registry,
        runtime_factory=lambda choice, mode: TaskRuntime(choice.model, choice.model, choice))
    await tm.submit(TaskRequest(text="one", task_id="first"))
    await entered.wait()
    registry.replace([config("b", context_window=128000)], "b")
    await tm.submit(TaskRequest(text="two", task_id="second"))
    release.set()
    for _ in range(100):
        if len(seen) == 2:
            break
        await asyncio.sleep(0.01)
    assert sorted(seen) == [("first", "a", "a", 64000), ("second", "b", "b", 128000)]


def test_resume_after_restart_uses_persisted_nonsecret_snapshot(tmp_path):
    from app.orchestrator.task_store import TaskStore
    from app.orchestrator.task_manager import TaskManager, TaskRequest, TaskRuntime
    from app.observability.trace import TraceBus
    store = TaskStore(tmp_path / "tasks.db")
    registry = ModelRegistry()
    registry.replace([config(context_window=64000)], "a")
    def manager():
        return TaskManager(graph=None, tools=[], bus=TraceBus(), task_store=store, model_registry=registry, runtime_factory=lambda c, m: TaskRuntime(c.id, c.id, c))
    first = manager()
    first.prepare_task(TaskRequest("first", task_id="same", source="schedule"))
    registry.replace([config(context_window=128000), config("b")], "b")
    resumed = TaskRequest("resume", task_id="same", source="schedule", resume_execution=True)
    manager().prepare_task(resumed)
    assert resumed.runtime.config.context_window == 64000
    assert resumed.runtime.config.id == "a"
    assert "api_key" not in store.load_model_snapshot("same")
    assert b"fake-key" not in (tmp_path / "tasks.db").read_bytes()
