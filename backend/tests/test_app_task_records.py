import pytest

from app.orchestrator.task_store import TaskStore


def test_app_record_survives_status_updates_and_restart(tmp_path):
    path = tmp_path / 'tasks.db'
    store = TaskStore(path)
    origin = {'app_id': 'cn.example.tasks', 'project_id': 'p1', 'route': '/tasks/1'}
    assert store.create_app_task('t1', '分析风险', origin)
    assert not store.create_app_task('t1', '分析风险', origin)
    store.upsert('t1', 'RUNNING')
    store.append_event('t1', {'type': 'graph.end', 'summary': '有延期风险'})
    store.upsert('t1', 'DONE')
    store.close()
    store = TaskStore(path)
    assert store.get('t1')['origin'] == origin
    assert store.get('t1')['text'] == '分析风险'
    assert store.events('t1')[0]['event']['summary'] == '有延期风险'
    assert [row['task_id'] for row in store.app_tasks('cn.example.tasks')] == ['t1']
    assert store.app_tasks('other') == []


def test_only_unfinished_app_records_are_interrupted(tmp_path):
    store = TaskStore(tmp_path / 'tasks.db')
    store.create_app_task('t1', '分析', {'app_id': 'app'})
    store.upsert('regular', 'RUNNING')
    store.interrupt_app_tasks()
    assert store.get_status('t1') == 'INTERRUPTED'
    assert store.get_status('regular') == 'RUNNING'
