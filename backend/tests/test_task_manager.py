"""Product lifecycle around the official runtime, including disconnected clients."""
import asyncio
import pytest
from app.main import build_stack
from app.orchestrator.task_manager import TaskRequest
from tests.conftest import FakeChatModel, make_ai


def manager(tmp_path, responses):
    return build_stack(supervisor_llm=FakeChatModel(responses=responses),
                       whitelist=[str(tmp_path)])['task_manager']


@pytest.mark.asyncio
async def test_submit_returns_id_and_finishes(tmp_path):
    tm = manager(tmp_path, [make_ai('完成')])
    try:
        task_id = await tm.submit(TaskRequest(text='hello', session_mode='single-agent', enabled_skill_ids=[]))
        await asyncio.wait_for(tm._workers[task_id], 5)
        assert tm.status(task_id) == 'DONE'
        assert tm.admission.status()['active'] == 0
    finally:
        await tm.close()


@pytest.mark.asyncio
async def test_client_disconnect_does_not_cancel_task(tmp_path):
    tm = manager(tmp_path, [make_ai('完成')])
    stream = tm.handle(TaskRequest(task_id='disconnect', text='hello', session_mode='single-agent', enabled_skill_ids=[]))
    try:
        assert (await anext(stream))['type'] == 'graph.start'
        await stream.aclose()
        await asyncio.wait_for(tm._workers['disconnect'], 5)
        assert tm.status('disconnect') == 'DONE'
    finally:
        await tm.close()


@pytest.mark.asyncio
async def test_concurrent_sessions_do_not_mix_events(tmp_path):
    tm = manager(tmp_path, [make_ai('one'), make_ai('two')])
    async def collect(task_id):
        return [event async for event in tm.handle(TaskRequest(task_id=task_id, text='hello',
            session_id=task_id, session_mode='single-agent', enabled_skill_ids=[]))]
    try:
        a, b = await asyncio.gather(collect('a'), collect('b'))
        assert all(event['task_id'] == 'a' for event in a)
        assert all(event['task_id'] == 'b' for event in b)
        assert a[-1]['status'] == b[-1]['status'] == 'ok'
    finally:
        await tm.close()


@pytest.mark.asyncio
async def test_stop_before_execution_releases_admission(tmp_path):
    tm = manager(tmp_path, [make_ai('unused')])
    try:
        await tm.submit(TaskRequest(task_id='early', text='hello', enabled_skill_ids=[]))
        assert tm.cancel('early')
        await asyncio.sleep(.01)
        assert tm.status('early') == 'CANCELLED'
        assert tm.admission.status()['active'] == 0
        assert len(tm._tasks['early']['events']) == 1
    finally:
        await tm.close()


@pytest.mark.asyncio
async def test_missing_status_raises(tmp_path):
    tm = manager(tmp_path, [make_ai('unused')])
    try:
        with pytest.raises(KeyError):
            tm.status('missing')
    finally:
        await tm.close()


def test_cancel_session_targets_all_matching_runs_only():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app.orchestrator.task_manager import TaskManager
    manager = object.__new__(TaskManager)
    manager._requests = {
        'a': SimpleNamespace(session_id='deleted', project_id='p1'),
        'b': SimpleNamespace(session_id='deleted', project_id='p1'),
        'c': SimpleNamespace(session_id='other', project_id='p2'),
    }
    manager.cancel = Mock(return_value=True)
    assert manager.cancel_session('deleted') == 2
    assert {call.args[0] for call in manager.cancel.call_args_list} == {'a', 'b'}
