"""v2 Act loop."""

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool as langchain_tool

from app.runtime.v2.loop import run_act_loop
from tests.conftest import FakeChatModel, make_ai


@langchain_tool
def echo(text: str) -> str:
    """Echo input."""
    return f"echo:{text}"


@pytest.mark.asyncio
async def test_loop_executes_tool_then_stops():
    model = FakeChatModel(
        responses=[
            make_ai("", tool_calls=[{"id": "1", "name": "echo", "args": {"text": "hi"}}]),
            make_ai("done with echo:hi"),
        ]
    )
    out = await run_act_loop(model, [echo], [HumanMessage(content="hi")])
    roles = [getattr(m, "type", None) for m in out]
    assert "tool" in roles
    assert out[-1].content == "done with echo:hi"


@pytest.mark.asyncio
async def test_loop_stops_on_first_text_reply():
    model = FakeChatModel(responses=[make_ai("list 可变，tuple 不可变。")])
    out = await run_act_loop(
        model,
        [],
        [HumanMessage(content="Python 里 list 和 tuple 的区别")],
        max_steps=10,
    )
    assert model.idx == 1
    assert out[-1].content == "list 可变，tuple 不可变。"


@pytest.mark.asyncio
async def test_loop_merges_streamed_tool_call_chunks():
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessageChunk
    from langchain_core.outputs import ChatGeneration, ChatResult

    class _ChunkModel(BaseChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            return ChatResult(
                generations=[ChatGeneration(message=make_ai("should stream"))]
            )

        async def astream(self, messages, **kwargs):
            yield AIMessageChunk(content="搜一下")
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {
                        "id": "1",
                        "name": "echo",
                        "args": '{"text": "hi"}',
                        "index": 0,
                    }
                ],
            )
            yield AIMessageChunk(content="")

        @property
        def _llm_type(self) -> str:
            return "chunk-stream"

    model = _ChunkModel()
    out = await run_act_loop(model, [echo], [HumanMessage(content="hi")])
    assert any(getattr(m, "name", "") == "echo" for m in out)


@pytest.mark.asyncio
async def test_loop_emits_content_tokens_as_they_arrive():
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessageChunk
    from langchain_core.outputs import ChatGeneration, ChatResult

    from app.observability.trace import TraceBus
    from app.runtime.todo_context import TodoRuntime, reset_todo_runtime, set_todo_runtime

    class _TokenModel(BaseChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            return ChatResult(
                generations=[ChatGeneration(message=make_ai("hello world"))]
            )

        async def astream(self, messages, **kwargs):
            for part in ("hello", " ", "world"):
                yield AIMessageChunk(content=part)

        @property
        def _llm_type(self) -> str:
            return "token-stream"

    bus = TraceBus()
    events: list[dict] = []
    bus.subscribe(events.append)
    token = set_todo_runtime(
        TodoRuntime(task_id="t1", bus=bus, agent_id="single_agent")
    )
    try:
        out = await run_act_loop(_TokenModel(), [], [HumanMessage(content="hi")])
    finally:
        reset_todo_runtime(token)
    deltas = [e["delta"] for e in events if e.get("type") == "step.delta"]
    assert deltas == ["hello", " ", "world"]


@pytest.mark.asyncio
async def test_loop_emits_llm_progress_for_tool_call_chunks():
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessageChunk
    from langchain_core.outputs import ChatGeneration, ChatResult

    from app.observability.trace import TraceBus
    from app.runtime.todo_context import TodoRuntime, reset_todo_runtime, set_todo_runtime

    class _ChunkModel(BaseChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            return ChatResult(
                generations=[ChatGeneration(message=make_ai("should stream"))]
            )

        async def astream(self, messages, **kwargs):
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {
                        "id": "1",
                        "name": "fs_write",
                        "args": '{"path": "/tmp/a.html", "content": "' + ("x" * 80),
                        "index": 0,
                    }
                ],
            )
            yield AIMessageChunk(content="")

        @property
        def _llm_type(self) -> str:
            return "chunk-stream"

    bus = TraceBus()
    events: list[dict] = []
    bus.subscribe(events.append)
    token = set_todo_runtime(
        TodoRuntime(task_id="t1", bus=bus, agent_id="single_agent")
    )
    try:
        from app.runtime.v2.loop import _invoke_model

        await _invoke_model(_ChunkModel(), [HumanMessage(content="hi")])
    finally:
        reset_todo_runtime(token)
    progress = [e for e in events if e.get("type") == "llm.progress"]
    assert progress
    assert progress[-1]["tool"] == "fs_write"
    assert int(progress[-1]["chars"]) >= 80


@pytest.mark.asyncio
async def test_loop_emits_tool_start_before_result():
    from app.observability.trace import TraceBus
    from app.runtime.todo_context import TodoRuntime, reset_todo_runtime, set_todo_runtime

    bus = TraceBus()
    events: list[dict] = []
    bus.subscribe(events.append)
    token = set_todo_runtime(
        TodoRuntime(task_id="t1", bus=bus, agent_id="single_agent")
    )
    try:
        model = FakeChatModel(
            responses=[
                make_ai("", tool_calls=[{"id": "1", "name": "echo", "args": {"text": "hi"}}]),
                make_ai("done"),
            ]
        )
        await run_act_loop(model, [echo], [HumanMessage(content="hi")])
    finally:
        reset_todo_runtime(token)
    types = [e.get("type") for e in events]
    assert "tool.start" in types
    assert types.index("tool.start") < types.index("tool.result")
    start = next(e for e in events if e.get("type") == "tool.start")
    assert start["tool"] == "echo"
    assert "hi" in str(start.get("preview") or "")


@pytest.mark.asyncio
async def test_floor_retry_forces_search_after_preamble():
    from app.graphs.single_agent import run_with_floor_retries
    from app.runtime.v2.critic import floor_analysis

    @langchain_tool
    def web_search(query: str) -> str:
        """Search the web."""
        return (
            '[{"url":"https://yangzhou.gov.cn/a","snippet":"限购已放宽"},'
            '{"url":"https://yangzhou.gov.cn/b","snippet":"首付"}]'
        )

    user = "调研扬州最新购房政策"
    model = FakeChatModel(
        responses=[
            make_ai("我先搜一下扬州最新购房政策的相关信息。"),
            make_ai("扬州限购已放宽。来源见工具结果。"),
        ]
    )
    out = await run_with_floor_retries(
        model,
        [web_search],
        [HumanMessage(content=user)],
        user,
    )
    assert any(getattr(m, "name", "") == "web_search" for m in out)
    queries = []
    for msg in out:
        for call in getattr(msg, "tool_calls", None) or []:
            args = call.get("args") if isinstance(call, dict) else getattr(call, "args", {})
            if isinstance(args, dict) and args.get("query"):
                queries.append(str(args["query"]))
    assert any("细则" in q or "例外" in q for q in queries)
    floor = floor_analysis(user, out)
    assert floor is not None
    assert any("web_fetch" in i for i in floor.issues)


@pytest.mark.asyncio
async def test_floor_retry_forces_fetch_after_search():
    from app.graphs.single_agent import run_with_floor_retries
    from app.runtime.v2.critic import floor_analysis

    @langchain_tool
    def web_search(query: str) -> str:
        """Search the web."""
        return (
            '[{"title":"a","url":"https://yangzhou.gov.cn/a","snippet":"限购已放宽"},'
            '{"title":"b","url":"https://yangzhou.gov.cn/b","snippet":"首付"}]'
        )

    @langchain_tool
    def web_fetch(url: str) -> str:
        """Fetch a URL."""
        return f"URL: {url}\n\n扬州取消限购，首付政策见正文。"

    user = "调研扬州最新购房政策"
    model = FakeChatModel(
        responses=[
            make_ai("我先搜一下扬州最新购房政策的相关信息。"),
            make_ai(
                "扬州已取消限购，首付政策见官方文件。"
                "来源 https://yangzhou.gov.cn/a 与 https://yangzhou.gov.cn/b"
            ),
        ]
    )
    out = await run_with_floor_retries(
        model,
        [web_search, web_fetch],
        [HumanMessage(content=user)],
        user,
    )
    assert any(getattr(m, "name", "") == "web_search" for m in out)
    assert any(getattr(m, "name", "") == "web_fetch" for m in out)
    floor = floor_analysis(user, out)
    assert floor is None


@pytest.mark.asyncio
async def test_floor_retry_search_gap_without_tool():
    from app.graphs.single_agent import run_with_floor_retries
    from app.runtime.v2.critic import floor_analysis

    user = "调研扬州最新购房政策"
    model = FakeChatModel(responses=[make_ai("我先搜一下扬州最新购房政策的相关信息。")])
    out = await run_with_floor_retries(
        model, [], [HumanMessage(content=user)], user
    )
    floor = floor_analysis(user, out)
    assert floor is not None
    assert any("web_search" in i for i in floor.issues)


@pytest.mark.asyncio
async def test_floor_retry_does_not_nudge_complete_qa():
    from app.graphs.single_agent import run_with_floor_retries

    user = "Python 里 list 和 tuple 的区别"
    model = FakeChatModel(responses=[make_ai("list 可变，tuple 不可变。")])
    out = await run_with_floor_retries(
        model, [], [HumanMessage(content=user)], user
    )
    assert model.idx == 1
    assert out[-1].content == "list 可变，tuple 不可变。"


@pytest.mark.asyncio
async def test_floor_retry_forces_html_write_for_web_game():
    from app.graphs.single_agent import run_with_floor_retries
    from app.runtime.v2.critic import floor_analysis

    @langchain_tool
    def fs_write(path: str, content: str) -> str:
        """Write a file."""
        return f"Wrote {len(content)} characters to {path}"

    user = "帮我开发一个坦克大战的web网页游戏"
    model = FakeChatModel(
        responses=[
            make_ai(
                "已确认目录，开始构建游戏文件，包括玩家坦克、AI 敌人和关卡系统。"
            ),
            make_ai(
                "",
                tool_calls=[
                    {
                        "id": "c1",
                        "name": "fs_write",
                        "args": {
                            "path": "/tmp/tank.html",
                            "content": "<html><body>tank</body></html>",
                        },
                    }
                ],
            ),
            make_ai("坦克大战已写入 /tmp/tank.html，用浏览器打开即可游玩。"),
        ]
    )
    out = await run_with_floor_retries(
        model, [fs_write], [HumanMessage(content=user)], user
    )
    assert any(getattr(m, "name", "") == "fs_write" for m in out)
    assert floor_analysis(user, out) is None


@pytest.mark.asyncio
async def test_loop_invokes_with_single_leading_system():
    from langchain_core.messages import SystemMessage

    seen: list[list] = []

    class Cap(FakeChatModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            seen.append(list(messages))
            return super()._generate(messages, stop, run_manager, **kwargs)

    model = Cap(responses=[make_ai("ok")])
    await run_act_loop(
        model,
        [],
        [
            SystemMessage(content="role"),
            SystemMessage(content="rules"),
            HumanMessage(content="hi"),
        ],
    )
    assert seen
    systems = [m for m in seen[0] if getattr(m, "type", None) == "system"]
    assert len(systems) == 1
    assert "role" in systems[0].content
    assert "rules" in systems[0].content


@pytest.mark.asyncio
async def test_loop_stops_unsolicited_office_write():
    policy = (
        "扬州目前已全面取消限购、限售，门槛处于历史最宽松阶段。"
        "最新政策以扬建房〔2026〕9号为准，有效期至年底。"
    )

    @langchain_tool
    def bash(command: str) -> str:
        """Run a shell command."""
        return "wrote /tmp/x.docx"

    model = FakeChatModel(
        responses=[
            make_ai(
                policy,
                tool_calls=[
                    {
                        "id": "c1",
                        "name": "bash",
                        "args": {"command": "officecli create /tmp/x.docx"},
                    }
                ],
            ),
            make_ai("已完成。Word 版调研报告已写入。"),
        ]
    )
    out = await run_act_loop(
        model,
        [bash],
        [HumanMessage(content="调研扬州最新购房政策")],
        allow_file_writes=False,
    )
    assert model.idx == 1
    assert "取消限购" in out[-1].content
    assert "Word 版" not in (out[-1].content or "")
    assert not any("wrote /tmp" in str(getattr(m, "content", "")) for m in out)


@pytest.mark.asyncio
async def test_loop_refuses_exec_bash_officecli():
    @langchain_tool
    def exec_bash(cmd: str) -> str:
        """Shell alias."""
        return "officecli 1.0"

    exec_bash.name = "exec.bash"
    model = FakeChatModel(
        responses=[
            make_ai(
                "我来用 officecli 生成 Word",
                tool_calls=[
                    {
                        "id": "c1",
                        "name": "exec.bash",
                        "args": {"cmd": "officecli --version"},
                    }
                ],
            ),
            make_ai("扬州取消限购。"),
        ]
    )
    out = await run_act_loop(
        model,
        [exec_bash],
        [HumanMessage(content="调研扬州最新购房政策")],
        allow_file_writes=False,
    )
    refused = [
        m
        for m in out
        if "not an Office file" in str(getattr(m, "content", ""))
        or "chat answer, not a file" in str(getattr(m, "content", ""))
    ]
    assert refused
    assert not any("officecli 1.0" in str(getattr(m, "content", "")) for m in out)


@pytest.mark.asyncio
async def test_loop_allows_markdown_fs_write():
    policy = (
        "扬州目前已全面取消限购、限售，门槛处于历史最宽松阶段。"
        "最新政策以扬建房〔2026〕9号为准，有效期至年底。"
    )

    @langchain_tool
    def fs_write(path: str, content: str) -> str:
        """Write a text file."""
        return f"Wrote {len(content)} characters to {path}"

    model = FakeChatModel(
        responses=[
            make_ai(
                policy,
                tool_calls=[
                    {
                        "id": "c1",
                        "name": "fs_write",
                        "args": {
                            "path": "/tmp/扬州最新购房政策.md",
                            "content": policy,
                        },
                    }
                ],
            ),
            make_ai("已写入 Markdown。"),
        ]
    )
    out = await run_act_loop(
        model,
        [fs_write],
        [HumanMessage(content="调研扬州最新购房政策")],
        allow_file_writes=False,
    )
    assert any("Wrote " in str(getattr(m, "content", "")) for m in out)
    assert model.idx == 2


@pytest.mark.asyncio
async def test_loop_load_skill_does_not_insert_human_between_tools():
    @langchain_tool
    def load_skill(name: str) -> str:
        """Load a skill."""
        return f"SKILL:{name}"

    model = FakeChatModel(
        responses=[
            make_ai(
                "加载公文写作规范和 Word 文档生成技能。",
                tool_calls=[
                    {
                        "id": "c1",
                        "name": "load_skill",
                        "args": {"name": "official-document-writing"},
                    },
                    {
                        "id": "c2",
                        "name": "load_skill",
                        "args": {"name": "officecli-docx"},
                    },
                ],
            ),
            make_ai("开始按规范起草请示。"),
        ]
    )
    out = await run_act_loop(
        model, [load_skill], [HumanMessage(content="写一份请示")]
    )
    roles = [getattr(m, "type", None) for m in out]
    assert roles == ["human", "ai", "tool", "tool", "ai"]
    bodies = [str(getattr(m, "content", "")) for m in out if getattr(m, "type", None) == "tool"]
    assert any("SKILL:official-document-writing" in b for b in bodies)
    assert any("Follow the skill markdown" in b for b in bodies)


@pytest.mark.asyncio
async def test_loop_refuses_pandoc_docx():
    ran = {"n": 0}

    @langchain_tool
    def bash(command: str) -> str:
        """Run a shell command."""
        ran["n"] += 1
        return "wrote /tmp/x.docx"

    model = FakeChatModel(
        responses=[
            make_ai(
                "我用 pandoc 转 Word",
                tool_calls=[
                    {
                        "id": "c1",
                        "name": "bash",
                        "args": {
                            "command": "pandoc report.html -o /tmp/扬州购房政策调研报告.docx"
                        },
                    }
                ],
            ),
            make_ai("改用 officecli 生成。"),
        ]
    )
    out = await run_act_loop(
        model,
        [bash],
        [HumanMessage(content="帮我生成word文档")],
        allow_file_writes=True,
    )
    assert ran["n"] == 0
    refused = [
        m
        for m in out
        if "Do not use pandoc" in str(getattr(m, "content", ""))
    ]
    assert refused


@pytest.mark.asyncio
async def test_loop_filters_mcp_tools_before_bind():
    from langchain_core.tools import StructuredTool

    from app.tools.mcp.manager import reset_enabled_mcp, set_enabled_mcp

    bound: list[str] = []

    class Rec(FakeChatModel):
        def bind_tools(self, tools, **kwargs):  # type: ignore[no-untyped-def]
            bound.clear()
            bound.extend(str(getattr(t, "name", "") or "") for t in tools)
            return self

    pw = StructuredTool.from_function(
        lambda: "a",
        name="mcp_playwright_nav",
        description="d",
        metadata={"mcp_server": "playwright"},
    )
    other = StructuredTool.from_function(
        lambda: "b",
        name="mcp_other_foo",
        description="d",
        metadata={"mcp_server": "other"},
    )
    model = Rec(responses=[make_ai("ok")])
    token = set_enabled_mcp(["playwright"])
    try:
        await run_act_loop(model, [pw, other], [HumanMessage(content="hi")])
    finally:
        reset_enabled_mcp(token)
    assert "mcp_playwright_nav" in bound
    assert "mcp_other_foo" not in bound


@pytest.mark.asyncio
async def test_loop_refuses_search_after_budget(monkeypatch):
    import app.runtime.v2.loop as loop_mod

    monkeypatch.setattr(loop_mod, "_MAX_RESEARCH_SEARCHES", 2)

    calls: list[str] = []

    @langchain_tool
    def web_search(query: str) -> str:
        """Search the web."""
        calls.append(query)
        return f'[{{"url":"https://example.gov/{len(calls)}"}}]'

    model = FakeChatModel(
        responses=[
            make_ai(
                "",
                tool_calls=[{"id": "1", "name": "web_search", "args": {"query": "q1 官方"}}],
            ),
            make_ai(
                "",
                tool_calls=[{"id": "2", "name": "web_search", "args": {"query": "q2 细则"}}],
            ),
            make_ai(
                "",
                tool_calls=[{"id": "3", "name": "web_search", "args": {"query": "q3 更多"}}],
            ),
            make_ai("enough"),
        ]
    )
    out = await run_act_loop(model, [web_search], [HumanMessage(content="调研政策")])
    assert calls == ["q1 官方", "q2 细则"]
    notices = [
        str(getattr(m, "content", "") or "")
        for m in out
        if getattr(m, "type", None) == "tool"
    ]
    assert any("Research budget exhausted" in t for t in notices)
    assert out[-1].content == "enough"
