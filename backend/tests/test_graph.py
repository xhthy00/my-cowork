"""Workforce graph: decompose routing helpers + coordinator fan-out."""

from dataclasses import dataclass
from pathlib import Path
import time

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool as langchain_tool

from app.agents.factory import create_worker
from app.graphs.routing import (
    infer_default_worker,
    needs_forced_delegation,
    parse_workers,
    ready_subtasks,
    route_after_coordinator,
)
from app.graphs.state import WorkforceState
from app.graphs.workforce import compile_workforce_graph
from app.observability.trace import TraceBus
from app.runtime.graph_runner import _emit_graph_end, run_graph
from tests.conftest import FakeChatModel, make_ai


def _mock_tool():
    @langchain_tool
    def mock_tool(query: str) -> str:
        """A mock tool for testing."""
        return f"mock:{query}"

    return mock_tool


@dataclass
class _Task:
    task_id: str
    text: str
    session_mode: str = "workforce"
    memory_enabled: bool = True


class TestParseWorkers:
    def test_parallel_protocol(self):
        assert parse_workers("PARALLEL:file_worker,doc_worker") == [
            "developer_agent",
            "document_agent",
        ]

    def test_finish(self):
        assert parse_workers("FINISH") == []

    def test_natural_language_routing(self):
        assert parse_workers("The doc_worker needs to handle this request.") == [
            "document_agent"
        ]


class TestInferDefaultWorker:
    def test_ppt_followup_beats_travel_keywords(self):
        q = "帮我将上述的旅游攻略生成图文并茂的 PPT 版攻略"
        assert infer_default_worker(q) == "document_agent"

    def test_research_still_web(self):
        assert infer_default_worker("帮我搜索宜昌旅游攻略") == "browser_agent"

    def test_short_ppt_forces_delegation(self):
        assert needs_forced_delegation("生成PPT") is True
        assert infer_default_worker("生成PPT") == "document_agent"

    def test_unspecified_report_goes_to_document_agent(self):
        assert infer_default_worker("做成一份报告") == "document_agent"
        assert infer_default_worker("写一份报告") == "document_agent"


class TestReadySubtasks:
    def test_dependency_order(self):
        subtasks = [
            {
                "id": "task_1",
                "content": "research",
                "assignee": "browser_agent",
                "dependencies": [],
                "status": "completed",
                "result": "ok",
                "retries": 0,
            },
            {
                "id": "task_2",
                "content": "write ppt",
                "assignee": "document_agent",
                "dependencies": ["task_1"],
                "status": "waiting",
                "result": "",
                "retries": 0,
            },
        ]
        ready = ready_subtasks(subtasks)
        assert [t["id"] for t in ready] == ["task_2"]

    def test_parallel_ready(self):
        subtasks = [
            {
                "id": "a",
                "content": "a",
                "assignee": "browser_agent",
                "dependencies": [],
                "status": "waiting",
                "result": "",
                "retries": 0,
            },
            {
                "id": "b",
                "content": "b",
                "assignee": "developer_agent",
                "dependencies": [],
                "status": "waiting",
                "result": "",
                "retries": 0,
            },
        ]
        assert len(ready_subtasks(subtasks)) == 2


class TestWorkforceGraph:
    @pytest.mark.asyncio
    async def test_coordinator_runs_developer_then_ends(self):
        developer = FakeChatModel(responses=[make_ai(content="file done")])
        graph = compile_workforce_graph(
            {
                "developer_agent": create_worker(
                    "developer_agent",
                    system_prompt="dev",
                    model=developer,
                    tools=[],
                )
            }
        )
        state = WorkforceState(
            messages=[],
            task_id="t2",
            session_mode="workforce",
            user_text="write a file",
            subtasks=[
                {
                    "id": "task_1",
                    "content": "write a file",
                    "assignee": "developer_agent",
                    "dependencies": [],
                    "status": "waiting",
                    "result": "",
                    "retries": 0,
                }
            ],
            assigned_task_id=None,
            round=0,
        )
        result = await graph.ainvoke(state)
        statuses = {t["id"]: t["status"] for t in result["subtasks"]}
        assert statuses["task_1"] == "completed"

    @pytest.mark.asyncio
    async def test_parallel_independent_subtasks(self):
        browser = FakeChatModel(responses=[make_ai(content="browser ok")])
        developer = FakeChatModel(responses=[make_ai(content="dev ok")])
        graph = compile_workforce_graph(
            {
                "browser_agent": create_worker(
                    "browser_agent", "b", model=browser, tools=[]
                ),
                "developer_agent": create_worker(
                    "developer_agent", "d", model=developer, tools=[]
                ),
            }
        )
        state = WorkforceState(
            messages=[],
            task_id="t-par",
            session_mode="workforce",
            user_text="do both",
            subtasks=[
                {
                    "id": "a",
                    "content": "search",
                    "assignee": "browser_agent",
                    "dependencies": [],
                    "status": "waiting",
                    "result": "",
                    "retries": 0,
                },
                {
                    "id": "b",
                    "content": "write",
                    "assignee": "developer_agent",
                    "dependencies": [],
                    "status": "waiting",
                    "result": "",
                    "retries": 0,
                },
            ],
            assigned_task_id=None,
            round=0,
        )
        result = await graph.ainvoke(state)
        assert all(t["status"] == "completed" for t in result["subtasks"])


class TestRouteAfterCoordinator:
    def test_fanout_send(self):
        nxt = route_after_coordinator(
            {
                "subtasks": [
                    {
                        "id": "a",
                        "content": "x",
                        "assignee": "browser_agent",
                        "dependencies": [],
                        "status": "waiting",
                        "result": "",
                        "retries": 0,
                    }
                ],
                "round": 1,
            }
        )
        assert isinstance(nxt, list)
        assert nxt[0].node == "browser_agent"


class TestGraphRunner:
    @pytest.mark.asyncio
    async def test_run_graph_trivial_skips_workforce(self):
        graph = compile_workforce_graph({})
        bus = TraceBus()
        events = []
        async for ev in run_graph(_Task(task_id="t3", text="hello"), graph, bus):
            events.append(ev)
        assert events[0]["type"] == "graph.start"
        assert events[-1]["type"] == "graph.end"
        assert any(e["type"] == "agent.create" for e in events)


class TestSingleAgentGraph:
    @pytest.mark.asyncio
    async def test_single_agent_solves_with_tools_no_supervisor(self):
        from app.agents.factory import create_single_agent
        from app.graphs.single_agent import compile_single_agent_graph

        model = FakeChatModel(
            responses=[
                make_ai(
                    content="",
                    tool_calls=[
                        {
                            "name": "mock_tool",
                            "args": {"query": "hello"},
                            "id": "call_1",
                        }
                    ],
                ),
                make_ai(content="single agent done"),
            ]
        )
        agent = create_single_agent(
            system_prompt="You are the Single Agent.",
            model=model,
            tools=[_mock_tool()],
        )
        graph = compile_single_agent_graph(agent)
        state = WorkforceState(
            messages=[HumanMessage(content="do the thing")],
            task_id="sa-1",
            session_mode="single-agent",
            user_text="do the thing",
            round=0,
        )
        result = await graph.ainvoke(state)
        texts = " ".join(str(m.content) for m in result["messages"])
        assert "single agent done" in texts

    @pytest.mark.asyncio
    async def test_run_graph_emits_single_agent_roster(self):
        from app.agents.factory import create_single_agent
        from app.graphs.single_agent import compile_single_agent_graph

        model = FakeChatModel(responses=[make_ai(content="ok")])
        graph = compile_single_agent_graph(
            create_single_agent("prompt", model, tools=[])
        )
        bus = TraceBus()
        events = []
        async for ev in run_graph(
            _Task(task_id="sa-2", text="hi", session_mode="single-agent"),
            graph,
            bus,
        ):
            events.append(ev)

        creates = [e for e in events if e["type"] == "agent.create"]
        assert len(creates) == 1
        assert creates[0]["agent_id"] == "single_agent"
        assert events[0]["type"] == "graph.start"
        assert events[-1]["type"] == "graph.end"

    @pytest.mark.asyncio
    async def test_run_graph_errors_when_gongwen_regen_writes_no_file(self):
        from app.agents.factory import create_single_agent
        from app.graphs.single_agent import compile_single_agent_graph

        model = FakeChatModel(
            responses=[
                make_ai(content="已按规范重新生成"),
                make_ai(content="已按规范重新生成"),
            ]
        )
        graph = compile_single_agent_graph(
            create_single_agent("prompt", model, tools=[])
        )
        bus = TraceBus()
        events = []
        async for ev in run_graph(
            _Task(
                task_id="sa-regen",
                text="#official-document-writing 帮我重新生成一份上述内容的公文汇报",
                session_mode="single-agent",
            ),
            graph,
            bus,
        ):
            events.append(ev)

        end = events[-1]
        assert end["type"] == "graph.end"
        assert end["status"] == "error"
        assert "未生成文档文件" in str(end.get("error") or "")

    @pytest.mark.asyncio
    async def test_remote_channel_does_not_fail_graph_when_doc_missing(self):
        from app.agents.factory import create_single_agent
        from app.graphs.single_agent import compile_single_agent_graph
        from app.guardrails.approval import reset_remote_channel, set_remote_channel

        model = FakeChatModel(
            responses=[make_ai(content="清单如下……"), make_ai(content="清单如下……")]
        )
        graph = compile_single_agent_graph(
            create_single_agent("prompt", model, tools=[])
        )
        bus = TraceBus()
        events = []
        token = set_remote_channel(True)
        try:
            async for ev in run_graph(
                _Task(
                    task_id="sa-wx-docx",
                    text="帮我把上述方案内容生成 docx",
                    session_mode="single-agent",
                ),
                graph,
                bus,
            ):
                events.append(ev)
        finally:
            reset_remote_channel(token)

        end = events[-1]
        assert end["type"] == "graph.end"
        assert end["status"] != "error"
        assert "写入确认" not in str(end.get("error") or "")

    @pytest.mark.asyncio
    async def test_remote_channel_errors_when_claimed_file_missing(self):
        from app.agents.factory import create_single_agent
        from app.graphs.single_agent import compile_single_agent_graph
        from app.guardrails.approval import reset_remote_channel, set_remote_channel

        fake = "/Users/tanghaoyu/.my-cowork/spaces/space-local/projects/x/runs/x/江苏兴化旅游攻略.docx"
        reply = f"最终交付文件\n- 路径：`{fake}`"
        model = FakeChatModel(responses=[make_ai(content=reply), make_ai(content=reply)])
        graph = compile_single_agent_graph(
            create_single_agent("prompt", model, tools=[])
        )
        bus = TraceBus()
        events = []
        token = set_remote_channel(True)
        try:
            async for ev in run_graph(
                _Task(
                    task_id="sa-wx-claimed",
                    text="整理兴化旅游攻略 word 版本发我",
                    session_mode="single-agent",
                ),
                graph,
                bus,
            ):
                events.append(ev)
        finally:
            reset_remote_channel(token)

        end = events[-1]
        assert end["type"] == "graph.end"
        assert end["status"] == "error"
        assert "未生成文档文件" in str(end.get("error") or "")

    @pytest.mark.asyncio
    async def test_run_graph_errors_when_claimed_xlsx_missing(self):
        from app.agents.factory import create_single_agent
        from app.graphs.single_agent import compile_single_agent_graph

        fake_path = "/Users/tanghaoyu/Documents/AIS/200P算力中心建设投资估算.xlsx"
        reply = f"交付文件\n{fake_path}"
        model = FakeChatModel(
            responses=[make_ai(content=reply), make_ai(content=reply)]
        )
        graph = compile_single_agent_graph(
            create_single_agent("prompt", model, tools=[])
        )
        bus = TraceBus()
        events = []
        async for ev in run_graph(
            _Task(
                task_id="sa-xlsx",
                text="帮我做一份200P算力中心建设投资估算",
                session_mode="single-agent",
            ),
            graph,
            bus,
        ):
            events.append(ev)

        end = events[-1]
        assert end["type"] == "graph.end"
        assert end["status"] == "error"
        assert "未生成文档文件" in str(end.get("error") or "") or fake_path in str(
            end.get("error") or ""
        )


class _CollectBus:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event: dict) -> None:
        self.events.append(event)


def test_graph_end_emits_untracked_deliverable(tmp_path: Path):
    workdir = tmp_path / "work"
    workdir.mkdir()
    report = workdir / "方案对比综合评审报告.docx"
    report.write_bytes(b"PK")
    bus = _CollectBus()
    events = _emit_graph_end(
        bus,
        "t-docx",
        "error",
        workdir=workdir,
        written_paths=set(),
        min_mtime=time.time() - 10,
        error="LARK_APP_ID missing",
    )
    arts = [e for e in events if e.get("type") == "artifact.file"]
    assert any(str(report) in str(e.get("path")) for e in arts)
    assert events[-1]["type"] == "graph.end"
    assert events[-1]["status"] == "error"
