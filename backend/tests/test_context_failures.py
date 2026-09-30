import pytest
from langchain_core.messages import HumanMessage
from app.llm.context_limits import ContextPreparationError, ModelInputBudgetCallback
from app.llm.model_config import ModelConfig


class OverBudget:
    async def ainvoke(self, messages):
        raise ContextPreparationError("上下文预算不足")


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["planner", "coordinator", "critic", "synthesis", "decompose"])
async def test_capacity_error_is_not_silently_replaced_by_fallback(path):
    with pytest.raises(ContextPreparationError):
        if path == "planner":
            from app.runtime.todo_planner import plan_todos_llm
            await plan_todos_llm("分析项目文件", OverBudget())
        elif path == "coordinator":
            from app.graphs.coordinator import coordinate
            await coordinate("分析项目文件", [], OverBudget())
        elif path == "critic":
            from app.runtime.v2.critic import _invoke_analysis_llm
            await _invoke_analysis_llm(OverBudget(), "分析项目文件")
        elif path == "synthesis":
            from app.runtime.v2.synthesize import synthesize_answer
            await synthesize_answer("分析项目文件", [], OverBudget(), rewrite=True)
        else:
            from app.runtime.decompose import decompose_subtasks
            await decompose_subtasks("请读取全部项目文件，分析实现约束，并生成一份详细的 Markdown 报告文件", OverBudget())


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_sdk_blocks_tool_schema_overflow_before_any_network_call(stream):
    import httpx
    from langchain_openai import ChatOpenAI
    sent = []
    def handler(request):
        sent.append(request)
        raise AssertionError("must not send oversized request")
    config = ModelConfig(id="small", provider="openai_compat", model="small", api_key="fake", context_window=4096, output_limit=1024)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        model = ChatOpenAI(model="test", api_key="fake", http_async_client=client, callbacks=[ModelInputBudgetCallback(config)])
        bound = model.bind_tools([{"type": "function", "function": {"name": "large_schema", "description": "detail " * 5000, "parameters": {"type": "object", "properties": {}}}}])
        with pytest.raises(ContextPreparationError):
            if stream:
                async for _ in bound.astream([HumanMessage("hello")]):
                    pass
            else:
                await bound.ainvoke([HumanMessage("hello")])
    assert not sent


@pytest.mark.asyncio
async def test_task_end_preserves_context_error_code_for_draft_recovery():
    from app.graphs.single_agent import compile_single_agent_graph
    from app.observability.trace import TraceBus
    from app.orchestrator.task_manager import TaskManager, TaskRequest
    manager = TaskManager(graph=compile_single_agent_graph(model=OverBudget(), tools=[]), tools=[], bus=TraceBus())
    request = TaskRequest(text="请分析这份项目的约束", task_id="context-error", session_id="context-error", session_mode="single_agent")
    manager.prepare_task(request)
    events = [event async for event in manager._execute(request.task_id, request)]
    end = next(e for e in events if e["type"] == "graph.end")
    assert end["status"] == "error"
    assert end["error_code"] == "context_preparation"
    assert "上下文" in end["error"]
    assert not manager.session_busy(request.session_id)
