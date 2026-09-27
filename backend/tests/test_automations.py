"""Scheduled tasks: persistence, catch-up, overlap, execution and REST."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.automation import Automation, AutomationRun, AutomationScheduler, AutomationStore, Schedule, next_fire_time
from app.automation.runtime import AutomationRunner
from app.automation.migration import import_skill_schedules
from app.automation.migration import _from_trigger
from apscheduler.triggers.cron import CronTrigger
from app.automation.tools import make_automation_tools
from app.guardrails.approval import ConfirmHub, reset_automation_policy, set_automation_policy, valid_automation_grants
from app.runtime.todo_context import TodoRuntime, get_todo_runtime, reset_todo_runtime, set_todo_runtime
from app.server.routes.automations import router


def _task(**changes) -> Automation:
    base = dict(title="Daily brief", instructions="Write a brief",
                schedule=Schedule(kind="cron", cron="0 9 * * *", timezone="UTC"))
    base.update(changes)
    return Automation(**base)


def test_store_crud_schedule_and_run_history(tmp_path):
    store = AutomationStore(tmp_path / "automations.db")
    task = store.save(_task())
    assert store.get(task.id).title == "Daily brief"
    assert store.list()[0].next_run == task.next_run
    store.mark_seen(task.id)
    assert store.get(task.id).next_run == task.next_run
    run = store.claim(task.id, trigger="manual")
    assert run and run.session_id == f"__run__{run.run_id}"
    assert store.get(task.id).next_run == task.next_run  # manual must not postpone cron
    store.append_event(run.run_id, {"type": "graph.end", "summary": "Done"})
    run.status, run.result_text = "ok", "Done"
    store.finish(run)
    store.finish(run)  # terminal writes must be idempotent
    assert store.get(task.id).run_count == 1
    assert store.runs(task.id)[0].result_text == "Done"
    assert store.events(run.run_id)[0]["type"] == "graph.end"
    assert store.delete(task.id)
    assert not store.runs(task.id)
    store.close()


def test_once_and_timezone_validation():
    now = datetime.now(timezone.utc)
    schedule = Schedule(kind="once", fire_at=(now + timedelta(hours=2)).isoformat(), timezone="UTC")
    assert next_fire_time(schedule) is not None
    assert next_fire_time(schedule, run_count=1) is None
    monday = datetime(2026, 9, 28, tzinfo=timezone.utc)
    monday_fire = next_fire_time(Schedule(kind="cron", cron="0 9 * * 1", timezone="UTC"), after=monday.timestamp())
    sunday_fire = next_fire_time(Schedule(kind="cron", cron="0 9 * * 0", timezone="UTC"), after=monday.timestamp())
    assert datetime.fromtimestamp(monday_fire, timezone.utc).weekday() == 0
    assert datetime.fromtimestamp(sunday_fire, timezone.utc).weekday() == 6
    weekdays = next_fire_time(Schedule(kind="cron", cron="0 9 * * 1-5", timezone="UTC"), after=monday.timestamp())
    assert datetime.fromtimestamp(weekdays, timezone.utc).weekday() == 0
    alternate = next_fire_time(Schedule(kind="cron", cron="0 9 * * */2,1", timezone="UTC"), after=monday.timestamp())
    assert datetime.fromtimestamp(alternate, timezone.utc).weekday() == 0
    either_day = next_fire_time(Schedule(kind="cron", cron="0 9 1 * 1", timezone="UTC"),
                                 after=datetime(2026, 9, 29, tzinfo=timezone.utc).timestamp())
    assert datetime.fromtimestamp(either_day, timezone.utc).date().isoformat() == "2026-10-01"
    with pytest.raises(ValueError, match="timezone"):
        Schedule(kind="cron", cron="0 9 * * *", timezone="No/Such_Zone").validate()


def test_skill_schedule_import_is_idempotent(tmp_path):
    skill_root = tmp_path / "skills"
    item = skill_root / "daily"
    item.mkdir(parents=True)
    (item / "skill.yaml").write_text("id: daily\nname: Daily\nschedule: '0 9 * * *'\nprompt: Run report\n", encoding="utf-8")
    store = AutomationStore(tmp_path / "automations.db")
    assert import_skill_schedules(store, root=skill_root, config_path=tmp_path / "config.json") == 1
    assert import_skill_schedules(store, root=skill_root, config_path=tmp_path / "config.json") == 0
    task = store.get("skill:daily")
    assert task and task.instructions == "Run report" and task.workspace
    store.close()


def test_legacy_apscheduler_weekday_keeps_its_original_day():
    legacy = CronTrigger.from_crontab("0 9 * * 0", timezone="UTC")  # APScheduler: Monday
    imported = _from_trigger(legacy)
    assert imported.cron == "0 9 * * mon"
    after = datetime(2026, 9, 27, tzinfo=timezone.utc).timestamp()
    fire = next_fire_time(imported, after=after)
    assert datetime.fromtimestamp(fire, timezone.utc).weekday() == 0


@pytest.mark.asyncio
async def test_checkpoint_resumes_pending_question_without_repeating_completed_tool(tmp_path, monkeypatch):
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
    from langchain_core.tools import tool

    from app.guardrails.human_input import HumanInputHub
    from app.runtime.v2 import session as session_module
    from app.runtime.v2.loop import run_act_loop

    monkeypatch.setattr(session_module, "_STORE", session_module.SessionStore(tmp_path / "sessions.db"))
    side_effects: list[str] = []
    prompts: list[dict] = []
    model_calls = 0

    class FakeModel:
        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, messages):
            nonlocal model_calls
            model_calls += 1
            if not any(isinstance(msg, ToolMessage) for msg in messages):
                return AIMessage(content="", tool_calls=[
                    {"id": "call-write", "name": "save_report", "args": {"text": "saved"}},
                    {"id": "call-ask", "name": "ask_choice", "args": {"question": "Which format?"}},
                ])
            assert {msg.tool_call_id for msg in messages if isinstance(msg, ToolMessage)} == {"call-write", "call-ask"}
            return AIMessage(content="Finished in Markdown")

    @tool
    async def save_report(text: str) -> str:
        """Save a report."""
        side_effects.append(text)
        return "saved"

    hub = HumanInputHub(prompts.append, tmp_path / "questions.db")

    @tool
    async def ask_choice(question: str) -> str:
        """Ask a human for a choice."""
        runtime = get_todo_runtime()
        return await runtime.human_input_hub.ask(runtime.task_id, "single_agent", question)

    async def execute(current_hub, *, resume: bool):
        prior = session_module.load_thread("__run__checkpoint") if resume else []
        messages = [SystemMessage(content="test"), *prior] if prior else [HumanMessage(content="Write a report")]
        token = set_todo_runtime(TodoRuntime(
            task_id="execution-1", bus=None, source="schedule", session_id="__run__checkpoint",
            human_input_hub=current_hub, resume_execution=resume,
        ))
        try:
            return await run_act_loop(FakeModel(), [save_report, ask_choice], messages)
        finally:
            reset_todo_runtime(token)

    first = asyncio.create_task(execute(hub, resume=False))
    for _ in range(100):
        if prompts:
            break
        await asyncio.sleep(0.01)
    assert prompts and side_effects == ["saved"]
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    checkpoint = session_module.load_thread("__run__checkpoint")
    assert any(isinstance(msg, ToolMessage) and msg.tool_call_id == "call-write" for msg in checkpoint)
    assert not any(isinstance(msg, ToolMessage) and msg.tool_call_id == "call-ask" for msg in checkpoint)

    next_hub = HumanInputHub(prompts.append, tmp_path / "questions.db")
    resumed = asyncio.create_task(execute(next_hub, resume=True))
    for _ in range(100):
        if len(prompts) > 1:
            break
        await asyncio.sleep(0.01)
    assert len(prompts) > 1
    assert next_hub.reply("execution-1", prompts[-1]["question_id"], "Markdown")
    result = await asyncio.wait_for(resumed, 2)
    assert isinstance(result[-1], AIMessage) and result[-1].content == "Finished in Markdown"
    assert side_effects == ["saved"] and model_calls == 2


@pytest.mark.asyncio
async def test_workforce_resume_uses_graph_checkpoint_without_reasking_plan(monkeypatch):
    from langchain_core.messages import AIMessage

    from app.observability.trace import TraceBus
    from app.runtime import graph_runner

    async def should_not_replan(*_args, **_kwargs):
        raise AssertionError("Recovered worker must not ask to approve its plan again")

    monkeypatch.setattr(graph_runner, "decompose_subtasks", should_not_replan)
    subtasks = [{"id": "step-1", "content": "Write summary", "status": "completed", "result": "done"}]

    class FakeGraph:
        def __init__(self):
            self.input = "unseen"

        async def aget_state(self, _config):
            return SimpleNamespace(values={"messages": [], "subtasks": subtasks}, next=("synthesize",))

        async def astream(self, value, **_kwargs):
            self.input = value
            yield {"synthesize": {"messages": [AIMessage(content="Recovered result")]}}

    graph = FakeGraph()
    task = SimpleNamespace(task_id="resume-graph", text="Write summary", source="schedule",
                           session_mode="workforce", session_id="run-session", resume_execution=True,
                           memory_enabled=False)
    events = [event async for event in graph_runner.run_graph(task, graph, TraceBus())]
    assert graph.input is None
    assert any(event.get("type") == "graph.end" and event.get("summary") == "Recovered result"
               for event in events)

    class CompletedGraph(FakeGraph):
        async def aget_state(self, _config):
            return SimpleNamespace(values={"messages": [AIMessage(content="Saved final")],
                                           "subtasks": subtasks}, next=())

        async def astream(self, value, **_kwargs):
            self.input = value
            if False:
                yield {}

    completed = CompletedGraph()
    events = [event async for event in graph_runner.run_graph(task, completed, TraceBus())]
    assert completed.input is None
    assert any(event.get("type") == "graph.end" and event.get("summary") == "Saved final"
               for event in events)


def test_due_claim_overlap_and_recovery(tmp_path):
    store = AutomationStore(tmp_path / "automations.db")
    task = store.save(_task(schedule=Schedule(kind="interval", interval_seconds=60)))
    task.next_run = 1.0
    store.save(task, preserve_next_run=True)
    run = store.claim(task.id, trigger="catchup")
    assert run and run.scheduled_for == 1.0
    assert store.get(task.id).next_run > 1.0
    # Force a due occurrence while the first run is still active.
    task = store.get(task.id)
    task.next_run = 2.0
    store.save(task, preserve_next_run=True)
    assert store.claim(task.id, trigger="schedule") is None
    assert any(item.status == "skipped" for item in store.runs(task.id))
    recovered = store.recover_interrupted()
    assert len(recovered) == 1 and recovered[0].run_id == run.run_id
    assert store.get_run(run.run_id).status == "running"
    assert store.get_run(run.run_id).resume_count == 1
    assert store.get(task.id).next_run > 2.0
    # The original run is reserved for recovery, so no second run can overlap it.
    task = store.get(task.id)
    task.next_run = 3.0
    store.save(task, preserve_next_run=True)
    assert store.claim(task.id, trigger="catchup") is None
    store.close()


def test_inflight_write_waits_for_recovery_review(tmp_path, monkeypatch):
    from langchain_core.messages import ToolMessage

    from app.runtime.v2 import session as session_module

    monkeypatch.setattr(session_module, "_STORE", session_module.SessionStore(tmp_path / "sessions.db"))
    store = AutomationStore(tmp_path / "automations.db")
    task = store.save(_task())
    run = store.claim(task.id, trigger="manual")
    key = run.session_id
    store.tool_started(run.run_id, "send-1", "lark_send_message", key)
    assert store.recover_interrupted() == []
    paused = store.get_run(run.run_id)
    assert paused.status == "recovery_review"
    assert paused.recovery_tools == [{"tool": "lark_send_message", "call_id": "send-1"}]
    assert store.claim(task.id, trigger="manual") is None

    # If the result was durably checkpointed just before a crash, it is safe to resume.
    another = store.claim(store.save(_task()).id, trigger="manual")
    store.tool_started(another.run_id, "write-1", "fs.write", another.session_id)
    session_module.save_thread(another.session_id, [ToolMessage(content="written", tool_call_id="write-1")])
    recovered = store.recover_interrupted()
    assert [item.run_id for item in recovered] == [another.run_id]
    assert store.unfinished_tools(another.run_id) == []
    recovered[0].status = "ok"
    store.finish(recovered[0])
    human_task = store.save(_task())
    human_run = store.claim(human_task.id, trigger="manual")
    store.tool_started(human_run.run_id, "ask-1", "ask_human", human_run.session_id)
    assert [item.run_id for item in store.recover_interrupted()] == [human_run.run_id]
    assert store.get_run(human_run.run_id).status == "running"
    store.close()


@pytest.mark.asyncio
async def test_scheduler_runs_due_independently(tmp_path):
    store = AutomationStore(tmp_path / "automations.db")
    first = store.save(_task(schedule=Schedule(kind="interval", interval_seconds=60)))
    second = store.save(_task(title="Other", schedule=Schedule(kind="interval", interval_seconds=60)))
    for task in (first, second):
        task.next_run = 1.0
        store.save(task, preserve_next_run=True)
    seen: list[str] = []
    done = asyncio.Event()

    async def runner(task: Automation, run: AutomationRun):
        seen.append(task.id)
        run.status = "ok"
        store.finish(run)
        if len(seen) == 2:
            done.set()
        return run

    scheduler = AutomationScheduler(store, runner)
    await scheduler.tick(trigger="catchup")
    await asyncio.wait_for(done.wait(), 2)
    assert set(seen) == {first.id, second.id}
    assert all(store.get(task.id).run_count == 1 for task in (first, second))
    await scheduler.stop()
    store.close()


@pytest.mark.asyncio
async def test_cancelled_run_does_not_catch_up_again(tmp_path):
    store = AutomationStore(tmp_path / "automations.db")
    task = store.save(_task(schedule=Schedule(kind="interval", interval_seconds=60)))
    task.next_run = 1.0
    store.save(task, preserve_next_run=True)
    started = asyncio.Event()

    async def runner(_task, run):
        started.set()
        await asyncio.Event().wait()
        return run

    scheduler = AutomationScheduler(store, runner)
    await scheduler.tick(trigger="catchup")
    await asyncio.wait_for(started.wait(), 2)
    run = store.runs(task.id)[0]
    assert await scheduler.cancel_run(run.run_id)
    assert store.get_run(run.run_id).status == "cancelled"
    assert store.get(task.id).next_run > 1.0
    await scheduler.stop()
    store.close()


@pytest.mark.asyncio
async def test_scheduler_restarts_the_same_unfinished_run(tmp_path):
    store = AutomationStore(tmp_path / "automations.db")
    task = store.save(_task(schedule=Schedule(kind="interval", interval_seconds=60)))
    run = store.claim(task.id, trigger="manual")
    started = asyncio.Event()

    async def suspended(_task, _run):
        started.set()
        await asyncio.Event().wait()

    first = AutomationScheduler(store, suspended)
    first._spawn(task.id, run)
    await asyncio.wait_for(started.wait(), 2)
    await first.stop()
    assert store.get_run(run.run_id).finished_at is None
    resumed_runs = []
    finished = asyncio.Event()

    async def complete(_task, recovered):
        resumed_runs.append(recovered)
        recovered.status = "ok"
        store.finish(recovered)
        finished.set()
        return recovered

    second = AutomationScheduler(store, complete)
    second.start()
    await asyncio.wait_for(finished.wait(), 2)
    assert len(resumed_runs) == 1
    assert resumed_runs[0].run_id == run.run_id and resumed_runs[0].resume_count == 1
    assert len(store.runs(task.id)) == 1
    await second.stop()
    store.close()


@pytest.mark.asyncio
async def test_reviewed_run_can_resume_or_be_cancelled(tmp_path):
    store = AutomationStore(tmp_path / "automations.db")
    task = store.save(_task())
    run = store.claim(task.id, trigger="manual")
    store.tool_started(run.run_id, "send-1", "lark_send_message", run.session_id)
    assert store.recover_interrupted() == []
    finished = asyncio.Event()

    async def runner(_task, resumed):
        assert resumed.run_id == run.run_id and resumed.resume_count == 1
        resumed.status = "ok"
        store.finish(resumed)
        finished.set()
        return resumed

    scheduler = AutomationScheduler(store, runner)
    assert scheduler.resume_reviewed(run.run_id) is not None
    await asyncio.wait_for(finished.wait(), 2)
    assert store.get_run(run.run_id).status == "ok"

    second = store.claim(task.id, trigger="manual")
    store.tool_started(second.run_id, "write-1", "fs.write", second.session_id)
    assert store.recover_interrupted() == []
    assert await scheduler.cancel_run(second.run_id)
    assert store.get_run(second.run_id).status == "cancelled"
    await scheduler.stop()
    store.close()


@pytest.mark.asyncio
async def test_runner_persists_terminal_result(tmp_path):
    store = AutomationStore(tmp_path / "automations.db")
    task = store.save(_task())
    run = store.claim(task.id, trigger="manual")

    class FakeManager:
        async def handle(self, request):
            assert request.task_id == run.task_execution_id
            assert request.session_id == run.session_id
            assert request.space_id == task.id
            assert request.space_root_path == task.workspace
            yield {"type": "artifact.file", "path": "/tmp/report.md"}
            yield {"type": "graph.end", "status": "done", "summary": "Finished"}

    await AutomationRunner(store, FakeManager())(task, run)
    saved = store.get_run(run.run_id)
    assert saved.status == "ok" and saved.result_text == "Finished"
    assert saved.artifacts == ["/tmp/report.md"]
    assert len(store.events(run.run_id)) == 2
    store.close()


@pytest.mark.asyncio
async def test_runner_sends_optional_lark_completion_notice(tmp_path, monkeypatch):
    from app.tools.builtin.lark import send_message

    store = AutomationStore(tmp_path / "automations.db")
    task = store.save(_task(notify_target="lark:chat-123"))
    run = store.claim(task.id, trigger="manual")
    sent = []

    async def fake_send(chat_id, text):
        sent.append((chat_id, text))
        return "message-1"

    class FakeManager:
        async def handle(self, _request):
            yield {"type": "graph.end", "status": "done", "summary": "Finished"}

    monkeypatch.setattr(send_message, "send", fake_send)
    await AutomationRunner(store, FakeManager())(task, run)
    assert sent == [("chat-123", "✓ Daily brief\n\nFinished")]
    assert store.get_run(run.run_id).notification_error is None
    store.close()


def test_rest_create_edit_run_delete(tmp_path):
    store = AutomationStore(tmp_path / "automations.db")

    async def runner(_task, run):
        run.status = "ok"
        store.finish(run)
        return run

    app = FastAPI()
    app.include_router(router)
    app.state.automations = store
    app.state.automation_scheduler = AutomationScheduler(store, runner)
    with TestClient(app) as client:
        created = client.post("/api/automations", json={
            "title": "Morning brief", "instructions": "Write a brief",
            "schedule": {"kind": "cron", "cron": "0 9 * * *", "timezone": "UTC"},
        })
        assert created.status_code == 201
        task_id = created.json()["task"]["id"]
        assert len(client.get("/api/automations").json()["tasks"]) == 1
        assert client.patch(f"/api/automations/{task_id}", json={"enabled": False}).json()["task"]["enabled"] is False
        run = client.post(f"/api/automations/{task_id}/run")
        assert run.status_code == 202
        run_id = run.json()["run"]["run_id"]
        assert client.get(f"/api/automations/{task_id}/runs/{run_id}").status_code == 200
        # The runner may still be active between requests; deletion is rejected then.
        response = client.delete(f"/api/automations/{task_id}")
        assert response.status_code in (200, 409)
    store.close()


def test_command_allowlist_persists_and_can_be_changed(tmp_path):
    store = AutomationStore(tmp_path / "automations.db")
    app = FastAPI()
    app.include_router(router)
    app.state.automations = store
    app.state.automation_scheduler = AutomationScheduler(store, lambda _task, run: run)
    with TestClient(app) as client:
        created = client.post("/api/automations", json={
            "title": "Check", "instructions": "Run checks",
            "schedule": {"kind": "cron", "cron": "0 9 * * *", "timezone": "UTC"},
            "always_allowed_commands": ["git status --short", "git status --short"],
        })
        assert created.status_code == 201
        task_id = created.json()["task"]["id"]
        assert created.json()["task"]["always_allowed_commands"] == ["git status --short"]
        added = client.patch(f"/api/automations/{task_id}", json={"add_command": "pwd"})
        assert added.json()["task"]["always_allowed_commands"] == ["git status --short", "pwd"]
        revoked = client.patch(f"/api/automations/{task_id}", json={"revoke_command": "git status --short"})
        assert revoked.json()["task"]["always_allowed_commands"] == ["pwd"]
        approved = client.patch(f"/api/automations/{task_id}", json={"auto_approve_commands": True})
        assert approved.json()["task"]["auto_approve_commands"] is True
        assert store.get(task_id).auto_approve_commands is True
        assert client.post("/api/automations", json={
            "title": "Bad", "instructions": "Run checks",
            "schedule": {"kind": "cron", "cron": "0 9 * * *", "timezone": "UTC"},
            "always_allowed_commands": ["pwd\nrm -rf ."],
        }).status_code == 422
    store.close()


@pytest.mark.asyncio
async def test_scheduled_command_grant_requires_exact_command_and_workspace(tmp_path):
    events: list[dict] = []
    hub = ConfirmHub(emit=events.append)
    current = ["git status --short"]
    token = set_automation_policy(str(tmp_path), [], commands=current.copy(),
                                  current_commands=lambda: current.copy())
    try:
        assert await hub.request("allowed", "exec.bash", {"cmd": "git status --short", "cwd": str(tmp_path)})
        assert events == []
        for call_id, args in [
            ("different", {"cmd": "git status --short && echo hi", "cwd": str(tmp_path)}),
            ("other-dir", {"cmd": "git status --short", "cwd": str(tmp_path / "child")}),
        ]:
            waiting = asyncio.create_task(hub.request(call_id, "exec.bash", args))
            await asyncio.sleep(0)
            assert not waiting.done()
            assert hub.resolve(call_id, False)
            assert await waiting is False
        current.clear()
        waiting = asyncio.create_task(hub.request("revoked", "exec.bash", {"cmd": "git status --short", "cwd": str(tmp_path)}))
        await asyncio.sleep(0)
        assert not waiting.done()
        assert hub.resolve("revoked", False)
        assert await waiting is False
    finally:
        reset_automation_policy(token)


@pytest.mark.asyncio
async def test_scheduled_auto_approve_commands_is_workspace_scoped_and_revocable(tmp_path):
    hub = ConfirmHub()
    enabled = True
    token = set_automation_policy(str(tmp_path), [], auto_approve_commands=True,
                                  current_auto_approve_commands=lambda: enabled)
    try:
        assert await hub.request("auto", "exec.bash", {"cmd": "echo dynamic", "cwd": str(tmp_path)})
        assert await hub.request("browser-input", "browser_type", {
            "url": "https://cn.bing.com/", "target": "#sb_form_q", "text_length": 15,
        })
        pending = asyncio.create_task(hub.request("elsewhere", "exec.bash", {"cmd": "echo dynamic", "cwd": str(tmp_path / "child")}))
        await asyncio.sleep(0)
        assert not pending.done()
        assert hub.resolve("elsewhere", False)
        assert await pending is False
        enabled = False
        pending = asyncio.create_task(hub.request("browser-revoked", "browser_type", {
            "url": "https://cn.bing.com/", "target": "#sb_form_q", "text_length": 15,
        }))
        await asyncio.sleep(0)
        assert not pending.done()
        assert hub.resolve("browser-revoked", False)
        assert await pending is False
        pending = asyncio.create_task(hub.request("revoked", "exec.bash", {"cmd": "echo dynamic", "cwd": str(tmp_path)}))
        await asyncio.sleep(0)
        assert not pending.done()
        assert hub.resolve("revoked", False)
        assert await pending is False
    finally:
        reset_automation_policy(token)


def test_main_app_starts_scheduler_and_serves_automations(tmp_path, monkeypatch):
    from app import main
    from app.observability.trace import TraceBus

    store = AutomationStore(tmp_path / "automations.db")

    class FakeManager:
        human_input_hub = None

        async def handle(self, request):
            yield {"type": "graph.end", "status": "ok", "summary": "scheduled result",
                   "task_id": request.task_id}

    monkeypatch.setattr(main, "build_stack", lambda: {
        "task_manager": FakeManager(), "automation_store": store,
        "bus": TraceBus(), "confirm_hub": ConfirmHub(), "data_dir": tmp_path,
    })
    monkeypatch.setenv("MY_COWORK_SKILLS_ROOT", str(tmp_path / "skills"))
    monkeypatch.setenv("MY_COWORK_SKILLS_CONFIG", str(tmp_path / "skills.json"))
    monkeypatch.setenv("MY_COWORK_SCHEDULER_DB", str(tmp_path / "legacy.db"))
    app = main.create_app()
    with TestClient(app) as client:
        assert client.get("/api/automations").status_code == 200
        created = client.post("/api/automations", json={
            "title": "One time", "instructions": "Summarize",
            "schedule": {"kind": "once", "fire_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), "timezone": "UTC"},
        })
        assert created.status_code == 201
        task_id = created.json()["task"]["id"]
        assert client.post(f"/api/automations/{task_id}/run").status_code == 202
        assert client.get(f"/api/automations/{task_id}").status_code == 200


@pytest.mark.asyncio
async def test_agent_creation_requires_approval_and_standing_grants_are_scoped(tmp_path):
    store = AutomationStore(tmp_path / "automations.db")
    seen: list[dict] = []

    class Approver:
        async def request(self, _call_id, _name, args):
            seen.append(args)
            return True

    token = set_todo_runtime(TodoRuntime(task_id="chat-1", bus=None, project_id="project-1"))
    try:
        tools = {tool.name: tool for tool in make_automation_tools(store, Approver())}
        result = await tools["create_scheduled_task"].ainvoke({
            "title": "Daily", "instructions": "Write a report", "cron": "0 9 * * *",
            "permissions": [
                {"tool": "fs.write", "target": "/tmp/exact.txt", "access": "write"},
                {"tool": "exec.bash", "target": "rm -rf /", "access": "write"},
            ],
        })
        assert result["ok"] and seen
        task = store.get(result["id"])
        assert task.project_id == "project-1"
        assert task.always_allowed_tools == [{"tool": "fs.write", "target": "/tmp/exact.txt"}]
    finally:
        reset_todo_runtime(token)

    events: list[dict] = []
    hub = ConfirmHub(emit=events.append)
    policy = set_automation_policy(str(tmp_path), valid_automation_grants([
        {"tool": "fs.write", "target": "/tmp/exact.txt", "access": "write"}
    ]))
    try:
        assert await hub.request("allowed", "fs.write", {"path": str(tmp_path / "report.md")})
        assert await hub.request("exact", "fs.write", {"path": "/tmp/exact.txt"})
        waiting = asyncio.create_task(hub.request("shell", "exec.bash", {"cmd": "echo hi"}))
        await asyncio.sleep(0)
        assert any(event.get("call_id") == "shell" for event in events)
        assert not waiting.done()
        assert hub.resolve("shell", False)
        assert await waiting is False
    finally:
        reset_automation_policy(policy)
    store.close()


@pytest.mark.asyncio
async def test_lark_send_requires_exact_scheduled_target(tmp_path, monkeypatch):
    from app.tools.builtin.lark.tools import make_lark_send_tool
    from app.tools.builtin.lark import tools as lark_module

    sent: list[tuple[str, str]] = []

    async def fake_send(chat_id: str, message: str):
        sent.append((chat_id, message))
        return "message-1"

    monkeypatch.setattr(lark_module.lark_send, "send", fake_send)
    hub = ConfirmHub()
    tool = make_lark_send_tool(hub)
    policy = set_automation_policy(str(tmp_path), [
        {"tool": "lark.send_message", "target": "approved-chat"}
    ])
    try:
        assert "message-1" in await tool.ainvoke({"chat_id": "approved-chat", "text": "hello"})
        assert sent == [("approved-chat", "hello")]
    finally:
        reset_automation_policy(policy)
