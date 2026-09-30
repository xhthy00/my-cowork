import httpx
import asyncio
import pytest
from fastapi import FastAPI
from langchain_core.messages import AIMessage, HumanMessage

from app.llm.model_config import ModelConfig, ModelRegistry
from app.orchestrator.task_manager import TaskManager, TaskRequest, TaskRuntime
from app.observability.trace import TraceBus
from app.runtime.v2.session import SessionStore
from app.server.routes import context, model_registry
from app.task_support.admission import MaintenanceBusy
from starlette.responses import JSONResponse


def setup(tmp_path, monkeypatch, model):
    store = SessionStore(tmp_path / "sessions.db")
    original = [HumanMessage("早期目标 " * 5000), AIMessage("answer"), HumanMessage("现在的问题"), AIMessage("latest")]
    store.save("s", original)
    registry = ModelRegistry()
    registry.replace([ModelConfig(id="a", provider="openai_compat", model="a", api_key="never-echo-this-key")], "a")
    manager = TaskManager(graph=None, tools=[], bus=TraceBus(), model_registry=registry, runtime_factory=lambda c, m: TaskRuntime(None, model, c))
    app = FastAPI()
    app.state.task_manager = manager
    app.add_exception_handler(MaintenanceBusy, lambda request, error: JSONResponse({"detail": str(error)}, status_code=503))
    app.include_router(context.router)
    app.include_router(model_registry.router)
    monkeypatch.setattr(context, "get_session_store", lambda: store)
    monkeypatch.setattr(context, "create_configured_model", lambda _: model)
    return app, store, manager


@pytest.mark.asyncio
async def test_compaction_counts_for_maintenance_and_rejects_new_work(tmp_path, monkeypatch):
    entered, finish = asyncio.Event(), asyncio.Event()
    class Model:
        async def ainvoke(self, messages):
            entered.set()
            await finish.wait()
            return AIMessage("摘要")
    app, store, manager = setup(tmp_path, monkeypatch, Model())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        running = asyncio.create_task(client.post("/api/context/compact", json={"session_id": "s"}))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            assert manager.admission.pause()["active"] == 1
            denied = await client.post("/api/context/compact", json={"session_id": "other"})
            assert denied.status_code == 503
            assert manager.compacting_sessions == {"s"}
            finish.set()
            assert (await running).status_code == 200
            assert manager.admission.status()["active"] == 0
        finally:
            finish.set()
            running.cancel()
            await asyncio.gather(running, return_exceptions=True)


@pytest.mark.asyncio
async def test_compact_is_a_real_command_and_preserves_transcript(tmp_path, monkeypatch):
    class Model:
        async def ainvoke(self, messages):
            return AIMessage("保留目标、决定和未完成事项。")
    app, store, manager = setup(tmp_path, monkeypatch, Model())
    original = store.load("s")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/api/context/compact", json={"session_id": "s", "focus": "保留目标"})
        assert response.status_code == 200, response.text
        assert response.json()["tokens"] < response.json()["before_tokens"]
        assert store.load("s") == original
        usage = (await client.get("/api/context", params={"session_id": "s"})).json()
        assert usage["tokens"] == response.json()["tokens"]
    assert not manager.compacting_sessions
    assert manager.admission.status()["active"] == 0


@pytest.mark.asyncio
async def test_changed_session_rejects_snapshot_and_blocks_new_task_during_compaction(tmp_path, monkeypatch):
    class Model:
        async def ainvoke(self, messages):
            with pytest.raises(ValueError, match="正在压缩"):
                manager.prepare_task(TaskRequest("new", session_id="s"))
            store.save("s", [HumanMessage("changed")])
            return AIMessage("摘要")
    app, store, manager = setup(tmp_path, monkeypatch, Model())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/api/context/compact", json={"session_id": "s"})
    assert response.status_code == 409
    assert store.load_compaction("s") is None
    assert manager.admission.status()["active"] == 0
    assert not manager.compacting_sessions


@pytest.mark.asyncio
async def test_busy_session_and_authenticated_registry(tmp_path, monkeypatch):
    app, store, manager = setup(tmp_path, monkeypatch, None)
    manager.prepare_task(TaskRequest("reserved", task_id="one", session_id="s"))
    monkeypatch.setenv("MY_COWORK_MODEL_TOKEN", "internal-token")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        assert (await client.post("/api/context/compact", json={"session_id": "s"})).status_code == 409
        bad = {"models": [{"id": "b", "api_key": "never-echo-this-key"}]}
        assert (await client.post("/api/internal/models", json=bad)).status_code == 403
        response = await client.post("/api/internal/models", json=bad, headers={"x-model-token": "internal-token"})
        assert response.status_code == 400
        assert "never-echo-this-key" not in response.text
        assert manager.model_registry.resolve().id == "a"


@pytest.mark.asyncio
async def test_cancelled_compaction_keeps_original_state_and_releases_session(tmp_path, monkeypatch):
    import asyncio
    class Model:
        async def ainvoke(self, messages):
            raise asyncio.CancelledError()
    app, store, manager = setup(tmp_path, monkeypatch, Model())
    original = store.load("s")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        with pytest.raises(asyncio.CancelledError):
            await client.post("/api/context/compact", json={"session_id": "s"})
    assert store.load("s") == original
    assert store.load_compaction("s") is None
    assert manager.admission.status()["active"] == 0
    assert not manager.compacting_sessions


@pytest.mark.asyncio
async def test_compact_uses_conversation_reasoning_and_rejects_invalid_choice(tmp_path, monkeypatch):
    class Model:
        async def ainvoke(self, messages):
            return AIMessage("保留目标。")
    app, store, manager = setup(tmp_path, monkeypatch, Model())
    manager.model_registry.replace([ModelConfig(id="a", provider="openai_compat", model="a", api_key="test", reasoning_mode="openai-responses", reasoning_effort="low", allowed_efforts=("low", "high"))], "a")
    captured = []
    monkeypatch.setattr(context, "create_configured_model", lambda config: captured.append(config) or Model())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        bad = await client.post("/api/context/compact", json={"session_id": "s", "reasoning": {"effort": "max"}})
        assert bad.status_code == 400
        assert not captured
        response = await client.post("/api/context/compact", json={"session_id": "s", "reasoning": {"effort": "high"}})
        assert response.status_code == 200
    assert captured[0].reasoning_effort == "high"


@pytest.mark.asyncio
async def test_context_usage_follows_target_model_without_modifying_cached_summary(tmp_path, monkeypatch):
    from app.llm.token_counter import count_tokens
    app, store, manager = setup(tmp_path, monkeypatch, None)
    manager.model_registry.replace([
        ModelConfig(id="small", provider="openai_compat", model="small", api_key="", context_window=5000, output_limit=1000),
        ModelConfig(id="big", provider="openai_compat", model="big", api_key="", context_window=100000, output_limit=1000),
    ], "small")
    cached = {"boundary_index": 2, "summary_text": "brief", "input_budget": 2976}
    store.save_compaction("s", cached)
    original = store.load("s")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        small = (await client.get("/api/context", params={"session_id": "s", "model_profile_id": "small"})).json()
        big = (await client.get("/api/context", params={"session_id": "s", "model_profile_id": "big"})).json()
    assert small["compacted"] and not big["compacted"]
    assert big["tokens"] == count_tokens(original) > small["tokens"]
    assert store.load_compaction("s") == cached
    assert store.load("s") == original
