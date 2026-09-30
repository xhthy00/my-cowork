import pytest
import asyncio
from pathlib import Path

from app.graphs.single_agent import compile_single_agent_graph
from app.industry_apps.file_tools import make_app_file_tools
from app.observability.trace import TraceBus
from app.orchestrator.task_manager import TaskManager, TaskRequest
from app.orchestrator.task_store import TaskStore
from app.runtime.app_context import AppTaskScope
from tests.conftest import FakeChatModel, make_ai


@pytest.mark.asyncio
async def test_report_uses_declared_artifact_without_generic_office_retry(tmp_path, monkeypatch):
    monkeypatch.setenv('MY_COWORK_DATA_DIR', str(tmp_path))
    tools = make_app_file_tools()
    model = FakeChatModel(responses=[
        make_ai(tool_calls=[{'id': 'report', 'name': 'app_write_report', 'args': {'content': '# 周报\n本周完成了交付材料核对。'}}]),
        make_ai('周报已保存为 Markdown 文件，其中包括本周进展和下一步需要核对的内容。请打开附件检查。'),
    ])
    graph = compile_single_agent_graph(model=model, tools=tools)
    store = TaskStore(tmp_path / 'tasks.db')
    manager = TaskManager(graph=graph, single_agent_graph=graph, tools=tools, bus=TraceBus(), task_store=store)
    store.create_app_task('report1', '生成周报', {'app_id': 'cn.one', 'project_id': 'project1'})
    scope = AppTaskScope('cn.one', frozenset({'app_write_report'}), output_dir=str(tmp_path / 'reports'),
                         record_file=lambda path: store.add_file('cn.one', path, task_id='report1'))
    stream = manager.handle(TaskRequest(text='生成本周工作报告，保存 Markdown 文件。', task_id='report1', project_id='project1',
                                       session_mode='single-agent', memory_enabled=False, app_scope=scope))
    async for event in stream:
        if event['type'] == 'graph.end':
            # Even callers that stop at the terminal event see the persisted final state.
            assert event['status'] == 'ok', event
            assert store.get_status('report1') == 'DONE'
            break
    await stream.aclose()
    assert model.idx == 2
    assert len(store.task_files('cn.one', 'report1')) == 1
    assert any(row['event']['type'] == 'artifact.file' for row in store.events('report1'))
    assert all(Path(path).is_file() for path in scope.artifacts)


@pytest.mark.asyncio
async def test_app_task_can_stop_before_execution_starts(tmp_path):
    store = TaskStore(tmp_path / 'tasks.db')
    manager = TaskManager(graph=None, tools=[], bus=TraceBus(), task_store=store)
    store.create_app_task('early', '分析', {'app_id': 'cn.one'})
    await manager.submit(TaskRequest(text='分析', task_id='early', app_scope=AppTaskScope('cn.one', frozenset())))
    assert manager.cancel('early')
    await asyncio.sleep(.01)
    assert store.get_status('early') == 'CANCELLED'
    assert store.events('early')[-1]['event']['status'] == 'cancelled'
    assert manager.admission.status()['active'] == 0


@pytest.mark.asyncio
async def test_event_storage_failure_is_retained_even_when_status_save_succeeds(tmp_path, monkeypatch):
    monkeypatch.setenv('MY_COWORK_DATA_DIR', str(tmp_path))
    graph = compile_single_agent_graph(model=FakeChatModel(responses=[make_ai('分析已完成')]), tools=[])
    store = TaskStore(tmp_path / 'tasks.db')
    store.create_app_task('unsaved', '分析', {'app_id': 'cn.one'})
    manager = TaskManager(graph=graph, single_agent_graph=graph, tools=[], bus=TraceBus(), task_store=store)
    def fail_append(*args):
        raise OSError('disk full')
    monkeypatch.setattr(store, 'append_event', fail_append)
    events = [event async for event in manager.handle(TaskRequest(text='分析', task_id='unsaved',
              session_mode='single-agent', memory_enabled=False, app_scope=AppTaskScope('cn.one', frozenset()))) ]
    assert events[-1]['status'] == 'error'
    assert store.get_status('unsaved') == 'FAILED'
    assert 'disk full' in manager._tasks['unsaved']['storage_error']
