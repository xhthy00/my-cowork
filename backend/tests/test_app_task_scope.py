import asyncio
import threading
from pathlib import Path

import pytest
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.runtime.app_context import AppTaskScope, app_task_scope
from app.runtime.v2.loop import run_act_loop, _invoke_tool
from app.industry_apps.file_tools import make_app_file_tools
from app.industry_apps.sdk import AppTool, LoadedAppTool
from app.industry_apps.tooling import make_agent_tool
from app.runtime.admission import Admission
from tests.conftest import FakeChatModel, make_ai


@pytest.mark.asyncio
async def test_effective_scope_filters_and_rejects_actual_invocation():
    invoked = []
    @tool
    def forbidden() -> str:
        """Would execute a forbidden operation."""
        invoked.append(True)
        return 'bad'
    token = app_task_scope.set(AppTaskScope('cn.one', frozenset()))
    try:
        model = FakeChatModel(responses=[make_ai(tool_calls=[{'id': '1', 'name': 'forbidden', 'args': {}}]), make_ai('完成')])
        await run_act_loop(model, [forbidden], [HumanMessage('分析')], max_steps=3)
        assert 'outside' in await _invoke_tool(forbidden, {})
        assert invoked == []
    finally:
        app_task_scope.reset(token)


@pytest.mark.asyncio
async def test_parallel_apps_keep_distinct_model_and_execution_scopes():
    observed = []
    @tool
    async def read_business() -> str:
        """Read the business selection of this execution."""
        await asyncio.sleep(.01)
        scope = app_task_scope.get()
        observed.append((scope.app_id, scope.business['selection']))
        return scope.app_id
    async def run(app_id, selection):
        token = app_task_scope.set(AppTaskScope(app_id, frozenset({'read_business'}), {'selection': selection}))
        try:
            model = FakeChatModel(responses=[make_ai(tool_calls=[{'id': app_id, 'name': 'read_business', 'args': {}}]), make_ai('完成')])
            await run_act_loop(model, [read_business], [HumanMessage('分析')], max_steps=3)
        finally:
            app_task_scope.reset(token)
    await asyncio.gather(run('cn.one', [1]), run('cn.two', [2]))
    assert sorted(observed) == [('cn.one', [1]), ('cn.two', [2])]


@pytest.mark.asyncio
async def test_file_references_and_report_are_scoped(tmp_path):
    source = tmp_path / 'input.txt'; source.write_text('业务材料', encoding='utf-8')
    files = make_app_file_tools()
    recorded = []
    scope = AppTaskScope('cn.one', frozenset({'app_read_file', 'app_write_report'}), files={'f1': str(source)},
                         output_dir=str(tmp_path / 'output'), record_file=lambda path: recorded.append(path) or {'id': 'output1'})
    token = app_task_scope.set(scope)
    try:
        assert await files[0].ainvoke({'file_id': 'f1'}) == '业务材料'
        with pytest.raises(PermissionError):
            await files[0].ainvoke({'file_id': str(source)})
        result = await files[1].ainvoke({'content': '# 本周工作\n已完成核对'})
        assert result['id'] == 'output1'
        assert Path(recorded[0]).read_text(encoding='utf-8').startswith('# 本周工作')
        assert Path(recorded[0]).parent == tmp_path / 'output'
        source.unlink()
        with pytest.raises(FileNotFoundError):
            await files[0].ainvoke({'file_id': 'f1'})
    finally:
        app_task_scope.reset(token)


@pytest.mark.asyncio
async def test_stop_does_not_lose_a_synchronous_business_write_result():
    class Args(BaseModel):
        title: str
    class Confirm:
        async def request(self, *args, **kwargs): return True
    began, release = threading.Event(), threading.Event()
    records = []
    def write(context, args):
        began.set(); release.wait(3)
        return {'id': 7, 'title': args.title}
    gate = Admission()
    wrapped = make_agent_tool(LoadedAppTool('cn.one', '应用一', AppTool('create', '创建', '创建一条记录', Args, write, 'write')), Confirm(), gate)
    token = app_task_scope.set(AppTaskScope('cn.one', frozenset({wrapped.name}), record_operation=records.append))
    try:
        task = asyncio.create_task(wrapped.ainvoke({'title': '实际写入'}))
        for _ in range(100):
            if began.is_set(): break
            await asyncio.sleep(.01)
        assert began.is_set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert gate.status()['active'] == 1
        release.set()
        for _ in range(100):
            if gate.status()['active'] == 0: break
            await asyncio.sleep(.01)
        assert records[-1]['status'] == 'completed'
        assert records[-1]['result']['id'] == 7
    finally:
        release.set(); app_task_scope.reset(token)
