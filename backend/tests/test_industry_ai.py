from types import SimpleNamespace

from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
import pytest_asyncio
import pytest

from app.orchestrator.task_store import TaskStore
from app.runtime.admission import Admission
from app.server.routes.industry_ai import router


@pytest_asyncio.fixture
async def setup(tmp_path):
    store = TaskStore(tmp_path / 'tasks.db')
    submitted = []
    class Manager:
        task_store = store
        admission = Admission()
        async def submit(self, req):
            submitted.append(req)
            return req.task_id
        def cancel(self, task_id):
            return True
    app = FastAPI()
    app.include_router(router)
    app.state.task_manager = Manager()
    app.state.generation = 'generation1'
    app.state.app_manifests = {'cn.test.one': {
        'id': 'cn.test.one', 'name': '业务', 'version': '1.0.0',
        'capabilities': {'host_api': ['ai', 'files']},
        'agent_tools': [{'name': 'list_items', 'access': 'read'}, {'name': 'create_item', 'access': 'write'}],
    }}
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        yield client, store, submitted, app
    store.close()


def body(**extra):
    return {'request_id': 'request1', 'generation': 'generation1', 'prompt': '分析风险',
            'project_id': 'project1', 'space_id': 'space1', 'tools': ['list_items'],
            'context': {'selection': [1], 'partition': 'local'}, **extra}


@pytest.mark.asyncio
async def test_query_exposes_storage_failure_as_terminal_snapshot(setup):
    client, store, submitted, app = setup
    response = await client.post('/api/industry-ai/cn.test.one/tasks', json=body())
    task_id = response.json()['task_id']
    app.state.task_manager._tasks = {task_id: {'storage_error': '任务记录保存失败：disk full'}}
    snapshot = (await client.get(f'/api/industry-ai/cn.test.one/tasks/{task_id}')).json()
    assert snapshot['status'] == 'FAILED'
    assert 'disk full' in snapshot['storage_error']
    assert snapshot['waiting'] is False


@pytest.mark.asyncio
async def test_create_is_idempotent_and_binds_scope(setup):
    client, store, submitted, app = setup
    first = await client.post('/api/industry-ai/cn.test.one/tasks', json=body())
    assert first.status_code == 200, first.text
    second = await client.post('/api/industry-ai/cn.test.one/tasks', json=body())
    assert first.json() == second.json()
    assert len(submitted) == 1
    req = submitted[0]
    assert req.app_scope.app_id == 'cn.test.one'
    assert req.app_scope.tools == frozenset({'industry__cn_test_one__list_items', 'ask_human'})
    assert req.app_scope.business['partition'] == 'local'
    assert req.memory_enabled is False
    changed = await client.post('/api/industry-ai/cn.test.one/tasks', json=body(prompt='another'))
    assert changed.status_code == 409
    assert (await client.post('/api/industry-ai/cn.test.one/tasks', json=body(request_id='concurrent'))).status_code == 409


@pytest.mark.asyncio
async def test_development_followup_requires_same_revision(setup):
    client, store, submitted, app = setup
    app.state.app_development = {'cn.test.one': 'a' * 64}
    first = (await client.post('/api/industry-ai/cn.test.one/tasks', json=body())).json()
    assert first['origin']['dev_revision'] == 'a' * 64
    store.upsert(first['task_id'], 'DONE')
    app.state.app_development['cn.test.one'] = 'b' * 64
    response = await client.post('/api/industry-ai/cn.test.one/tasks', json=body(request_id='followup', parent_task_id=first['task_id']))
    assert response.status_code == 409
    assert '重新加载' in response.text


@pytest.mark.asyncio
async def test_scope_generation_capability_and_ownership(setup):
    client, store, submitted, app = setup
    assert (await client.post('/api/industry-ai/cn.test.one/tasks', json=body(tools=['bash']))).status_code == 403
    assert (await client.post('/api/industry-ai/cn.test.one/tasks', json=body(generation='old'))).status_code == 409
    assert (await client.post('/api/industry-ai/cn.test.one/tasks', json=body(files=['invented']))).status_code == 403
    app.state.app_manifests['cn.test.one']['capabilities']['host_api'] = []
    assert (await client.post('/api/industry-ai/cn.test.one/tasks', json=body())).status_code == 403
    store.create_app_task('foreign', 'hidden', {'app_id': 'cn.test.two'})
    assert (await client.get('/api/industry-ai/cn.test.one/tasks/foreign')).status_code == 404
    assert (await client.post('/api/industry-ai/cn.test.one/tasks/foreign/cancel')).status_code == 404


@pytest.mark.asyncio
async def test_followup_inherits_scope_and_rejects_old_generation(setup):
    client, store, submitted, app = setup
    first = (await client.post('/api/industry-ai/cn.test.one/tasks', json=body())).json()
    store.upsert(first['task_id'], 'DONE')
    followup = body(request_id='next', parent_task_id=first['task_id'], prompt='继续', tools=['create_item'], context={'selection': [999]})
    assert (await client.post('/api/industry-ai/cn.test.one/tasks', json=followup)).status_code == 200
    assert submitted[1].app_scope.tools == submitted[0].app_scope.tools
    assert submitted[1].app_scope.business == submitted[0].app_scope.business
    app.state.generation = 'new'
    app.state.app_manifests['cn.test.one']['version'] = '1.0.1'
    assert (await client.post('/api/industry-ai/cn.test.one/tasks', json=body(request_id='third', generation='new', parent_task_id=first['task_id']))).status_code == 409


@pytest.mark.asyncio
async def test_completed_task_can_be_followed_after_same_version_restart(setup):
    client, store, submitted, app = setup
    first = (await client.post('/api/industry-ai/cn.test.one/tasks', json=body())).json()
    store.upsert(first['task_id'], 'DONE')
    app.state.generation = 'restarted'
    response = await client.post('/api/industry-ai/cn.test.one/tasks', json=body(request_id='followup', generation='restarted', parent_task_id=first['task_id']))
    assert response.status_code == 200
    assert response.json()['origin']['generation'] == 'restarted'
    assert submitted[-1].app_scope.business == submitted[0].app_scope.business
