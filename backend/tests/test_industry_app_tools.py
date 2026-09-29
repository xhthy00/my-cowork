from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import yaml
from fastapi import APIRouter
from langchain_core.messages import ToolMessage
from pydantic import BaseModel

from app.guardrails.approval import reset_remote_channel, set_remote_channel
from app.industry_apps.package import AppManifest
from app.industry_apps.sdk import AppContribution, AppTool, LoadedAppTool
from app.industry_apps.tooling import make_agent_tool, validate_app_tools
from app.observability.trace import TraceBus
from app.runtime.graph_runner import _tool_result_events
from app.runtime.todo_context import TodoRuntime, reset_todo_runtime, set_todo_runtime
from app.runtime.v2.loop import _emit_tool_event


class Args(BaseModel):
    value: str


class Approval:
    def __init__(self, allow: bool) -> None:
        self.allow = allow
        self.calls: list[tuple[str, dict]] = []

    async def request(self, _call_id: str, name: str, args: dict) -> bool:
        self.calls.append((name, args))
        return self.allow


def test_manifest_must_match_supplied_tools() -> None:
    example = Path(__file__).resolve().parents[2] / "examples/taskboard/mycowork-app.yaml"
    manifest = AppManifest.model_validate(yaml.safe_load(example.read_text(encoding="utf-8")))
    with pytest.raises(ValueError, match="do not match"):
        validate_app_tools(manifest, AppContribution(router=APIRouter()))


def test_write_tool_uses_host_confirmation() -> None:
    writes: list[str] = []
    entry = LoadedAppTool(
        "cn.example.taskboard", "任务管理样例",
        AppTool("save_item", "保存项目", "保存一个项目。", Args,
                lambda _context, args: writes.append(args.value) or {"saved": args.value},
                access="write"),
    )
    denied = Approval(False)
    tool = make_agent_tool(entry, denied)
    assert asyncio.run(tool.ainvoke({"value": "A"})) == "Operation rejected by user"
    assert writes == []
    assert denied.calls[0] == (tool.name, {"value": "A"})
    allowed = Approval(True)
    assert asyncio.run(make_agent_tool(entry, allowed).ainvoke({"value": "B"})) == {"saved": "B"}
    assert writes == ["B"]
    with pytest.raises(RuntimeError, match="asynchronous confirmation"):
        tool.invoke({"value": "C"})
    token = set_remote_channel(True)
    try:
        assert asyncio.run(tool.ainvoke({"value": "remote"})).startswith("[ERROR]")
    finally:
        reset_remote_channel(token)
    assert writes == ["B"]


def test_industry_tool_trace_carries_app_identity() -> None:
    bus = TraceBus()
    name = "industry__cn_example_taskboard__list_tasks"
    bus.tool_metadata[name] = {
        "tool_source": "industry_app", "app_id": "cn.example.taskboard",
        "app_name": "任务管理样例", "tool_title": "查询任务", "tool_access": "read",
    }
    events: list[dict] = []
    bus.subscribe(events.append)
    token = set_todo_runtime(TodoRuntime(task_id="run-1", bus=bus))
    try:
        _emit_tool_event("tool.start", name=name, call_id="call-1", args={})
        _emit_tool_event("tool.result", name=name, call_id="call-1", result="done")
    finally:
        reset_todo_runtime(token)
    assert [event["type"] for event in events] == ["tool.start", "tool.result"]
    assert all(event["payload"]["app_name"] == "任务管理样例" for event in events)
    worker_events = _tool_result_events(bus, "run-2", {
        "messages": [ToolMessage(content="{}", name=name, tool_call_id="call-2")],
    })
    assert worker_events[-1]["payload"]["tool_source"] == "industry_app"
    assert worker_events[-1]["payload"]["tool_title"] == "查询任务"
