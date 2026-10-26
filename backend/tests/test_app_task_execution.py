"""Industry application scopes are enforced across the runtime boundary."""
import pytest
from pathlib import Path
from app.main import build_stack
from app.orchestrator.task_manager import TaskRequest
from app.runtime.app_context import AppTaskScope
from app.skills import SkillMeta
from tests.conftest import FakeChatModel, make_ai


@pytest.mark.asyncio
async def test_plugin_skill_catalog_is_recorded_when_mounted_for_execution(tmp_path):
    folder = tmp_path / 'plugin-skill'
    folder.mkdir()
    (folder / 'SKILL.md').write_text('---\nname: weekly-report\ndescription: 项目周报\n---\n按授权范围生成周报。')
    skill = SkillMeta(id='app:cn.one:weekly-report', name='项目周报', description='项目周报',
                      prompt='按授权范围生成周报。', base_dir=folder,
                      app_origin={'id': 'cn.one', 'name': '项目', 'version': '1.0.0'})
    model = FakeChatModel(responses=[make_ai(tool_calls=[{'id': 'plan', 'name': 'write_todos', 'args': {
        'todos': [{'content': '核对项目周报范围', 'status': 'in_progress'}]}}]), make_ai('已核对范围')])
    manager = build_stack(supervisor_llm=model, whitelist=[str(tmp_path)])['task_manager']
    loaded = []
    scope = AppTaskScope('cn.one', frozenset(), skills={skill.id: skill}, record_skills=lambda: loaded.append(skill.id))
    try:
        events = [event async for event in manager.handle(TaskRequest(task_id='plugin-skill', text='核对范围',
            session_mode='single-agent', enabled_skill_ids=[skill.id], app_scope=scope))]
        assert events[-1]['status'] == 'ok', events[-1]
        assert loaded == [skill.id]
        assert any(path.is_file() for path in (manager.data_dir / 'harness-skills').rglob('SKILL.md'))
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_report_uses_registered_artifact(tmp_path):
    model = FakeChatModel(responses=[make_ai(tool_calls=[{'id': 'report', 'name': 'app_write_report',
        'args': {'content': '# 周报\n本周完成核对。'}}]), make_ai('周报已保存')])
    manager = build_stack(supervisor_llm=model, whitelist=[str(tmp_path)])['task_manager']
    store = manager.task_store
    store.create_app_task('report', '周报', {'app_id': 'cn.one', 'project_id': 'project'})
    scope = AppTaskScope('cn.one', frozenset({'app_write_report'}), output_dir=str(tmp_path / 'reports'),
        record_file=lambda path: store.add_file('cn.one', path, task_id='report'))
    try:
        events = [event async for event in manager.handle(TaskRequest(task_id='report', text='生成周报',
            project_id='project', session_mode='single-agent', enabled_skill_ids=[], app_scope=scope))]
        assert events[-1]['status'] == 'ok', events[-1]
        assert store.get_status('report') == 'DONE'
        assert len(store.task_files('cn.one', 'report')) == 1
        assert any(event['type'] == 'artifact.file' for event in events)
        assert all(Path(path).is_file() for path in scope.artifacts)
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_event_storage_failure_is_not_success(tmp_path, monkeypatch):
    manager = build_stack(supervisor_llm=FakeChatModel(responses=[make_ai('完成')]), whitelist=[str(tmp_path)])['task_manager']
    store = manager.task_store
    store.create_app_task('unsaved', '分析', {'app_id': 'cn.one'})
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(store, 'append_event', fail)
    try:
        events = [event async for event in manager.handle(TaskRequest(task_id='unsaved', text='分析',
            session_mode='single-agent', enabled_skill_ids=[], app_scope=AppTaskScope('cn.one', frozenset()))) ]
        assert events[-1]['status'] == 'error'
        assert 'disk full' in manager._tasks['unsaved']['storage_error']
    finally:
        await manager.close()
